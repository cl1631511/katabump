#!/usr/bin/env python3
"""签到全流程的假浏览器测试（不启动 Selenium），覆盖 audiences 与 mua 两种表单结构。

重点验证三件事：
  1. 正常链路：注入 cookie → 打开签到页 → Turnstile 出 token → 提交 → 判成功
     （第一枪就必须带着 cookie：mua 无 cookie 直接拒连）；
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


class FakeFrame:
    """find_elements 回来的假元素，只需要能被 switch_to.frame 认出来。"""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return f"<FakeFrame {self.name}>"


class FakeSwitchTo:
    def __init__(self, sb):
        self.sb = sb

    def frame(self, el):
        self.sb.timeline.append(("frame_in", getattr(el, "name", "?")))
        self.sb.state["in_frame"] = True

    def default_content(self):
        self.sb.timeline.append(("frame_out", ""))
        self.sb.state["in_frame"] = False


class FakeDriver:
    """真 BaseCase 一定带 .driver（WebDriver），app._cdp 走 driver.execute_cdp_cmd 这条分支。"""

    def __init__(self, sb):
        self.sb = sb
        self.switch_to = FakeSwitchTo(sb)

    def execute_cdp_cmd(self, cmd, params):
        return self.sb._cdp(cmd, params)

    def execute_script(self, js, *args):
        return self.sb.execute_script(js)

    def find_elements(self, by, value):
        # 只有「签到入口还在」的那几页上才有 CF 的 iframe
        card = self.sb._cur()[2]
        if value.startswith("iframe"):
            return [FakeFrame(f"iframe{i}") for i in range(2)] if card else []
        return []



class FakeSB:
    """按 state['key'] 走剧本；执行 _SUBMIT_JS 时翻到 after_key。

    timeline 记录「写 cookie」和「导航」的先后，因为本流程的关键约束就是
    cookie 必须在第一次请求之前进罐（mua 无 cookie 不给连）。
    """

    def __init__(self, routes, nav_map, state):
        self.routes, self.nav_map, self.state = routes, nav_map, state
        self.cookies = []
        self.shots = []
        self.timeline = []
        self.driver = FakeDriver(self)

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def open(self, url): pass
    def get_text(self, sel): return "8.8.8.8"
    def get_title(self): return "签到 - Powered by NexusPHP"
    def save_screenshot(self, name): self.shots.append(name)

    def _cdp(self, cmd, params):
        # 只认代码真会发的命令；冒出别的说明调用点和测试没对上
        if cmd == "Input.dispatchMouseEvent":
            self.timeline.append(("mouse", params.get("type"),
                                  params.get("x"), params.get("y")))
            if params.get("type") == "mouseReleased" and self.state.get("solve_ok"):
                # 模拟「点得动」：真事件发出去后 CF 才把 token 填进 input
                self.state["token"] = self.state.get("issued") or TOKEN
            return {}
        if cmd != "Network.setCookie":
            raise AssertionError(f"假浏览器没认出的 CDP 命令: {cmd}")
        if not self.state.get("cdp_ok", True):
            raise RuntimeError("DevToolsActivePort file doesn't exist")
        self.timeline.append(("set_cookie", params["name"]))
        self.cookies.append((params["name"], params["domain"]))
        return {"success": True}


    def uc_open_with_reconnect(self, url, reconnect_time=6):
        self.timeline.append(("nav", url.split("?")[0]))
        k = self.nav_map.get(url.split("?")[0], "home")
        if self.state.get("nav_fails", 0) > 0:
            self.state["nav_fails"] -= 1
            self.state["err_page"] = True
        else:
            self.state["err_page"] = False
            self.state["key"] = k

    def add_cookie(self, cookie_dict, expiry=False):
        # 名字与 SeleniumBase 真实 API 一致；写成 set_cookie 就是首跑那个 bug
        if not self.state.get("page_cookie_ok", True):
            raise AttributeError("'BaseCase' object has no attribute 'set_cookie'")
        self.timeline.append(("add_cookie", cookie_dict["name"]))
        self.cookies.append((cookie_dict["name"], cookie_dict["domain"]))

    def get_cookies(self):
        # 真库返回 [{"name":.., "value":..}, ...]；值一律用假串
        return [{"name": n, "value": "fake"} for n, _ in self.cookies]

    def get_current_url(self):
        if self.state.get("err_page"):
            return "chrome-error://chromewebdata/"
        return self._cur()[0]

    def _cur(self):
        return self.routes[self.state["key"]]

    def execute_script(self, js):
        # 真 WebDriver 把脚本当「函数体」跑：顶层没有 return 语句就必然拿到 None。
        # 上一轮的假绿就是这个形状：_VERIFY_CARD_JS 写成裸 IIFE（里面 return、外面没有），
        # execute_script 恒返回 None -> bool(None)=False -> 「没读到入口」= 「今天已签到」。
        # 桩必须复刻这条语义，否则这类 bug 只有 CI 能发现（而 CI 发现的代价是一整轮假绿）。
        if self._bare_iife(js):
            return None
        # 分发按各脚本的独有串，顺序即特异性顺序（几条脚本都含 innerText / cf-turnstile-response）
        if "/*signals*/" in js: return self._signals()   # _PAGE_SIGNALS_JS
        if "/*diag*/" in js:                              # _TS_DIAG_JS
            card = self._cur()[2]
            return {"ifr": 2 if card else 0, "cfifr": 1 if card else 0,
                    "shroot": 3, "shifr": 0, "cfres": 4, "api": 1,
                    "wid": "760,230 300x65" if card else "no", "tok": 0}
        if "/*container*/" in js:                         # _TS_CONTAINER_JS
            # outer 抓不到 iframe 时靠容器矩形落点，所以两者要能各自独立失败
            if not self._cur()[2] or not self.state.get("container_ok", True):
                return None
            return {"x": 760, "y": 230, "w": 300, "h": 65}
        if "/*outer*/" in js:                             # _TS_OUTER_JS
            if not self._cur()[2] or not self.state.get("outer_ok", True):
                return None
            if self.state.get("outer_shadow"):
                # CF 的 widget iframe 挂在 open shadow root 里：看得见矩形、切不进去
                return {"idx": -2, "shadow": 1, "box": {"x": 700, "y": 300, "w": 300, "h": 65}}
            return {"idx": 0, "box": {"x": 500, "y": 200, "w": 300, "h": 65}}
        if "/*inner*/" in js:                            # _TS_INNER_JS
            if not self.state.get("in_frame"):
                raise AssertionError("没切进 iframe 就读内层矩形")
            return {"x": 8, "y": 6, "w": 65, "h": 65}
        if "/*shadow*/" in js:                           # _TS_SHADOW_CLICK_JS
            if not self._cur()[2]:
                return "no-checkbox"
            if self.state.get("solve_ok"):
                self.state["token"] = TOKEN
            return "shadow-clicked"
        if "/*execute*/" in js:                          # _TS_EXECUTE_JS
            if not self.state.get("api", True):
                return "no-api"
            if self.state.get("solve_ok"):
                self.state["token"] = TOKEN
            return "executed"
        if "no-token" in js:                             # _SUBMIT_JS
            self.state["key"] = self.state["after_key"]
            self.state["submitted"] = True
            return self.state["submit_ret"]
        if "i.value" in js: return self.state["token"]     # _read_token
        if "innerText" in js: return self._cur()[1]       # _BODY_TEXT_JS
        raise AssertionError("假浏览器没认出的脚本:\n" + js[:200])

    @staticmethod
    def _bare_iife(js):
        """脚本整体是个括号开头的表达式（IIFE），函数体里没有 return —— 真库给 None。"""
        body = re.sub(r"^/\*.*?\*/", "", js.strip(), flags=re.S).strip()
        return body.startswith("(")

    def _signals(self):
        """特征必须跟着「当前这一页」走：提交之后入口就没了，写死一份会测不出真假。

        signals 覆盖只作用于提交前那页 —— 它是用来构造页面剧本的，不是永久属性，
        否则「提交后入口消失」这条最关键的路径永远测不到。
        """
        _url, body, card = self._cur()
        sig = {"user": 1 if self.state["logged_in"] else 0, "login": 0,
               "form": 1 if card else 0, "widget": 1 if card else 0,
               "btn": 1 if card else 0, "cf": 1 if card else 0,
               "pw": 0, "len": len(body)}
        if self.state.get("submitted"):
            return sig
        if self.state.get("signals") == "boom":
            return "boom"
        sig.update(self.state["signals"] or {})
        return sig


def run_case(site, pre_body, card_pre=True, after_body="", after_card=False,
             attend_key="attend_pre", logged_in=True, token=TOKEN, solve_ok=True,
             pairs=None, submit_ret="submitted", nav_fails=0,
             cdp_ok=True, page_cookie_ok=True, signals=None,
             outer_ok=True, container_ok=True, outer_shadow=False):
    login_url = site.home.replace("index.php", "login.php")
    routes = {
        "home": (site.home, "x" * 300, False),
        "attend_pre": (site.attend, pre_body, card_pre),
        "login": (login_url, "请输入用户名 " * 30, False),
        "result": (site.attend, after_body, after_card),
    }
    state = {"key": "home", "logged_in": logged_in, "token": token,
             "after_key": "result", "submit_ret": submit_ret,
             "nav_fails": nav_fails, "cdp_ok": cdp_ok,
             "page_cookie_ok": page_cookie_ok, "submitted": False,
             # True = 这一下点击真能换来 token（CF 签发）；False = 点了也没用
             "solve_ok": solve_ok,
             # CI 里真实出现过的形状：顶层抓不到 CF iframe，只有 widget 容器
             "outer_ok": outer_ok, "container_ok": container_ok,
             "outer_shadow": outer_shadow,
             # None = 由当前页的 card 标志推导；给了就覆盖「提交前」那页（构造特殊页面）
             "signals": signals}
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
ok(sb.cookies == [("c_secure_uid", ".audiences.me"), ("c_secure_pass", ".audiences.me")],
   "A1b 安全模式 cookie 注入到 .audiences.me")
ok(("cf_clearance", ".audiences.me") not in sb.cookies,
   "A1b2 cf_clearance 一律不注入（它绑他家的出口 IP/UA，带进 CI 反而更容易卡盾）")
ok("attendance_audiences_result.png" in sb.shots, "A1c 成功也留截图，文件名带站点")

st, detail, sb = run_case(SITE_A, A_PRE, after_body=A_PRE, after_card=True)
ok(st == aud.CHK_UNKNOWN, f"A2 提交后页面不变 -> UNKNOWN，非 PASS（{st}）")

st, detail, sb = run_case(SITE_A, A_PRE, after_body="您今天的签到已经完成" + FILL, after_card=False)
ok(st == aud.CHK_PASS, f"A3 无措辞但入口消失 -> PASS（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, attend_key="login")
ok(st == aud.CHK_NO_SESSION, f"A4 重定向 login.php -> NO_SESSION（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, logged_in=False, card_pre=False,
                          signals={"user": 0, "login": 0, "form": 0, "widget": 0,
                                   "pw": 1, "len": 400})
ok(st == aud.CHK_NO_SESSION and "罐里有" in detail and "密码框=1" in detail,
   f"A5 无登录链接且无签到表单 -> NO_SESSION，并把页面特征打出来（{detail}）")

# 上一版死在这里：只认 userdetails 链接，链接名一变就把有签到表单的页判成没登录。
# 表单在页上 = 站点认为你是登录用户，必须继续走。
st, detail, sb = run_case(SITE_A, A_PRE, logged_in=False,
                          signals={"user": 0, "login": 0, "form": 1, "widget": 1,
                                   "pw": 0, "len": 900},
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
ok(st == aud.CHK_PASS, f"A5b 没登录链接但签到表单在页上 -> 按已登录继续（{detail}）")

st, detail, sb = run_case(SITE_A, "您今日已经签到，请勿重复打卡" + FILL)
ok(st == aud.CHK_ALREADY, f"A6 打开即已签到措辞 -> ALREADY（{detail}）")

# 上一版在这里报 PASS（「入口不在大概就是签好了」），mua 就这么被假绿了一整轮：
# 页面只有签到记录表格、既没入口也没成功措辞 —— 读不懂只能报红，绝不猜绿。
st, detail, sb = run_case(SITE_A, "今日签到记录：连续 12 天" + FILL, card_pre=False)
ok(st == aud.CHK_UNKNOWN and "宁红不绿" in detail,
   f"A7 打开即无入口又无措辞 -> UNKNOWN 而非 PASS（{detail}）")

# mua 的「立即签到」可能是 onclick 按钮、不在 <form> 里：入口判据不能只认 form 元素。
st, detail, sb = run_case(SITE_A, A_PRE, signals={"form": 0, "widget": 0, "btn": 1},
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
ok(st == aud.CHK_PASS, f"A7b 只有文字按钮、没有 form 元素 -> 仍算有入口并签到（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, token="", solve_ok=False)
ok(st == aud.CHK_VERIFY_FAIL, f"A8 Turnstile 失败 -> VERIFY_FAIL（{detail}）")
ok("attendance_audiences_turnstile_fail.png" in sb.shots, "A8b 失败留截图")

# 探针自己失灵（JS 抛/返回非 dict）时不能顺势报「站点不认 cookie」—— 那是探针的问题。
st, detail, sb = run_case(SITE_A, A_PRE, signals="boom",
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
ok(st == aud.CHK_PASS, f"A5c 特征探针返回非 dict -> 不据此判 NO_SESSION（{detail}）")

# 首跑的真实 bug：sb.set_cookie 根本不存在 -> 6 条 cookie 一条没落地 -> 站点当我是游客
# -> 302 到 login.php -> 日志却报「cookie 已失效」，把方向整个指错。注入失败必须单独说。
st, detail, sb = run_case(SITE_A, A_PRE, cdp_ok=False, page_cookie_ok=False)
ok(st == aud.CHK_UNKNOWN and "没写进浏览器" in detail,
   f"A9 两条注入路径都失败 -> UNKNOWN 并说明是注入这步（{detail}）")
ok(sb.cookies == [], "A9b 注入失败时确实一个 cookie 都没落地")

# 关键约束：cookie 先进罐，再发第一枪。先开首页等于拿游客身份去撞 mua 的连接闸门，
# 这条断言就是防止有人把顺序改回「导航 → 注入」。
st, detail, sb = run_case(SITE_A, A_PRE,
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
kinds = [t[0] for t in sb.timeline]
ok(kinds[0] == "set_cookie" and "nav" in kinds and kinds.index("nav") > kinds.index("set_cookie"),
   f"A13 第一次导航之前 cookie 已入罐（时间线 {kinds[:3]}）")
ok(SITE_A.home not in [u for k, u in sb.timeline if k == "nav"],
   "A13b 正常路径不再先去首页（那一趟不带 cookie，纯浪费 CF 时间）")
ok(SITE_A.attend in [u for k, u in sb.timeline if k == "nav"], "A13c 直接打开签到页")

# CDP 不可用（少见）时退回「先开首页建域 + add_cookie」，链路仍要跑通
st, detail, sb = run_case(SITE_A, A_PRE, cdp_ok=False,
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
ok(st == aud.CHK_PASS and ("add_cookie", "c_secure_pass") in sb.timeline,
   f"A13d CDP 不通时退回页面建域注入（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, nav_fails=1,
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
ok(st == aud.CHK_PASS, f"A10 签到页 chrome-error 重试一次就能签到（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, nav_fails=2)
ok(st == aud.CHK_UNKNOWN and "签到页 chrome-error" in detail and "罐里有" in detail,
   f"A11 两次都 chrome-error -> 报错误码并附 cookie 罐（{detail}）")


class _ErrPage:
    def get_title(self): return "mua.xloli.cc 的响应时间过长"
    def get_text(self, sel): return "ERR_CONNECTION_TIMED_OUT"


ok(aud._net_error(_ErrPage()) == "ERR_CONNECTION_TIMED_OUT", "A12 日志里带上 Chrome 的 ERR_ 码")

# ===== Turnstile：站点不静默签发时自己点，而且点数必须有上限 =====
# 上一轮 13 分钟就卡在这：core.handle_turnstile 里的 iframe 定位脚本也是裸 IIFE（恒 None），
# 定位不到就退化成 uc_gui 盲点 4 轮。现在点击由本模块自己做，最多两次。
st, detail, sb = run_case(SITE_A, A_PRE, token="",
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
released = [t for t in sb.timeline if t[0] == "mouse" and t[1] == "mouseReleased"]
ok(st == aud.CHK_PASS and len(released) == 1,
   f"A14 没静默签发 -> 自己点一次拿到 token 再提交（{len(released)} 次点击，{detail}）")
ok(released and (released[0][2], released[0][3]) == (540, 238),
   f"A14b 坐标=外层 iframe(500,200)+内层 widget(8,6,65x65) 的中心 {released and released[0][2:]}")

st, detail, sb = run_case(SITE_A, A_PRE, token="", solve_ok=False)
released = [t for t in sb.timeline if t[0] == "mouse" and t[1] == "mouseReleased"]
ok(st == aud.CHK_VERIFY_FAIL and len(released) == 1,
   f"A14c 点了还没 token -> 最多三招就收手报 VERIFY_FAIL（{len(released)} 次，{detail}）")
ok(len([t for t in sb.timeline if t[0] == "frame_in"]) >= 1,
   "A14d 第二次尝试是切进 iframe 穿透 shadow DOM 点 checkbox")

# CI 实测形状：CF组件=1 但顶层 document 里没有 challenges.cloudflare.com 的 iframe，
# _TS_OUTER_JS 返回 null -> 上一版直接放弃点击。现在退而点 widget 容器。
st, detail, sb = run_case(SITE_A, A_PRE, token="", outer_ok=False,
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
rel = [t for t in sb.timeline if t[0] == "mouse" and t[1] == "mouseReleased"]
ok(st == aud.CHK_PASS and len(rel) == 1 and (rel[0][2], rel[0][3]) == (794, 262),
   f"A14e 顶层没有 CF iframe -> 改点容器矩形中心偏左（{rel and rel[0][2:]}，{detail}）")

# 前两招都摸不到东西时，站点自己引的 turnstile API 还能重跑一次 widget
st, detail, sb = run_case(SITE_A, A_PRE, token="", outer_ok=False, container_ok=False,
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
rel = [t for t in sb.timeline if t[0] == "mouse" and t[1] == "mouseReleased"]
ok(st == aud.CHK_PASS and not rel,
   f"A14h 坐标点不着、shadow 也没有 -> turnstile.execute() 拿到 token（{detail}）")

st, detail, sb = run_case(SITE_A, A_PRE, token="", solve_ok=False,
                          outer_ok=False, container_ok=False)
rel = [t for t in sb.timeline if t[0] == "mouse" and t[1] == "mouseReleased"]
ok(st == aud.CHK_VERIFY_FAIL and not rel,
   f"A14f iframe 与容器都读不到 -> 一次鼠标事件都不发，两次尝试后报红（{detail}）")


st, detail, sb = run_case(SITE_A, A_PRE, token="", outer_shadow=True,
                          after_body="恭喜，签到成功！你获得 22 粒爆米花" + FILL)
rel = [t for t in sb.timeline if t[0] == "mouse" and t[1] == "mouseReleased"]
ok(st == aud.CHK_PASS and len(rel) == 1 and (rel[0][2], rel[0][3]) == (734, 332),
   f"A14g widget 在 shadow root 里：量得到矩形就按它点，不去切 frame（{rel and rel[0][2:]}）")
ok(not [t for t in sb.timeline if t[0] == "frame_in"],
   "A14g2 影子里的 iframe 切不进去，代码不能去切")


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
