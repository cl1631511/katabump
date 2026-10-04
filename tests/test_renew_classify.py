#!/usr/bin/env python3
"""续期结果分类器的回归测试（防 2026-09-03 "suspend 却假绿" 事故复发）。

运行: /path/to/venv/bin/python tests/test_renew_classify.py
要求能 import app.py（顶层 import requests/seleniumbase；测试会先打空桩，无需真安装 Selenium）。
"""
import importlib.util
import json
import sys
import types

# Windows 控制台默认 gbk，app.py 顶层那些 ❌/中文 print 会炸掉裸跑（CI 上是 UTF-8，不受影响）。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ---- 打桩 app.py 顶层重型依赖（仅测纯函数，不需要真 Selenium/requests）----
req = types.ModuleType("requests")
req.Session = object
req.get = lambda *a, **k: None
sys.modules["requests"] = req

sb_pkg = types.ModuleType("seleniumbase")
sb_pkg.SB = object
sys.modules["seleniumbase"] = sb_pkg
for sub in ("common", "driver", "core", "js_code"):
    m = types.ModuleType(f"seleniumbase.{sub}")
    sys.modules[f"seleniumbase.{sub}"] = m
sys.modules["webdriver_manager"] = types.ModuleType("webdriver_manager")

from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("app", ROOT / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

_classify_renew = app._classify_renew
_next_renewable = app._next_renewable
RENEW_PASS, RENEW_COOLDOWN, RENEW_SUSPENDED = app.RENEW_PASS, app.RENEW_COOLDOWN, app.RENEW_SUSPENDED
RENEW_UNCONFIRMED, RENEW_UNKNOWN = app.RENEW_UNCONFIRMED, app.RENEW_UNKNOWN

SRV_WARN = (
    "Warning: changing the server type will reset the startup command "
    "and environment variables to the new type's defaults. Your files will not be affected."
)

def ok(cond, label):
    print(("✅" if cond else "❌"), label)
    if not cond:
        sys.exit(1)

SUSPEND_BODY = "Your server is suspended because you did not renew it in time. You can still renew it."

# ---- 多节点结果合并 `_merge_result`（根因回归：09-04 实锤节点3 unknown 误覆盖冷却）----
mr = app._merge_result
_Rsus = app.RENEW_SUSPENDED
# 09-04 核心回归：冷却之后瞬态 unknown → 必须保持冷却，不刷红
ok(mr(RENEW_COOLDOWN, None, app.RENEW_UNKNOWN, None) == (RENEW_COOLDOWN, None),
   "冷却 → 瞬态unknown: 保持冷却(不刷红)[09-04回归]")
# unknown 先进、后 cooldown → 升级为 cooldown
ok(mr(app.RENEW_UNKNOWN, None, RENEW_COOLDOWN, None) == (RENEW_COOLDOWN, None),
   "unknown → cooldown: 升级冷却")
# suspended 恒最高：无论之前是什么都硬红
ok(mr(RENEW_COOLDOWN, None, _Rsus, None)[0] == _Rsus, "任何 → suspended: 恒硬红")
ok(mr(app.RENEW_UNKNOWN, None, _Rsus, None)[0] == _Rsus, "unknown → suspended: 硬红")
# pass 高于 unconfirmed
ok(mr(RENEW_UNCONFIRMED, None, RENEW_PASS, None)[0] == RENEW_PASS, "unconfirmed → pass: 升为成功")
# 同级保持先
ok(mr(RENEW_COOLDOWN, 7, RENEW_COOLDOWN, 5) == (RENEW_COOLDOWN, 5), "同冷却: 采纳较新 rdays(5)")
ok(mr(RENEW_COOLDOWN, 5, RENEW_COOLDOWN, 7) == (RENEW_COOLDOWN, 7), "同冷却: 采纳较新 rdays(7)")
# unconfirmed 不被后续 unknown 覆盖
ok(mr(RENEW_UNCONFIRMED, None, app.RENEW_UNKNOWN, None) == (RENEW_UNCONFIRMED, None), "unconfirmed → unknown: 不降")
# 三重：cool→unconfirmed→unknown 最终仍冷却（全健康不刷红）
ok(mr(mr(RENEW_COOLDOWN, None, RENEW_UNCONFIRMED, None)[0], None, app.RENEW_UNKNOWN, None)[0] == RENEW_COOLDOWN,
   "三重冲突最终冷却(不刷红)")

print("✅ 合并 `_merge_result` 测试通过 (9 项)")

ok(_classify_renew("", "your server has been renewed successfully. new expiry 2026-09-16")[0] == RENEW_PASS,
   "真续期成功 → ok")
ok(_classify_renew("Your service has been renewed.", SRV_WARN)[0] == RENEW_PASS,
   "KataBump 面板实测提示: Your service has been renewed → pass")
ok(_classify_renew(SRV_WARN, "")[0] == RENEW_UNCONFIRMED,
   "仅 server-type 警告、无成功确认 → unconfirmed(红) [关键回归: 09-02 事故]")
ok(_classify_renew("", "You can't renew your server yet. as of 10 September 2026 (in 7 day(s)).")[0] == RENEW_COOLDOWN,
   "显式 can't renew(7天) → cooldown")
ok(_classify_renew("", SUSPEND_BODY)[0] == RENEW_SUSPENDED,
   "显式 suspended → suspended")
ok(_classify_renew("", "a random page that contains the word success but nothing about renewal")[0] == RENEW_UNKNOWN,
   "裸 success 无 renew → unknown（防误报）")
ok(_classify_renew(SRV_WARN, SRV_WARN + " Next renewal as of 05 September 2026 (in 2 day(s)).")[0] == RENEW_UNCONFIRMED,
   "仅警告 + 剩 2 天临界 → unconfirmed(红)")
ok(_classify_renew(SRV_WARN, SRV_WARN + " as of 12 September 2026 (in 9 day(s)).")[0] == RENEW_COOLDOWN,
   "仅警告 + 剩 9 天充足 → cooldown(绿)")
ok(_next_renewable("as of 05 September 2026 (in 2 day(s))") == ("05 september 2026", 2),
   "_next_renewable 精确解析天数")
ok(_next_renewable("available to renew as of 10 Sep 2026 (in 7 days)") == ("10 sep 2026", 7),
   "_next_renewable 解析 7 天")

# ---- 新增：拔出的 remaining_days（供 main 决定是否告警）----
ok(_classify_renew(SRV_WARN, "")[2] is None,
   "仅 server-type 警告无上下文 → remaining_days=None（健康冷却，静默不告警）")
ok(_classify_renew("", "You can't renew your server yet. as of 10 September 2026 (in 7 day(s)).")[2] == 7,
   "cooldown 显式 7 天 → remaining_days=7（静默）")
ok(_classify_renew(SRV_WARN, SRV_WARN + " as of 12 September 2026 (in 2 day(s)).")[2] == 2,
   "server-type + 剩 2 天 → remaining_days=2（main 判红告警）")
ok(_classify_renew("", SUSPEND_BODY)[0] == RENEW_SUSPENDED,
   "suspended → remaining_days 兜底红告警")

print("\n✅ 分类器+剩余天数+裸unable边界 通过 (9 + 4 + 2 = 15/15)")
# ---- 裸 unable 不误当冷却（防新告警逻辑静默掩真问题）----
ok(_classify_renew("", "Unable to renew the server, please try again later.")[0] == RENEW_UNKNOWN,
   "裸 unable 无冷却信息 → unknown(告警)，不静默成 cooldown")
ok(_classify_renew("", "You can't renew your server yet. as of 10 September 2026 (in 3 day(s)).")[0] == RENEW_COOLDOWN,
   "can't renew+明确天数 → cooldown(静默)")


# ---- 状态跳过引擎 `_days_until_next_renewable` / `_save_state` / `_load_state`（根因）----
import tempfile, os as _os
from datetime import date, timedelta

_tmp = tempfile.mkdtemp()
_TSTFILE = _os.path.join(_tmp, "state.json")
_old_statefile = app.STATE_FILE
app.STATE_FILE = _TSTFILE

# 无状态 → None（fail-open，会走完整流程）
ok(app._days_until_next_renewable("a@x.com") is None, "无状态 → None(fail-open 走完整)")

# 写入临近 expiry（明天）→ 1 → 未到冷却跳过线（仅剩 1 天，尝试 Renew）
app._save_state("a@x.com", (date.today()+timedelta(days=1)).isoformat())
ok(app._days_until_next_renewable("a@x.com")==1, "expiry 明天→仍尝试(1)")

# 冷却期（expiry 距今 12 天）→ 12，赋给 skip 逻辑(>2→跳过)
today = date.today()
app._save_state("b@x.com", (today+timedelta(days=12)).isoformat())
ok(app._days_until_next_renewable("b@x.com")==12, "expiry 12天后 → 12（冷却期跳过）")

# 已过期 → None（fail-open 必须尝试）
app._save_state("c@x.com", (today-timedelta(days=1)).isoformat())
ok(app._days_until_next_renewable("c@x.com") is None, "已过期 → None → 必须尝试")

# 损坏状态 → None（fail-open）
with open(_TSTFILE,"w") as f: f.write("{bad json")
ok(app._days_until_next_renewable("b@x.com") is None, "损坏状态 → None(fail-open)")
app.STATE_FILE = _old_statefile

# _parse_date 各种格式
ok(str(app._parse_date("2026-09-16"))=="2026-09-16", "parse YYYY-MM-DD")
ok(app._parse_date("11 August 2026") is not None, "parse '11 August 2026'")
ok(app._parse_date("nonsense") is None, "parse 非法 → None")

# _extract_expiry（返回 date）
ok(str(app._extract_expiry("renewed until 2026-09-16"))=="2026-09-16", "提取 'until 2026-09-16'")
ok(app._extract_expiry("no date here") is None, "无日期 → None")
ok(app._extract_expiry(None) is None, "空 detail → None")

print("\n✅ 状态跳过引擎测试通过 (12 项)")


# ---- 根系冷却探测 `_probe_cooldown_text`（根因：冷却期不去点 Renew）----
_probe = app._probe_cooldown_text

# 冷却文案 + 明确天数 → 判冷却，返回剩余天数（源头结束，不再点 Renew）
ok(_probe("You can't renew your server yet. as of 10 September 2026 (in 7 day(s)).") == (True, 7),
   "冷确文案+7天 → cooldown(7)[根因：源头跳过 Renew]")
ok(_probe("server is cooling down, cannot renew until as of 16 September 2026 (in 11 day(s)).") == (True, 11),
   "cannot renew+11天 → (True,11)")
# 无冷却文案 / 无天数 → 不判冷却（继续走 Renew 流程）
ok(_probe("") == (False, None), "空正文 → 非冷却")
ok(_probe("Unable to renew the server, please retry.") == (False, None),
   "裸 unable 无天数 → 非冷却(不误导成冷却)")
ok(_probe("Your server has been renewed successfully. new expiry 2026-09-16.") == (False, None),
   "成功文案 → 非冷却")
ok(_probe(SRV_WARN) == (False, None),
   "仅 server-type 静态警告 → 非冷却 → 会走 Renew（前端本身无天数）")

print("\n✅ 根因-冷却探测 `_probe_cooldown_text` 通过 (6 项)")


# ---- 告警决策 `_alert_action` 矩阵（用户拍板：只有真问题才告警）----
_alert_action = app._alert_action

def alert_is(a):
    return a[2]  # (icon, text, should_alert)[2]

# 静默（健康）：冷却期、明确剩余天数 >2 的 unconfirmed
ok(_alert_action(app.RENEW_COOLDOWN, None)[2] is False, "cooldown(无天数) → 静默")
ok(_alert_action(app.RENEW_COOLDOWN, 9)[2] is False, "cooldown(9天) → 静默")
ok(_alert_action(app.RENEW_UNCONFIRMED, 7)[2] is False, "unconfirmed(剩7天>2) → 健康冷却，静默")
# 真问题 → 告警
ok(_alert_action(app.RENEW_UNCONFIRMED, None)[2] is True, "unconfirmed(无天数) → 红告警[根因09-08：未知到，绝静默]")
ok(_alert_action(app.RENEW_SUSPENDED, None)[2] is True, "suspended → 红告警")
ok(_alert_action(app.RENEW_UNKNOWN, None)[2] is True, "unknown(流程未跑通) → 红告警[不静默]")
ok(_alert_action(app.RENEW_UNCONFIRMED, 2)[2] is True, "unconfirmed(剩2天) → 红告警")
ok(_alert_action(app.RENEW_UNCONFIRMED, 1)[2] is True, "unconfirmed(剩1天) → 红告警")
ok(_alert_action(app.RENEW_UNCONFIRMED, 0)[2] is True, "unconfirmed(剩0天) → 红告警")
# PASS → 通知（非告警）
ok(_alert_action(app.RENEW_PASS, None)[2] is False
   and _alert_action(app.RENEW_PASS, None)[0] == "✅", "PASS → ✅通知(非告警)")

print("\n✅ 告警决策 `_alert_action` 测试通过 (10 项)")


# ---- 出口探测 `_egress_unusable`（根因 09-11：ERR_CONNECTION_RESET 仍去登录）----
_eu = app._egress_unusable
ok(_eu("") is True, "空出口文本 → 不可用")
ok(_eu("148.244.144.194") is False, "纯 IPv4 → 可用")
ok(_eu("104.251.93.55") is False, "Frontier 家宽 IP → 可用")
ok(_eu("This site can’t be reached The connection was reset. ERR_CONNECTION_RESET") is True,
   "chrome ERR_CONNECTION_RESET → 不可用")
ok(_eu("This site can't be reached") is True, "can't be reached → 不可用")
ok(_eu("chrome-error://chromewebdata/") is True, "chrome-error URL → 不可用")
ok(_eu("not an ip at all") is True, "无 IP 的乱文 → 不可用")
ok(_eu("This site can’t be reached ipv4.icanhazip.com took too long to respond. ERR_TIMED_OUT") is True,
   "chrome ERR_TIMED_OUT → 不可用")

print("\n✅ 出口探测 `_egress_unusable` 通过 (8 项)")

# ---- ALTCHA payload 闸门（根因 09-11：challenge JWT 假通过 → unconfirmed）----
import base64 as _b64
def _jwt(payload: dict) -> str:
    body = json.dumps(payload, separators=(",", ":")).encode()
    mid = _b64.urlsafe_b64encode(body).decode().rstrip("=")
    return f"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.{mid}.xx"

_ap = app._altcha_payload_ok
_ak = app._altcha_payload_kind
ok(_ap("") is False, "空 payload → 不可提交")
ok(_ap("short") is False, "过短 → 不可提交")
ok(_ak("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.xx") == "challenge-jwt", "无 number 的 JWT = challenge")
ok(_ap("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.xx") is False, "challenge JWT → 不可提交")
ok(_ap(_jwt({"algorithm": "SHA-256", "challenge": "abc"})) is False, "challenge claims JWT → 不可提交")
ok(_ap(_jwt({"algorithm": "SHA-256", "number": 42, "signature": "x"})) is True, "solved JWT（含 number）→ 可提交")
ok(_ap('{"algorithm":"SHA-256","challenge":"abc","signature":"x"}') is False, "无 number 的 JSON → 不可提交")
ok(_ap('{"algorithm":"SHA-256","challenge":"abc","number":7,"signature":"x"}') is True, "solved JSON → 可提交")
real_altcha_solution = '{"algorithm":"SHA-256","challenge":"eede03e8c2947275785619c09e828574ce1f9062e1eabbe56a7307c6ff5e3ce","number":465836,"salt":"fbc22922aeffb5fa5e3b3e7d?expires=1789271408","signature":"6ece80e4cb5bb14003879b4c6ca22c5190e799f47e4ff5c8874daa14b3590adf","took":712}'
ok(_ak(real_altcha_solution) == "solved-json", "真实 Katabump AltCHA payload → solved-json")
ok(_ap(real_altcha_solution) is True, "真实 Katabump AltCHA payload → 可提交")
ok(_ap("not-a-token-but-longer-than-twenty-chars") is False, "长但非 JWT/JSON → 不可提交")


_b64_sol = _b64.b64encode(real_altcha_solution.encode()).decode()
ok(_ak(_b64_sol) == "solved-b64", "Base64 格式 AltCHA payload -> solved-b64")
ok(_ap(_b64_sol) is True, "Base64 格式 AltCHA payload -> 可提交")
_b64_chal = _b64.b64encode(json.dumps({"algorithm": "SHA-256", "challenge": "abc"}).encode()).decode()
ok(_ak(_b64_chal) == "challenge-b64", "Base64 格式 AltCHA challenge -> challenge-b64")
ok(_ap(_b64_chal) is False, "Base64 格式 AltCHA challenge -> 不可提交")

print("\n✅ ALTCHA payload 闸门通过 (15 项)")

# ---- PIN_NODE / PROXY_CHAIN_URL（根因 09-11：住宅池全挂，ZooProxy 经 AnyTLS 二跳）----
import os as _os
ph_spec = importlib.util.spec_from_file_location("proxy_handler", ROOT / "proxy_handler.py")
ph = importlib.util.module_from_spec(ph_spec)
ph_spec.loader.exec_module(ph)

_orig_cwd = _os.getcwd()
_tmpdir = ROOT / ".pin-test-tmp"
_tmpdir.mkdir(exist_ok=True)
_sample_pool = [
    {"name": "Frontier-US-1", "server": "104.251.93.55", "port": 16062},
    {"name": "Telmex-CO", "server": "200.118.71.12", "port": 8080},
]
try:
    _os.chdir(_tmpdir)
    (_tmpdir / "sample-pool.json").write_text(json.dumps(_sample_pool))
    _os.environ["PROXY_URL"] = "http://example.invalid:8080"
    _os.environ["POOL_FILE"] = str(_tmpdir / "sample-pool.json")
    _os.environ.pop("PROXY_CHAIN_URL", None)
    _os.environ["PIN_NODE"] = "2"
    ph.main()
    cfg = json.loads((_tmpdir / "config.json").read_text())
    proxy_ob = next(o for o in cfg["outbounds"] if o.get("tag") == "proxy")
    ok("urltest" not in [o.get("type") for o in cfg["outbounds"]], "PIN_NODE=2 无 urltest")
    ok(proxy_ob.get("server") == "200.118.71.12" and proxy_ob.get("server_port") == 8080,
       "PIN_NODE=2 → Telmex-CO 200.118.71.12:8080")
    ok(cfg.get("route", {}).get("final") == "proxy", "route.final=proxy")
    _os.environ["PIN_NODE"] = "1"
    ph.main()
    cfg1 = json.loads((_tmpdir / "config.json").read_text())
    p1 = next(o for o in cfg1["outbounds"] if o.get("tag") == "proxy")
    ok(p1.get("server") == "104.251.93.55", "PIN_NODE=1 → Frontier-US-1")
    del _os.environ["PIN_NODE"]
    ph.main()
    cfgp = json.loads((_tmpdir / "config.json").read_text())
    types = [o.get("type") for o in cfgp["outbounds"]]
    ok("urltest" in types, "无 PIN_NODE → urltest 池")
    _os.environ.pop("PIN_NODE", None)
    _os.environ.pop("POOL_FILE", None)
    _os.environ["PROXY_URL"] = "anytls://secret@vps.example:60629?sni=vps.example&fp=chrome&insecure=1"
    _os.environ["PROXY_CHAIN_URL"] = "http://user:pass@as.zooproxy.com:5000"
    ph.main()
    cfgc = json.loads((_tmpdir / "config.json").read_text())
    tags = {o.get("tag"): o for o in cfgc["outbounds"]}
    ok(tags["dialer"]["type"] == "anytls" and tags["dialer"]["server"] == "vps.example",
       "chain dialer = anytls vps")
    ok(tags["proxy"]["type"] == "http" and tags["proxy"].get("detour") == "dialer"
       and tags["proxy"]["server"] == "as.zooproxy.com",
       "chain proxy = ZooProxy HTTP detour dialer")
    ok("urltest" not in [o.get("type") for o in cfgc["outbounds"]], "chain 模式无 urltest")
finally:
    _os.chdir(_orig_cwd)
    for p in _tmpdir.glob("*"):
        p.unlink()
    _tmpdir.rmdir()
    for k in ("PIN_NODE", "POOL_FILE", "PROXY_URL", "PROXY_CHAIN_URL"):
        _os.environ.pop(k, None)

# ---- 日志里的账号身份（库是公开的，续期日志也是公开的）----
import re as _re
_src = (ROOT / "app.py").read_text(encoding="utf-8")
_raw = [l.strip() for l in _src.splitlines() if _re.search(r'print\(f"[^"]*\{email\}', l)]
ok(not _raw, "续期日志不再直接打印邮箱原文（以后漏网的写法会被这条钉住）：" + str(_raw))
# mask_email 的新形状（只留本地名两头）必须能活着走过 app 顶层的 stdout 过滤器：
# 旧形状 so****27@example.com 会被 MAIL_RE 从 "27@example.com" 咬住 -> 日志里成了
# so*******@***.***，掩码等于白做，域名也照样发给 api.day.app。
_masked = app.mask_email("some_user_9527@example.com")
ok(_masked == "so****27", "掩码形状 = so****27（无 @、无域名）")
ok(app._SanitizeFilter.MAIL_RE.sub("***@***.***", _masked) == _masked,
   "掩码形状不会被过滤器二次改写")
ok(all(s not in app.wash("失败于 some_user_9527@example.com / 203.0.113.7 / panel.internal:8443/?password=hunter2")
       for s in ("some_user_9527", "example.com", "203.0.113.7", "hunter2")),
   "wash() 把发给第三方的正文里的地址/IP/密码全洗掉")
# wash() 的五条规则必须和日志过滤器完全一致 —— 否则「日志里看不到」不等于「推送里也看不到」。
from io import StringIO as _SI
_through = _SI()
_dirty = '登录 some_user_9527@example.com 于 203.0.113.7，参数 password=hunter2 且 "token":"abc"'
app._SanitizeFilter(_through).write(_dirty)
ok(_through.getvalue() == app.wash(_dirty),
   "wash() 与 stdout 过滤器对同一段文本产出完全相同的结果（共用那五条正则，不是另起一份）")

print("\n✅ PIN_NODE / PROXY_CHAIN_URL 通过 (8 项)")
print("\n✅✅ 全部测试通过 (15 + 10 + 6 + 12 + 9 + 8 + 15 + 8 + 5 = 88/88)")
