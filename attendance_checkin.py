#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NexusPHP 系站点每日签到（attendance.php），站点在 SITES 表里逐个加。

当前覆盖：audiences.me、mua.xloli.cc。两站机制同构 —— 「登录态 cookie + Cloudflare Turnstile」，
签到动作就是把 token 交回 attendance.php：
  - audiences：表单只有 widget，widget 的 data-callback=cfCallback 自动 submit；
  - mua      ：表单带「立即签到」按钮，需要点它提交。
脚本对两种都走同一条路：有按钮点按钮，没按钮才 form.submit()。

复用 katabump 的现成设施，app.py 一行不改：
  - core.handle_turnstile : Cloudflare Turnstile 四策略绕过（两站用的是同一个 widget，
    判定通过所依赖的 input[name="cf-turnstile-response"] 由 Turnstile API 自动插入）。
  - core._restart_proxy / core._pool_size : 同一份 PROXY_URL secret、同一个 sing-box 出口池。
  - import core 时 app.py 顶层已装好日志脱敏过滤器，本脚本的 print 一并被遮蔽。

登录方式：注入浏览器已登录的 cookie。不走 login.php —— 那里的图形验证码在 CI 里无人可填。
"""

import os

# app.py 顶层 load_accounts() 缺 USERS_JSON 会打一行「未配置」提示；本脚本不使用续费账号。
os.environ.setdefault("USERS_JSON", "[]")

import json
import re
import sys
import time
from dataclasses import dataclass

# 浏览器/网络依赖只有真去签到或真发通知时才需要；本地 `--cookie-check` 只想验粘贴对不对，
# 机器上没装 seleniumbase/requests 也得能用。CI 上依赖已装好，永远走不到 except。
try:
    import requests
except ImportError:
    requests = None
try:
    from seleniumbase import SB
    import app as core
    _DEPS_ERROR = ""
except ImportError as e:
    SB = core = None
    _DEPS_ERROR = str(e)


@dataclass
class Site:
    key: str
    label: str
    home: str
    attend: str
    domain: str
    cookie_env: str
    require_any: tuple = ()          # 至少要具备其一才算有登录态


# NexusPHP 的登录 cookie 有两种形态，取决于站点是否开了「安全 cookie」模式：
#   普通模式  uid + passkey
#   安全模式  c_secure_uid + c_secure_pass（现在建站默认都开这个）
# 真正起认证作用的只有 pass 那一个（c_secure_uid 只是 base64 的用户 id），所以只卡 pass。
_SESSION_KEYS = ("passkey", "c_secure_pass")

SITES = (
    Site(
        key="audiences",
        label="🎬 audiences.me",
        home="https://audiences.me/index.php",
        attend="https://audiences.me/attendance.php",
        domain=".audiences.me",
        cookie_env="AUDIENCES_COOKIE",
        require_any=_SESSION_KEYS,
    ),
    Site(
        key="mua",
        label="🍥 mua.xloli.cc",
        home="https://mua.xloli.cc/index.php",
        attend="https://mua.xloli.cc/attendance.php",
        domain=".mua.xloli.cc",
        cookie_env="MUA_COOKIE",
        require_any=_SESSION_KEYS,
    ),
)

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""

# ===== 结果状态 =====
CHK_PASS = "pass"                # 本次签到成功
CHK_ALREADY = "already"          # 今日已签到（等价成功，静默）
CHK_NO_SESSION = "no_session"    # cookie 失效/被踢回登录页 → 只能人工重新复制 cookie
CHK_VERIFY_FAIL = "verify_fail"  # Turnstile 未通过
CHK_UNKNOWN = "unknown"          # 流程未跑通/读不到结果 → 宁红不绿

# 关键词严格对照 tests/fixtures/{audiences,mua}_attendance_pre_submit.html（未签到态快照）挑选：
# 「获得」「连续签到」「(粒)爆米花」「人机验证」「今日签到」在未签到页面上本来就出现，
# 用它们判成功必然假绿。成功措辞仍缺真实样本，故另有一条与措辞无关的信号：verify_pending。
_ALREADY_KW = ("已经签到", "已签到", "已經簽到", "今日已签到", "重复签到", "请勿重复打卡")
_SUCCESS_KW = ("签到成功", "簽到成功", "恭喜")
_FAIL_KW = ("验证失败", "驗證失敗", "请重新验证", "验证码错误", "请先完成验证", "签到失败")
_LOGIN_MARK = ("login.php", "signin.php")
# 拦截页特征必须比站点正文更严：mua 的表单标签本身就写着「安全验证」，
# 把它当拦截特征会把正常签到页判成没加载完。
_BLOCKED_MARK = ("just a moment", "checking your browser", "cf-chl",
                 "安全检测能力由雷池waf驱动", "雷池waf", "attention required!")


def notify(lines, alert):
    """一屏汇总所有站点；alert=True 表示其中有真问题。"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID or requests is None:
        print("ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID（或缺 requests），跳过 Telegram 推送。")
        return
    ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))
    head = "⚠️ 签到异常" if alert else "✅ 签到成功"
    text = f"🎫 PT 每日签到\n\n{head}\n" + "\n".join(lines) + f"\n⏱️ 时间: {ts}"
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT_ID, "text": text}, timeout=10)
        print("📩 Telegram 通知已发送" if r.status_code == 200 else f"⚠️ TG 发送失败: {r.text}")
    except Exception as e:
        print(f"⚠️ TG 发送异常: {e}")


_COOKIE_LABEL = re.compile(r"^\s*(set-)?cookie\s*:\s*", re.I)


def parse_cookie_header(raw):
    """把浏览器里复制出来的 cookie 解析成 [(name, value)]，容忍三种常见粘法：
      1. DevTools Network 请求头那一整行的值：  "a=1; b=2"
      2. 连 "Cookie:" 标签一起选了：            "Cookie: a=1; b=2"
      3. Application → Cookies 网格逐行复制：   "a\\t1\\nb\\t2"
    另外兼容 JSON（Playwright 的 cookies_xxx.json 那种 [{name,value},...]）。"""
    raw = (raw or "").strip()
    if not raw:
        return []
    if raw[0] in "[{":
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            out = []
            for c in data:
                if isinstance(c, dict) and c.get("name"):
                    out.append((c["name"], str(c.get("value", ""))))
            return out
        except Exception:
            return []  # 不是合法 JSON：宁可当没配，也别把半截字符串当 cookie 注入
    raw = _COOKIE_LABEL.sub("", raw)
    pairs = []
    for part in re.split(r"[;\r\n]+", raw):
        part = part.strip()
        if not part:
            continue
        name, sep, value = part.partition("=")
        if not sep:
            name, sep, value = part.partition("\t")
        if sep and name.strip() and value.strip():
            pairs.append((name.strip(), value.strip()))
    return pairs


def session_hint(site):
    return "、".join(site.require_any) + "（至少有一个）"


def session_ok(pairs, site):
    """cookie 里有没有可用登录态。cf_clearance/PHPSESSID 之类单独存在不算。"""
    names = {n.lower() for n, _ in pairs}
    if site.require_any and not any(k in names for k in site.require_any):
        return False
    return bool(names)


def classify_attendance(page_text, url="", verify_pending=None):
    """把签到后的页面文本判成 CHK_*。纯函数，可单测。

    verify_pending=True  表示「验证入口」（widget / 签到按钮）仍在页上（还没签到）；
    verify_pending=False 表示调用方确认入口已消失 —— 站点只在未签到时才渲染它，
                         因此这是与中文措辞无关的成功信号（措辞我们还没有真实样本，不能靠猜）。
    verify_pending=None  表示调用方没查，不参与判定。
    """
    low_url = (url or "").lower()
    text = (page_text or "").strip()
    low = text.lower()

    if any(m in low_url for m in _LOGIN_MARK):
        return CHK_NO_SESSION
    if any(m in low for m in _BLOCKED_MARK):
        # 仍停在 CF/雷池 拦截页：没看到真实结果，不能报绿
        return CHK_UNKNOWN
    if any(k in text for k in _FAIL_KW):
        return CHK_VERIFY_FAIL
    if any(k in text for k in _ALREADY_KW):
        return CHK_ALREADY
    if any(k in text for k in _SUCCESS_KW):
        return CHK_PASS
    if verify_pending is False:
        return CHK_PASS
    return CHK_UNKNOWN


# ===== 页面注入脚本 =====
_BODY_TEXT_JS = "return document.body ? document.body.innerText : '';"

_LOGGED_IN_JS = """
(function(){
    var as = document.querySelectorAll('a');
    for (var i = 0; i < as.length; i++) {
        var h = as[i].href || '';
        if (h.indexOf('userdetails.php') > -1 || h.indexOf('logout.php') > -1) return true;
    }
    return false;
})()
"""

# 「还要去验证」的证据优先级：widget 元素 > 指向 attendance 的提交按钮 > 页面文案。
# 文案（安全验证/立即签到）在签到后的记录页可能仍作为标题残留，所以只在前两者都查不到时兜底，
# 且要求它出现在 attendance 表单还在的页面上 —— 宁可判不出，不可报假绿。
_VERIFY_CARD_JS = """
(function(){
    if (document.querySelector('.cf-turnstile, input[name="cf-turnstile-response"]')) return true;
    var f = document.getElementById('attendance-form') || document.querySelector('form[action*="attendance"]');
    if (f && f.querySelector('input[type="submit"], button[type="submit"]')) return true;
    var b = document.body ? document.body.innerText : '';
    if (f && (b.indexOf('人机验证') > -1 || b.indexOf('安全验证') > -1 || b.indexOf('立即签到') > -1)) return true;
    return false;
})()
"""

# audiences 的 widget 靠 data-callback 自动提交；mua 有真实按钮 —— 有按钮就点按钮。
_SUBMIT_JS = """
(function(){
    var t = document.querySelector('input[name="cf-turnstile-response"]');
    if (!t || !t.value || t.value.length < 20) return 'no-token';
    var f = document.getElementById('attendance-form') || document.querySelector('form[action*="attendance"]');
    if (!f) return 'no-form';
    var hidden = document.getElementById('cf-token');
    if (hidden) hidden.value = t.value;
    var btn = f.querySelector('input[type="submit"], button[type="submit"]');
    if (btn) { btn.click(); return 'clicked'; }
    f.submit();
    return 'submitted';
})()
"""


def _body_text(sb):
    try:
        return sb.execute_script(_BODY_TEXT_JS) or ""
    except Exception:
        return ""


def _chrome_error(url):
    low = (url or "").lower()
    return "chrome-error" in low or "chromewebdata" in low


def _verify_pending(sb):
    """签到页是否还挂着验证入口。正文过短（没渲染完/被拦截）时一律返回 True。"""
    if len(_body_text(sb)) < 200:
        return True
    try:
        return bool(sb.execute_script(_VERIFY_CARD_JS))
    except Exception:
        return True


def _navigate(sb, url, wait_s=25):
    """导航并等 CF/雷池 拦截页自行放行，返回 (url, body_text)；chrome-error 时返回 (url, '')。"""
    try:
        sb.uc_open_with_reconnect(url, reconnect_time=6)
    except Exception as e:
        print(f"⚠️ 导航异常: {e}")
    for i in range(wait_s):
        cur = sb.get_current_url() or ""
        if _chrome_error(cur):
            return cur, ""
        text = _body_text(sb)
        if text and not any(m in text.lower() for m in _BLOCKED_MARK):
            print(f"✅ 页面就绪（{i + 1}s）: {(sb.get_title() or '')[:40]}")
            return cur, text
        if i in (0, 9, 19):
            print(f"  ⏳ 等待 CF/雷池 放行... ({i + 1}s)")
        time.sleep(1)
    return (sb.get_current_url() or ""), _body_text(sb)


def _inject_cookies(sb, pairs, site):
    for name, value in pairs:
        try:
            sb.set_cookie(name, value, domain=site.domain, path="/")
        except Exception as e:
            print(f"  ⚠️ cookie {name} 注入失败: {e}")
    print(f"🍪 已注入 {len(pairs)} 个 cookie: {', '.join(n for n, _ in pairs)}")


def _read_token(sb):
    try:
        v = sb.execute_script(
            "var i=document.querySelector('input[name=\"cf-turnstile-response\"]');"
            "return i && i.value ? i.value : '';") or ""
        return v if len(v) > 20 else ""
    except Exception:
        return ""


def _solve_turnstile(sb):
    """等 token；必要时调用 katabump 的 Turnstile 绕过。返回 token 字符串或 ''。"""
    for i in range(10):
        if core._turnstile_token_ok(sb):
            print(f"✅ Turnstile 已静默签发 token（{i + 1}s）")
            return _read_token(sb)
        if core._turnstile_present(sb):
            print(f"✅ 检测到 Turnstile widget（{i + 1}s）")
            break
        time.sleep(1)
    if not core._turnstile_token_ok(sb):
        if not core.handle_turnstile(sb):
            print("❌ Turnstile 未通过")
            return ""
    for _ in range(6):
        if core._turnstile_token_ok(sb):
            break
        time.sleep(1)
    return _read_token(sb)


def _first_result_line(body):
    """取页面里第一条像结果的短行，供 TG 详情/日志用。"""
    skip = ("每日签到", "签到奖励规则", "连续签到加成", "签到 - Powered", "魔力加成")
    for line in (body or "").splitlines():
        t = line.strip()
        if not t or len(t) > 80:
            continue
        if any(s in t for s in skip):
            continue
        if any(k in t for k in _SUCCESS_KW + _ALREADY_KW + _FAIL_KW):
            return t
    return ""


def _dump_evidence(site, body):
    """关键词没命中时把页面文本留成 artifact，供校准 _SUCCESS_KW/_FAIL_KW。"""
    try:
        with open(f"attendance_result_{site.key}.txt", "w", encoding="utf-8") as f:
            f.write(body or "(空)")
    except Exception:
        pass


def checkin(sb_kwargs, site, pairs):
    """单站点单趟流程。返回 (status, detail)。"""
    try:
        with SB(**sb_kwargs) as sb:
            def shot(tag):
                try:
                    sb.save_screenshot(f"attendance_{site.key}_{tag}.png")
                except Exception:
                    pass

            core._install_turnstile_hook_cdp(sb)
            try:
                sb.open("https://ipv4.icanhazip.com")
                ip_text = (sb.get_text("body") or "").strip()
                print(f"📍  当前出口IP: {ip_text}")
                if core._egress_unusable(ip_text):
                    return (CHK_UNKNOWN, "出口探测失败")
            except Exception:
                pass

            # 先建域再写 cookie：Selenium 只允许给当前页面所属域设 cookie
            url, _ = _navigate(sb, site.home)
            if _chrome_error(url):
                return (CHK_UNKNOWN, "首页 chrome-error（出口不可用）")
            _inject_cookies(sb, pairs, site)

            url, text = _navigate(sb, site.attend)
            if _chrome_error(url):
                return (CHK_UNKNOWN, "签到页 chrome-error（出口不可用）")
            st = classify_attendance(text, url)
            if st == CHK_NO_SESSION:
                return (CHK_NO_SESSION, "被重定向到登录页，cookie 已失效")
            try:
                logged_in = bool(sb.execute_script(_LOGGED_IN_JS))
            except Exception:
                logged_in = False
            if not logged_in:
                return (CHK_NO_SESSION, "注入 cookie 后仍未登录（登录 cookie 无效或已过期）")
            pending = _verify_pending(sb)
            if st in (CHK_PASS, CHK_ALREADY):
                shot("result")
                _dump_evidence(site, text)
                print("ℹ️ 页面已显示签到结果，跳过提交")
                return (st, _first_result_line(text) or "签到页已反映结果")
            if not pending:
                # 验证入口不在 = 站点认为今天已签（措辞未知，入口存在与否是唯一可靠信号）
                shot("result")
                _dump_evidence(site, text)
                return (CHK_PASS, "签到页已无验证入口，判定今日已签到")

            print("🧩 处理签到页 Turnstile...")
            token = _solve_turnstile(sb)
            if not token:
                shot("turnstile_fail")
                _dump_evidence(site, _body_text(sb))
                return (CHK_VERIFY_FAIL, "Turnstile 未签发 token")

            # widget 的回调可能已自动提交；入口还在则手动补一次
            time.sleep(2)
            if _verify_pending(sb):
                try:
                    print(f"📨 提交签到表单: {sb.execute_script(_SUBMIT_JS)}")
                except Exception as e:
                    print(f"⚠️ 提交异常: {e}")

            for i in range(20):
                time.sleep(1)
                cur = sb.get_current_url() or ""
                if _chrome_error(cur):
                    shot("result")
                    return (CHK_UNKNOWN, "提交后 chrome-error")
                body = _body_text(sb)
                # 提交后验证入口消失即成功；入口还在时不能报绿（防假绿）
                still = cur.split("?")[0].rstrip("/") == site.attend.rstrip("/")
                vp = _verify_pending(sb) if still else False
                st = classify_attendance(body, cur, vp)
                if st != CHK_UNKNOWN:
                    shot("result")
                    _dump_evidence(site, body)
                    return (st, _first_result_line(body))
            shot("result")
            _dump_evidence(site, _body_text(sb))
            return (CHK_UNKNOWN, "提交后 20s 内未读到明确结果")
    except Exception as e:
        print(f"\n❌ 处理异常: {e}")
        return (CHK_UNKNOWN, f"处理异常: {e}")


def run_site(sb_kwargs, site):
    raw = os.environ.get(site.cookie_env, "")
    pairs = parse_cookie_header(raw)
    if not pairs:
        # 只报长度和格式线索，绝不打印 cookie 内容（CI 日志是公开的）
        if not raw.strip():
            return (CHK_NO_SESSION, f"{site.cookie_env} 未配置或为空")
        hint = ("看起来是 JSON 但解析失败" if raw.lstrip()[0] in "[{" else "没有一组形如 name=value")
        return (CHK_NO_SESSION,
                f"{site.cookie_env} 长度 {len(raw)}，{hint}；"
                "要的是 DevTools Network 里请求头 Cookie: 后面那一整行（a=1; b=2）")
    if not session_ok(pairs, site):
        return (CHK_NO_SESSION,
                f"{site.cookie_env} 缺少登录 cookie，需要 {session_hint(site)}；"
                f"现有: {', '.join(n for n, _ in pairs)}")

    if core is None:
        return (CHK_UNKNOWN, f"浏览器依赖缺失，无法签到: {_DEPS_ERROR}（本地只想验 cookie 请用 --cookie-check）")

    pool_n = core._pool_size()
    try:
        max_attempts = int(os.environ.get("NODE_ATTEMPTS", "0") or "0")
    except ValueError:
        max_attempts = 0
    if max_attempts <= 0:
        max_attempts = min(5, pool_n) if pool_n else 1

    status, detail = CHK_UNKNOWN, ""
    for attempt in range(1, max_attempts + 1):
        print(f"\n  ── 节点尝试 {attempt}/{max_attempts} ──")
        if pool_n:
            core._restart_proxy(pin=attempt)
        elif attempt > 1:
            core._restart_proxy()
        status, detail = checkin(sb_kwargs, site, pairs)
        print(f"ℹ️  {site.key} 签到状态: {status} | {detail}")
        if status in (CHK_PASS, CHK_ALREADY):
            break
        if status == CHK_NO_SESSION:
            # 换出口救不回登录态，停止重试并给出可操作提示
            detail = (detail or "cookie 失效") + f"；请重新复制 Cookie 并更新 {site.cookie_env}"
            break
    return (status, detail)


_STATUS_LINE = {
    CHK_PASS: ("✅", "签到成功"),
    CHK_ALREADY: ("⏳", "今日已签到"),
    CHK_NO_SESSION: ("❌", "登录态失效"),
    CHK_VERIFY_FAIL: ("❌", "人机验证未通过"),
    CHK_UNKNOWN: ("❌", "流程未跑通，需查看"),
}
_ALERT = (CHK_NO_SESSION, CHK_VERIFY_FAIL, CHK_UNKNOWN)


def main():
    print("#" * 25)
    print("   PT 每日签到（attendance.php）")
    print("#" * 25)

    wanted = [s.strip().lower() for s in os.environ.get("CHECKIN_SITES", "").split(",") if s.strip()]
    sites = [s for s in SITES if not wanted or s.key in wanted]
    if not sites:
        print(f"❌ CHECKIN_SITES={wanted} 没有匹配到站点，可用: {[s.key for s in SITES]}")
        raise SystemExit(1)

    if "--cookie-check" in sys.argv:
        # 本地自检：只验「粘进去的字符串能不能解析出登录字段」，不开浏览器、不打码值
        for site in sites:
            raw = os.environ.get(site.cookie_env, "")
            pairs = parse_cookie_header(raw)
            verdict = "✅ 可用于签到" if session_ok(pairs, site) else "❌ 判为无登录态"
            print(f"{site.key}: {verdict}（需要 {session_hint(site)}；"
                  f"解析出 {len(pairs)} 项：{', '.join(n for n, _ in pairs) or '无'}）")
        raise SystemExit(0)

    IS_PROXY = os.environ.get("IS_PROXY", "false").lower() == "true"
    proxy_str = os.environ.get("PROXY_SERVER", "").strip() or "http://127.0.0.1:8080"
    sb_kwargs = {"uc": True, "headless": False}
    if IS_PROXY:
        print(f"🔗 挂载代理: {proxy_str}")
        sb_kwargs["proxy"] = proxy_str
    else:
        print("🌐 未使用代理，直连访问")

    lines, alert, quiet = [], False, True
    for site in sites:
        print("\n" + "=" * 25)
        print(f"  {site.label}")
        print("=" * 25)
        status, detail = run_site(sb_kwargs, site)
        icon, text = _STATUS_LINE[status]
        # 公开仓库的 CI 日志也是公开的：成功态不带页面原文，失败态才带（原文里可能有账号名）
        line = f"{icon} {site.label} {text}" + (f"：{detail}" if detail and status in _ALERT else "")
        print(line)   # 无论有没有配 TG，日志里都得看得到原因
        lines.append(line)
        if status in _ALERT:
            alert = True
        if status != CHK_ALREADY:
            quiet = False
        if status == CHK_UNKNOWN:
            print(f"📄 未命中关键词时的页面文本见 artifact: attendance_result_{site.key}.txt")

    print("\n" + "#" * 25)
    print("  完毕：" + " | ".join(f"{s.key}={l.split(' ', 1)[0]}" for s, l in zip(sites, lines)))
    print("#" * 25)
    if alert or not quiet:
        notify(lines, alert)
    else:
        print("⏳ 全部站点今日已签到，静默。")
    if alert:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
