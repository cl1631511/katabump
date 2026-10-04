#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 saved 页面快照里的个人标识洗掉 —— 仓库是公开的，fixture 只能留结构，不能留账号。

用法（在项目根目录）：
    python tests/scrub_fixture.py tests/fixtures/xxx_attendance_pre_submit.html [...]

三步：
  1. 从页面上收集「个人数据原文」（账号名、userdetails id/uuid、邀请 id、等级徽章、
     流量/分享率/魔力值/排名/短讯等数值）；
  2. 先按结构规则替换，再把收集到的名字与长 id 逐字面全局替换（不再依赖上下文）；
  3. 复核结构标记还在（签到判定和回归测试靠它们），并重新收集一遍确认无残留，否则不写入。
"""
import re
import sys
from pathlib import Path

USER_PLACEHOLDER = "exampleuser"
ID_PLACEHOLDER = "100001"
UUID_PLACEHOLDER = "00000000-0000-4000-8000-000000000000"

REQUIRED_ALL = ("cf-turnstile", "userdetails.php", "attendance.php", "challenges.cloudflare.com")
REQUIRED_ANY = ("人机验证", "安全验证", "立即签到")

# 捕获组即「原文」，既用于收集，也用于洗完后重新收集复核
SECRET_PATTERNS = (
    r"class='User_Name'><b>([^<]{2,40})</b>",
    r'title="([^"]{2,40})"\s+data-uploader-avatar',
    r'data-uploader-label="([^"]{2,40})"',
    r"userdetails\.php\?id=(\d{3,})",
    r"userdetails\.php\?uuid=([0-9a-fA-F-]{8,})",
    r"invite\.php\?id=(\d{3,})",
    r"UID (\d{3,})",
    r"([\d][\d.,]*\s*(?:GB|MB|KB|TB))",
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?)",
    r"\b(\d+\.\d{3})\b",
    r"↑ (\d+) / ↓ (\d+)",
    r"(\d+) \(\d+ 新\)",
    r"发件箱 (\d{1,6})",
    r"</a>\]: (\d+\(\d+\))",
    r'trans\.gif" ?/?>\s*(\d{1,6})',
    r'data-uploader-badge="([^"]{1,40})"',
)

RULES = [
    (r"(userdetails\.php\?id=)\d{3,}", r"\g<1>" + ID_PLACEHOLDER, "userdetails id"),
    (r"(userdetails\.php\?uuid=)[0-9a-fA-F-]{8,}", r"\g<1>" + UUID_PLACEHOLDER, "userdetails uuid"),
    (r"(invite\.php\?id=)\d{3,}", r"\g<1>" + ID_PLACEHOLDER, "invite id"),
    (r"(UID )\d{3,}", r"\g<1>" + ID_PLACEHOLDER, "正文里的 UID"),
    (r"[\d][\d.,]*\s*(?:GB|MB|KB|TB)\b", "0.00 GB", "上传/下载量"),
    (r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", "0", "千分位数值（魔力值/积分）"),
    (r"\b\d+\.\d{3}\b", "0.000", "分享率等三位小数"),
    (r"(↑ )\d+( / ↓ )\d+", "↑ 0 / ↓ 0", "排名"),
    (r"\d+ \(\d+ 新\)", "0 (0 新)", "收件箱"),
    (r"(发件箱 )\d+", "发件箱 0", "发件箱数"),
    (r"(</a>\]: )\d+\(\d+\)", "</a>]: 0(0)", "邀请数"),
    (r'(trans\.gif" ?/?>\s*)\d{1,6}', r"\g<1>0", "做种/下载数"),
    (r'data-uploader-badge="[^"]*"', 'data-uploader-badge=""', "等级徽章"),
]


def collect_secrets(html):
    out = set()
    for pat in SECRET_PATTERNS:
        for m in re.findall(pat, html):
            if isinstance(m, tuple):
                out.update(x.strip() for x in m if x.strip())
            elif m.strip():
                out.add(m.strip())
    known_clean = {USER_PLACEHOLDER, ID_PLACEHOLDER, UUID_PLACEHOLDER, "0", "0.000", "0.00 GB",
                   "0 (0 新)", "0(0)", "UID " + ID_PLACEHOLDER, ""}
    return {s for s in out if s not in known_clean}


def placeholder_for(secret):
    """按原文长相选占位值：uuid → 假 uuid；带单位/千分位的数值 → 归零；纯长数字 → 假 id；其余 → 假账号名。"""
    if re.fullmatch(r"[0-9a-fA-F-]{8,}", secret) and re.search(r"[a-fA-F]", secret):
        return UUID_PLACEHOLDER
    if re.fullmatch(r"[\d.,]+\s*(?:GB|MB|KB|TB)", secret):
        return "0.00 GB"
    if re.fullmatch(r"\d+\.\d{3}", secret):
        return "0.000"
    if re.fullmatch(r"[0-9(./\s]+", secret):
        return ID_PLACEHOLDER if len(re.sub(r"\D", "", secret) or "") >= 4 else "0"
    if re.fullmatch(r"\d[\d.,]*", secret):
        return "0"
    return USER_PLACEHOLDER


def worth_verifying(secret):
    """太短的纯数字（如做种数 3）在页面上到处都是，逐字复核只会误报。"""
    return bool(re.search(r"[A-Za-z]", secret)) or len(secret) >= 4


def scrub(path):
    original = Path(path).read_text(encoding="utf-8")
    secrets = collect_secrets(original)
    html = original
    hits = []
    for pat, rep, label in RULES:
        html, n = re.subn(pat, rep, html)
        if n:
            hits.append(f"{label}×{n}")

    # 规则漏网的原文：不再依赖上下文，逐字面全局替换（长者优先，避免洗出半截）
    for s in sorted((x for x in secrets if worth_verifying(x)), key=len, reverse=True):
        rep = placeholder_for(s)
        html, n = re.subn(re.escape(s), rep, html)
        if n:
            hits.append(f"字面 {s[:18]!r}→{rep}×{n}")

    missing = [k for k in REQUIRED_ALL if k not in html]
    if missing or not any(k in html for k in REQUIRED_ANY):
        print(f"❌ {path}: 结构被洗坏了 -> 缺 {missing}；未写入")
        return False
    leftovers = sorted(s for s in secrets if worth_verifying(s) and s in html)
    if leftovers:
        print(f"❌ {path}: 仍有残留 {leftovers}；未写入")
        return False

    Path(path).write_text(html, encoding="utf-8")
    print(f"✅ {path}: 收集 {len(secrets)} 项、逐字复核 {len([s for s in secrets if worth_verifying(s)])} 项")
    print(f"   {', '.join(hits)}")
    return True


if __name__ == "__main__":
    targets = sys.argv[1:]
    if not targets:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(0 if all(scrub(p) for p in targets) else 1)
