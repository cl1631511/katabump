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

# Windows 控制台默认 gbk，测试里那些 emoji/CJK 断言会直接把 print 炸掉（和代码无关，纯粹是这台机器的
# 编码）。CI 上是 UTF-8 所以只有本地裸跑会红 —— 自己把 stdout 收成 utf-8，失败才有意义。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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
# 统计行里的「已签到 N 天」不是今日已签：光秃秃的「已签到」曾把未签到页判成静默绿
ok(classify("您已连续签到 3 天，本月已签到 12 天", SITE_A.attend) not in (ALREADY, PASS),
   "统计行「已签到 12 天」不算今日已签")
ok(classify("签到成功，您已连续签到 4 天", SITE_A.attend) == PASS,
   "成功词优先于统计里的已签到 -> PASS（不是静默 ALREADY）")
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
ok("userdetails.php" in A_HTML and "userdetails.php" in M_HTML, "两站都有 userdetails 链接（_PAGE_SIGNALS_JS 依据）")

# ── 7. Cookie 解析与站点登录态要求 ──────────────────────────────────────────
pairs = aud.parse_cookie_header("uid=12345; passkey=abc123; cf_clearance=fakeClearance; PHPSESSID=x")
ok(pairs == [("uid", "12345"), ("passkey", "abc123"), ("cf_clearance", "fakeClearance"), ("PHPSESSID", "x")],
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
   "带前缀的整行粘贴同样能通过 audiences 的登录态检查")
ok(aud.session_ok([("uid", "1"), ("passkey", "a")], SITE_A), "普通模式 uid+passkey 可用")
ok(not aud.session_ok([("uid", "1")], SITE_A), "audiences: 只有 uid -> 不可用")
ok(not aud.session_ok([("cf_clearance", "a")], SITE_A), "audiences: 只有 cf_clearance -> 不可用")
ok(not aud.session_ok([("uuid", "abc")], SITE_M), "mua: 只有 uuid（那是用户 id，不是会话）-> 不可用")
ok(not aud.session_ok([("cf_clearance", "a"), ("lang", "cn")], SITE_M), "mua: 无会话字段 -> 不可用")

# ── 8. NexusPHP「安全 cookie」模式：真实站点用的就是这一组名字 ───────────────
# 上一版只认 uid/passkey，CI 上两站全被判成 NO_SESSION。名字取自公开日志，值一律不落测试。
SECURE_A = "c_secure_uid=ZmFrZVVpZA; c_secure_pass=fakeSessionToken; c_secure_login=fakeLoginFlag; c_secure_ssl=fakeSslFlag; cf_clearance=fakeClearance"
pairs_sec = aud.parse_cookie_header(SECURE_A)
ok(len(pairs_sec) == 5, "安全模式整行能解析出 5 项（全是假值，只测名字）")
ok(aud.session_ok(pairs_sec, SITE_A), "audiences: c_secure_pass -> 可用（他实际贴进去的就是这组字段名）")
ok(not aud.session_ok([("c_secure_uid", "ZmFrZVVpZA=")], SITE_A),
   "audiences: 只有 c_secure_uid -> 不可用（uid 不认证）")
ok(not aud.session_ok([("c_secure_ssl", "fakeSslFlag"), ("c_secure_login", "fakeLoginShort")], SITE_A),
   "audiences: c_secure_* 里非 pass 的字段不算登录态")
ok(aud.session_ok([("c_secure_pass", "x")], SITE_M), "mua: c_secure_pass 即算有会话")
ok(aud.parse_cookie_header("c_secure_uid=ZmFrZVVpZA%3D%3D") == [("c_secure_uid", "ZmFrZVVpZA%3D%3D")],
   "URL 编码值原样保留（不能把 %3D 当分隔符）")

# ===== 自检回路的日志清洗（证据要推到公开的 checkin-evidence 分支）=====
LOG = """📍  当前出口IP: 203.0.113.7
🔎 首枪后页面特征: 我的空间/退出链接=1 正文长度=820
随机一行页面原文：some_user_9527 同学 今日签到记录
📨 提交签到表单: submitted
🍪 首次请求前 写入成功 2/2: c_secure_uid, c_secure_pass"""
out = aud.sanitize_log(LOG)
ok("🔎 首枪后页面特征" in out and "📨 提交签到表单" in out and "🍪" in out,
   "L1 状态/计数行才留下")
ok("同学" not in out and "some_user_9527" not in out, "L2 不在白名单里的行一律不进证据")
ok("203.0.113.7" not in out and "203.0.113.*" in out, "L3 出口 IP 只留前三段")
ok(aud.sanitize_log("📨 token 是 " + "a" * 40).count("a") < 25,
   "L4 万一冒出一串凭证形状的东西，打码")

# ===== 措辞线索（取代 artifact：库是公开的，页面原文连本地文件都不留）=====
import contextlib
import io

BODY = ("some_user_9527 同学，今日已经签到，请明天再来吧。"
        "签到成功可获得 22 粒爆米花")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    aud._dump_evidence(SITE_A, BODY)
clue = buf.getvalue()
ok("some_user_9527" not in clue and "同学" not in clue, "L5 🧾 只报词汇，账号名不在里面")
ok("已经签到" in clue and "明天" in clue and "爆米花" in clue, "L6 站点词汇照常上报")
ok("🧾" in clue and "正文" in clue, "L7 🧾 行带长度、且能被 sanitize_log 白名单认出")
ok("已经签到" in aud.sanitize_log(clue), "L8 🧾 行能进证据（不会被清洗丢掉）")

# ── 9. 推送渠道：Bark 优先、退回 Telegram（方法照 PT-Checkin，一条实现两边共用）──
import urllib.parse

GETS, POSTS = [], []


class _Resp:
    status_code = 200
    text = "OK"


def _fake_get(url, params=None, timeout=None, **kw):
    GETS.append((url, params))
    return _Resp()


def _fake_post(url, json=None, timeout=None, **kw):
    POSTS.append((url, json))
    return _Resp()


req.get, req.post = _fake_get, _fake_post
app_mod.BARK_KEY, app_mod.BARK_URL = "fakeDeviceKey", "https://api.day.app"

ok(app_mod.send_bark("标题 A", "正文\n两行", critical=True) is True, "B1 Bark 发出即算成功")
u, p = GETS[-1]
ok(u == "/".join([app_mod.BARK_URL, "fakeDeviceKey",
                  urllib.parse.quote("标题 A", safe=""),
                  urllib.parse.quote("正文\n两行", safe="")]),
   "B2 URL 形状 = {base}/{key}/{title}/{body}（PT-Checkin 同款）")
ok(p["level"] == "critical" and p["group"] == "katabump", "B3 告警是 critical 级、同一分组")
ok(p["volume"] == "0" and p["sound"] == "minuet",
   "B3b 告警 volume=0（和 PT-Checkin 一致：横幅照弹、勿扰也弹，但不额外响铃）")
ok(app_mod.send_bark("t", "b") and GETS[-1][1]["level"] == "active", "B4 平时是 active 级")
ok("volume" not in GETS[-1][1], "B4b 普通通知不带 volume（用系统默认音量）")

# 账户身份：推送正文要经过 api.day.app（第三方），所以连域名都不许出现
GETS.clear(), POSTS.clear()
app_mod.CURRENT_EMAIL = "some_user_9527@example.com"
aud.TG_BOT_TOKEN, aud.TG_CHAT_ID = "fakeBot", "fakeChat"
ok(app_mod.push_notice("✅", "续期成功", "续期成功"), "B5 配了 BARK_KEY 就发 Bark")
ok(len(GETS) == 1 and not POSTS, "B6 有 Bark 就不再叠加 Telegram（同一件事只打扰一次）")
sent = urllib.parse.unquote(GETS[0][0])
ok("some_user_9527" not in sent and "example.com" not in sent,
   "B7 推送 URL 里没有账号本地名、也没有域名（以前只卡整串邮箱，域名就这么发给了第三方）")
ok("so****27" in sent, "B8 只留本地名两头（cl****11 形状）")
ok(app_mod.mask_email("ab@x.com") == "ab****" and app_mod.mask_email("") == "未知",
   "B9 短本地名不硬掩、空值不崩，且一律不带域名")
# mask_email 的输出还得能活着走过 app.py 顶层那个 stdout 过滤器：
# 带 @ 的掩码串（so****27@example.com）会被 MAIL_RE 从 "27@example.com" 咬掉，
# 日志里就成了 so*******@***.*** —— 掩码白做了。不带 @ 就原样通过。
_F = app_mod._SanitizeFilter
_washed = _F.MAIL_RE.sub("***@***.***", app_mod.mask_email("some_user_9527@example.com"))
ok(_washed == "so****27", "B9b 掩码形状不会被日志过滤器二次改写（带 @ 的那版会被洗成 cl*******@***.***）")
ok("@" not in _washed, "B9c 过滤器洗过的形状里仍然没有 @")

GETS.clear(), POSTS.clear()
app_mod.BARK_KEY = ""
app_mod.TG_BOT_TOKEN, app_mod.TG_CHAT_ID = "fakeBot", "fakeChat"
app_mod.push_notice("❌", "续期异常", "x", critical=True)
ok(not GETS and len(POSTS) == 1, "B10 没配 Bark 才退回 Telegram")
ok("some_user_9527" not in str(POSTS[0][1]), "B11 TG 那条同样只有掩码")

# 签到侧复用同一份实现
GETS.clear(), POSTS.clear()
app_mod.BARK_KEY = "fakeDeviceKey"
aud.notify(["✅ 🎬 audiences.me 签到成功", "⏳ 🍥 mua.xloli.cc 今日已签到"], alert=False)
ok(len(GETS) == 1 and not POSTS, "B12 签到也走 Bark，且用的就是 core.send_bark")
ok("PT 每日签到" in urllib.parse.unquote(GETS[0][0]), "B13 标题带业务名")
GETS.clear()
aud.notify(["❌ 🎬 audiences.me 登录态失效"], alert=True)
ok(GETS[0][1]["level"] == "critical", "B14 签到异常 = critical")
GETS.clear()
aud.notify(["⏳ 🎬 audiences.me 今日已签到", "⏳ 🍥 mua.xloli.cc 今日已签到"], False, all_already=True)
ok("今日均已签到" in urllib.parse.unquote(GETS[0][0]), "B15 全员已签到要说「均已签到」，不是「签到成功」")

GETS.clear(), POSTS.clear()
app_mod.BARK_KEY, aud.TG_BOT_TOKEN = "", ""
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    aud.notify(["✅ 🎬 audiences.me 签到成功"], False)
ok(not GETS and not POSTS and "都没配" in buf.getvalue(), "B16 两个渠道都没配 -> 结果只在 CI 日志里，且把这话说明白")
ok("📩" in aud.sanitize_log("📩 Bark 推送已送达"),
   "B17 推送结果行得进公开证据，否则我这边永远看不到「这轮到底发出去没有」")

# 「每轮都提醒」是这次的要点：今日都已签到也不能静默
GETS.clear()
app_mod.BARK_KEY = "fakeDeviceKey"
_real_run_site = aud.run_site
aud.run_site = lambda sb_kwargs, site: (aud.CHK_ALREADY, "")
try:
    with contextlib.redirect_stdout(io.StringIO()):
        aud.main()
finally:
    aud.run_site = _real_run_site
ok(len(GETS) == 1, "B18 全员已签到那一轮照样推一条（收到=今天没漏，没收到=该查）")

# ── 10. 续期每轮汇总：一条消息盖所有账号，且不顶着一个账号名 ────────────────
GETS.clear()
app_mod.CURRENT_EMAIL = "some_user_9527@example.com"
app_mod.push_notice("✅", "本轮跑完：1 个都在冷却期，无需续期",
                    "⏳ so****27 冷却期内无需续（剩 12 天）", account="")
sent = urllib.parse.unquote(GETS[0][0])
ok("👤" not in sent, "B19 account=\"\" 的汇总消息不带头部账号行（CURRENT_EMAIL 是最后一个账号，挂上去就是误导）")
ok("some_user_9527" not in sent and "@" not in sent and "example.com" not in sent,
   "B20 汇总正文同样只有掩码形状，且一个 @ 都没有")
GETS.clear()
app_mod.push_notice("✅", "续期成功", "到期 2026-11-04")
ok("👤 so****27" in urllib.parse.unquote(GETS[0][0]),
   "B21 不传 account 时仍按当前账号出头（单账号消息没变样）")
# 汇总行是拿 _alert_action 的 text 拼的，而它对「不单独告警」那两种状态返回空串 ——
# 空串进汇总就成了「⏳ ab****cd@x.com （剩 12 天）」这种读不出来的话，所以必须有兜底文案
_Quiet = {app_mod.RENEW_COOLDOWN, app_mod.RENEW_UNCONFIRMED}
ok(_Quiet <= set(app_mod._QUIET_TEXT), "B22 静默状态在汇总里都有人话（_QUIET_TEXT 覆盖全）")
for _st in (app_mod.RENEW_COOLDOWN, app_mod.RENEW_UNCONFIRMED):
    ok(app_mod._alert_action(_st, 12)[1] == "" and app_mod._QUIET_TEXT[_st],
       f"B23 {_st} 不单独告警但汇总有词：{app_mod._QUIET_TEXT[_st]}")

# ── 11. wash()：告警详情是页面上抠下来的自由文本，发给第三方前必须过一道 ──────
# 顶层的 stdout 过滤器只洗日志，洗不到 HTTP 正文 —— 这条以前是漏的。
DIRTY = ('登录失败 some_user_9527@example.com 于 203.0.113.7，'
         '面板 https://console.invalid:8443/?password=hunter2 提示 "token":"abc"')
w = app_mod.wash(DIRTY)
ok(all(s not in w for s in ("some_user_9527", "example.com", "203.0.113.7", "hunter2", '"abc"')),
   "B24 邮箱/IP/键值对/JSON 值全被洗掉：%s" % w)
ok("登录失败" in w and "提示" in w, "B25 洗的只是凭证形状，读得出是什么原因失败的")
GETS.clear()
app_mod.BARK_KEY = "fakeDeviceKey"
app_mod.push_notice("❌", "续期流程未跑通，需查看", DIRTY, critical=True, account="")
raw = urllib.parse.unquote(GETS[0][0])
ok("hunter2" not in raw and "some_user_9527" not in raw and "16315" not in raw,
   "B26 脏详情经过 push_notice 出口时确实被洗过才发出去")

print("\nALL OK")
