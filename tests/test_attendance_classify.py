#!/usr/bin/env python3
"""签到判定器的回归测试（防「把未签到页面的规则文案当成功」的假绿）。

运行: python tests/test_attendance_classify.py
只测纯函数：顶层 seleniumbase/requests 打空桩，不需要真浏览器。

反例素材是两站的未签到态真实页面快照：
  audiences_attendance_pre_submit.html / mua_attendance_pre_submit.html
它们本身就含「获得 / 连续签到 / 粒爆米花 / 人机验证 / 安全验证 / 今日签到」等字样，
任何宽松匹配都会在这里翻车。
"""
import html
import importlib.util
import os
import re
import sys
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

spec = importlib.util.spec_from_file_location("attendance_checkin", ROOT / "attendance_checkin.py")
aud = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aud)

classify = aud.classify_attendance
PASS, ALREADY = aud.CHK_PASS, aud.CHK_ALREADY
NO_SESSION, VERIFY_FAIL, UNKNOWN = aud.CHK_NO_SESSION, aud.CHK_VERIFY_FAIL, aud.CHK_UNKNOWN
SITE_A = [s for s in aud.SITES if s.key == "audiences"][0]
SITE_M = [s for s in aud.SITES if s.key == "mua"][0]


def load_text(name):
    raw = (ROOT / "tests" / "fixtures" / name).read_text(encoding="utf-8")
    return html.unescape(re.sub(r"<[^>]+>", " ", raw)), raw


A_TEXT, A_HTML = load_text("audiences_attendance_pre_submit.html")
M_TEXT, M_HTML = load_text("mua_attendance_pre_submit.html")


def ok(cond, label):
    print(("PASS" if cond else "FAIL"), label)
    if not cond:
        sys.exit(1)


# ── 1. 两站未签到态真实页面必须判不出成功（must-FAIL fixture）───────────────
ok(classify(A_TEXT, SITE_A.attend) == UNKNOWN, "audiences 未签到页 -> UNKNOWN")
ok(classify(A_TEXT, SITE_A.attend, True) == UNKNOWN, "audiences + 验证入口仍在 -> UNKNOWN")
ok(classify(M_TEXT, SITE_M.attend) == UNKNOWN, "mua 未签到页 -> UNKNOWN")
ok(classify(M_TEXT, SITE_M.attend, True) == UNKNOWN, "mua + 验证入口仍在 -> UNKNOWN")
ok(classify("", "") == UNKNOWN, "空页面 -> UNKNOWN")
ok(classify("Just a moment...", SITE_M.attend, False) == UNKNOWN, "CF 拦截页即使入口消失也不报绿")
ok(classify("安全检测能力由雷池WAF驱动 " * 20, SITE_M.attend, False) == UNKNOWN, "雷池拦截页不报绿")

# ── 2. mua 的表单标签「安全验证」不能被当成拦截页特征（否则正常页永远判不出）──
ok("安全验证" in M_TEXT, "mua 页面确实含「安全验证」字样")
ok(classify(M_TEXT + " 恭喜，签到成功", SITE_M.attend) == PASS, "mua 正文含安全验证不影响成功判定")

# ── 3. 明确的已签到/失败措辞 ────────────────────────────────────────────────
ok(classify("您今日已经签到，请勿重复打卡", SITE_A.attend) == ALREADY, "已签到措辞 -> ALREADY")
ok(classify("今日已签到", SITE_M.attend, True) == ALREADY, "今日已签到 -> ALREADY")
ok(classify("签到失败，请重新验证", SITE_A.attend) == VERIFY_FAIL, "验证失败优先于成功词 -> VERIFY_FAIL")

# ── 4. 成功信号 ─────────────────────────────────────────────────────────────
ok(classify("签到成功！获得 22 粒爆米花", SITE_A.attend) == PASS, "签到成功措辞 -> PASS")
ok(classify("您今天的签到已经完成", SITE_A.attend, False) == PASS, "无措辞但验证入口消失 -> PASS")
ok(classify("您今天的签到已经完成", SITE_A.attend, True) == UNKNOWN, "入口仍在且无措辞 -> UNKNOWN（不假绿）")

# ── 5. 登录态失效 ───────────────────────────────────────────────────────────
ok(classify(A_TEXT, SITE_A.home.replace("index.php", "login.php")) == NO_SESSION, "重定向 login.php -> NO_SESSION")
ok(classify("", SITE_M.attend.replace("attendance.php", "login.php")) == NO_SESSION, "空文本 + login.php -> NO_SESSION")

# ── 6. 注入脚本的选择器必须真能命中保存下来的 DOM ──────────────────────────
ok('class="cf-turnstile"' in A_HTML, "audiences 有 cf-turnstile 容器（_VERIFY_CARD_JS 选择器）")
ok('id="attendance-form"' in A_HTML and 'id="cf-token"' in A_HTML, "audiences 表单 id 与 cf-token 字段在")
ok('class="cf-turnstile"' in M_HTML, "mua 有 cf-turnstile 容器")
ok('action="attendance.php"' in M_HTML and 'type="submit"' in M_HTML, "mua 是「表单+提交按钮」结构（_SUBMIT_JS 走 click）")
ok("userdetails.php" in A_HTML and "userdetails.php" in M_HTML, "两站都有 userdetails 链接（_LOGGED_IN_JS 依据）")

# ── 7. Cookie 解析与站点登录态要求 ──────────────────────────────────────────
pairs = aud.parse_cookie_header("uid=12345; passkey=abc123; cf_clearance=hVq8; PHPSESSID=x")
ok(pairs == [("uid", "12345"), ("passkey", "abc123"), ("cf_clearance", "hVq8"), ("PHPSESSID", "x")],
   "Cookie 头解析")
ok(aud.parse_cookie_header('[{"name":"uid","value":"12345","domain":".audiences.me"}]')
   == [("uid", "12345")], "Playwright cookies JSON 解析")
ok(aud.parse_cookie_header("{不是合法JSON") == [], "坏 JSON -> []（不能当 cookie 注入）")
ok(aud.parse_cookie_header("") == [], "空 Cookie -> []")
# 他实际粘贴时的三种手式都得认（上一次 CI 就是卡在这里，两站秒退且原因被吞）
ok(aud.parse_cookie_header("Cookie: uid=1; passkey=a") == [("uid", "1"), ("passkey", "a")],
   "连「Cookie:」标签一起复制 -> 前缀要剥掉，否则第一个 cookie 名变成 'Cookie: uid' 判定就瞎了")
ok(aud.parse_cookie_header("cookie: uid=1; passkey=a") == [("uid", "1"), ("passkey", "a")],
   "小写 cookie: 前缀同样剥掉")
ok(aud.parse_cookie_header("uid=1\npasskey=a") == [("uid", "1"), ("passkey", "a")],
   "换行分隔（DevTools 多行头）")
ok(aud.parse_cookie_header("uid\t1\npasskey\ta") == [("uid", "1"), ("passkey", "a")],
   "Application→Cookies 网格的 name<Tab>value 逐行复制")
ok(aud.parse_cookie_header("uid=1;  ; passkey=a") == [("uid", "1"), ("passkey", "a")],
   "空段跳过")
ok(aud.parse_cookie_header("auth_token=abc=def") == [("auth_token", "abc=def")],
   "值里含 = 只按第一个 = 切")
ok(aud.session_ok(aud.parse_cookie_header("Cookie: uid=1; passkey=a"), SITE_A),
   "带前缀的整行粘贴同样能通过 audiences 的 uid+passkey 检查")
ok(aud.session_ok([("uid", "1"), ("passkey", "a")], SITE_A), "audiences: uid+passkey 可用")
ok(not aud.session_ok([("uid", "1")], SITE_A), "audiences: 缺 passkey -> 不可用")
ok(not aud.session_ok([("cf_clearance", "a")], SITE_A), "audiences: 只有 cf_clearance -> 不可用")
ok(aud.session_ok([("uuid", "abc"), ("passkey", "a")], SITE_M), "mua: passkey 即算有会话")
ok(not aud.session_ok([("cf_clearance", "a"), ("lang", "cn")], SITE_M), "mua: 无会话字段 -> 不可用")

print("\nALL OK")
