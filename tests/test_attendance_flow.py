#!/usr/bin/env python3
"""签到全流程的假浏览器测试（不启动 Selenium），覆盖 audiences 与 mua 两种表单结构。

重点验证三件事：
  1. 正常链路：建域 → 注入 cookie → 打开签到页 → Turnstile 出 token → 提交 → 判成功；
  2. 防假绿：提交后页面仍是未签到快照（验证入口还在）时，绝不返回 PASS；
  3. 两站差异：audiences 无按钮走 form.submit()，mua 必须点「立即签到」按钮。

运行: python tests/test_attendance_flow.py
"""
import html
import importlib.util
import os
import re
import sys
import tempfile
import types
from pathlib import Path

os.environ.setdefault("USERS_JSON", "[]")

req = types.ModuleType("requests")
req.Session = object
req.post = lambda *a, **k: None
req.get = lambda *a, **k: None
sys.modules["requests"] = req
sb_pkg = types.ModuleType("seleniumbase")
sb_pkg.SB = object
sys.modules["seleniumbase"] = sb_pkg
for sub in ("common", "driver", "core", "js_code"):
    sys.modules[f"seleniumbase.{sub}"] = types.ModuleType(f"seleniumbase.{sub}")
sys.modules["webdriver_manager"] = types.ModuleType("webdriver_manager")

ROOT = Path(__file__).resolve().parent.parent
app_spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
app_mod = importlib.util.module_from_spec(app_spec)
sys.modules["app"] = app_mod
app_spec.loader.exec_module(app_mod)

aud_spec = importlib.util.spec_from_file_location("attendance_checkin", ROOT / "attendance_checkin.py")
aud = importlib.util.module_from_spec(aud_spec)
aud_spec.loader.exec_module(aud)

aud.time.sleep = lambda s: None          # 跑满等待循环但不真的等
os.chdir(tempfile.mkdtemp())             # 证据文件/截图不落进仓库

app_mod._egress_unusable = lambda t: False
app_mod._install_turnstile_hook_cdp = lambda sb: None
app_mod._pool_size = lambda: 0
app_mod._restart_proxy = lambda pin=None: None

SITE_A = [s for s in aud.SITES if s.key == "audiences"][0]
SITE_M = [s for s in aud.SITES if s.key == "mua"][0]


def fixture_text(name):
    raw = (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")
    return html.unescape(re.sub(r"<[^>]+>", " ", raw))


A_PRE = fixture_text("audiences_attendance_pre_submit.html")
M_PRE = fixture_text("mua_attendance_pre_submit.html")
TOKEN = "x" * 60
FILL = "\n" + "填充" * 120


class FakeSB:
    """按 state['key'] 走剧本；执行 _SUBMIT_JS 时翻到 after_key。"""

    def __init__(self, routes, nav_map, state):
        self.routes, self.nav_map, self.state = routes, nav_map, state
        self.cookies = []
        self.shots = []

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def open(self, url): pass
    def get_text(self, sel): return "8.8.8.8"
    def get_title(self): return "签到 - Powered by NexusPHP"
    def save_screenshot(self, name): self.shots.append(name)

    def uc_open_with_reconnect(self, url, reconnect_time=6):
        self.state["key"] = self.nav_map.get(url.split("?")[0], "home")

    def set_cookie(self, name, value, domain=None, path=None):
        self.cookies.append((name, domain))

    def get_current_url(self): return self._cur()[0]

    def _cur(self):
        return self.routes[self.state["key"]]

    def execute_script(self, js):
        # 分发按各脚本的独有串，顺序即特异性顺序（几条脚本都含 innerText / cf-turnstile-response）
        if "no-token" in js:                             # _SUBMIT_JS
            self.state["key"] = self.state["after_key"]
            return self.state["submit_ret"]
        if "人机验证" in js: return self._cur()[2]         # _VERIFY_CARD_JS
        if "userdetails.php" in js: return self.state["logged_in"]   # _LOGGED_IN_JS
        if "i.value" in js: return self.state["token"]    # _read_token
        if "innerText" in js: return self._cur()[1]       # _BODY_TEXT_JS
        raise AssertionError("假浏览器没认出的脚本:\n" + js[:200])


def run_case(site, pre_body, card_pre=True, after_body="", after_card=False,
             attend_key="attend_pre", logged_in=True, token=TOKEN, solve_ok=True,
             pairs=None, submit_ret="submitted"):
    login_url = site.home.replace("index.php", "login.php")
    routes = {
        "home": (site.home, "x" * 300, False),
        "attend_pre": (site.attend, pre_body, card_pre),
        "login": (login_url, "请输入用户名 " * 30, False),
        "result": (site.attend, after_body, after_card),
    }
    state = {"key": "home", "logged_in": logged_in, "token": token,
             "after_key": "result", "submit_ret": submit_ret}
    app_mod._turnstile_token_ok = lambda sb: bool(state["token"])
    app_mod._turnstile_present = lambda sb: True
    app_mod.handle_turnstile = lambda sb: solve_ok and bool(state["token"])
    captured = {}

    def fake_sb(**kw):
        s = FakeSB(routes, {site.home: "home", site.attend: attend_key}, state)
        captured["sb"] = s
        return s

    aud.SB = fake_sb
    if pairs is None:
        # 默认用 NexusPHP 安全模式的真实字段名（他浏览器里看到的就是这一组）
        pairs = [("c_secure_uid", "ZmFrZVVpZA"), ("c_secure_pass", "fakeSessionToken"), ("cf_clearance", "fakeClearance")]
    st, detail = aud.checkin({"uc": True}, site, pairs)
    return st, detail, captured["sb"]


def ok(cond, label):
    print(("PASS" if cond else "FAIL"), label)
    if not cond:
        sys.exit(1)


# ===== audiences（无按钮，widget 回调自动提交）=====
st, detail, sb = run_case(SITE_A, A_PRE, after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
ok(st == aud.CHK_PASS, f"A1 正常链路 -> PASS（{detail}）")
ok(sb.cookies == [("c_secure_uid", ".audiences.me"), ("c_secure_pass", ".audiences.me"),
                  ("cf_clearance", ".audiences.me")], "A1b 安全模式 cookie 注入到 .audiences.me")
ok("attendance_audiences_result.png" in sb.shots, "A1c 成功也留截图，文件名带站点")

st, detail, sb = run_case(SITE_A, A_PRE, after_body=A_PRE, after_card=True)
ok(st == aud.CHK_UNKNOWN, f"A2 提交后页面不变 -> UNKNOWN，非 PASS（{st}）")

st, detail, sb = run_case(SITE_A, A_PRE, after_body="您今天的签到已经完成" + FILL, after_card=False)
ok(st == aud.CHK_PASS, f"A3 无措辞但入口消失 -> PASS（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, attend_key="login")
ok(st == aud.CHK_NO_SESSION, f"A4 重定向 login.php -> NO_SESSION（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, logged_in=False)
ok(st == aud.CHK_NO_SESSION, f"A5 无 userdetails 链接 -> NO_SESSION（{detail}）")

st, detail, sb = run_case(SITE_A, "您今日已经签到，请勿重复打卡" + FILL)
ok(st == aud.CHK_ALREADY, f"A6 打开即已签到措辞 -> ALREADY（{detail}）")

st, detail, sb = run_case(SITE_A, "今日签到记录：连续 12 天" + FILL, card_pre=False)
ok(st == aud.CHK_PASS, f"A7 打开即无验证入口 -> 判定已签到（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, token="", solve_ok=False)
ok(st == aud.CHK_VERIFY_FAIL, f"A8 Turnstile 失败 -> VERIFY_FAIL（{detail}）")
ok("attendance_audiences_turnstile_fail.png" in sb.shots, "A8b 失败留截图")

# ===== mua（有「立即签到」按钮）=====
# 这里显式用普通模式 uid+passkey，证明两种登录 cookie 形态都能走完整条链路
st, detail, sb = run_case(SITE_M, M_PRE, after_body="签到成功，获得魔力值 100" + FILL,
                          submit_ret="clicked",
                          pairs=[("uid", "1"), ("passkey", "abc")])
ok(st == aud.CHK_PASS, f"M1 正常链路 -> PASS（{detail}）")
ok(sb.cookies == [("uid", ".mua.xloli.cc"), ("passkey", ".mua.xloli.cc")], "M1b 普通模式 cookie 注入到 .mua.xloli.cc")

st, detail, sb = run_case(SITE_M, M_PRE, after_body=M_PRE, after_card=True)
ok(st == aud.CHK_UNKNOWN, f"M2 提交后仍是未签到快照 -> UNKNOWN，非 PASS（{st}）")

st, detail, sb = run_case(SITE_M, M_PRE, after_body="明天再来吧" + FILL, after_card=False)
ok(st == aud.CHK_PASS, f"M3 无措辞但入口消失 -> PASS（{detail}）")

st, detail, sb = run_case(SITE_M, M_PRE, attend_key="login")
ok(st == aud.CHK_NO_SESSION, f"M4 重定向 login.php -> NO_SESSION（{detail}）")

st, detail, sb = run_case(SITE_M, M_PRE, token="", solve_ok=False)
ok(st == aud.CHK_VERIFY_FAIL, f"M5 Turnstile 失败 -> VERIFY_FAIL（{detail}）")
ok("attendance_mua_turnstile_fail.png" in sb.shots, "M5b 截图名不与 audiences 冲突")

# ===== 站点级：cookie 配置缺失 / 字段不符 =====
os.environ.pop("MUA_COOKIE", None)
st, detail = aud.run_site({"uc": True}, SITE_M)
ok(st == aud.CHK_NO_SESSION and "MUA_COOKIE" in detail, f"S1 未配置 MUA_COOKIE -> 直接提示（{detail}）")

os.environ["MUA_COOKIE"] = "cf_clearance=abc; lang=cn"
st, detail = aud.run_site({"uc": True}, SITE_M)
ok(st == aud.CHK_NO_SESSION and "缺少登录 cookie" in detail, f"S2 cookie 无会话字段 -> 不启动浏览器（{detail}）")

os.environ["MUA_COOKIE"] = "c_secure_pass=fakeSessionToken"
mua_pairs = aud.parse_cookie_header(os.environ["MUA_COOKIE"])
ok(aud.session_ok(mua_pairs, SITE_M), "S3 mua 只有 c_secure_pass 一项也算有效会话（他实际粘的就是这样）")

os.environ["MUA_COOKIE"] = "uuid=00000000-0000-4000-8000-000000000000; passkey=abc"
ok(aud.session_ok(aud.parse_cookie_header(os.environ["MUA_COOKIE"]), SITE_M),
   "S3b 普通模式 passkey 同样有效")

os.environ["AUDIENCES_COOKIE"] = "uid=12345"
st, detail = aud.run_site({"uc": True}, SITE_A)
ok(st == aud.CHK_NO_SESSION and "c_secure_pass" in detail,
   f"S4 audiences 只有 uid -> 提示需要哪些字段（{detail}）")

os.environ["AUDIENCES_COOKIE"] = "c_secure_uid=ZmFrZVVpZA; c_secure_ssl=fakeSslFlag"
st, detail = aud.run_site({"uc": True}, SITE_A)
ok(st == aud.CHK_NO_SESSION, f"S5 安全模式里非 pass 的字段不启动浏览器（{detail}）")

print("\nALL OK")
