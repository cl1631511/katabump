#########################
PT 每日签到（attendance.php）
#########################
🔗 挂载代理: http://***.***.***.***:8080
<长串已打码>
🎬 audiences.me
<长串已打码>
── 节点尝试 1/4 ──
✅ 已注入 Turnstile attachShadow CDP 钩子
ℹ️ 窗口没最大化: WebDriverException
📍  当前出口IP: ***.***.***.***
🍪 首次请求前 写入成功 5/5: c_secure_login, c_secure_pass, c_secure_ssl, c_secure_tracker_ssl, c_secure_uid｜不注入 CF 凭证: cf_clearance
✅ 页面就绪（1s）: 404 Not Found
🔎 首枪后页面特征: 我的空间/退出链接=0 login.php 链接=0 签到表单=0 Turnstile=0 签到按钮=0 CF组件=0 密码框=0 正文长度=26
ℹ️  audiences 签到状态: no_session | cookie 确实随首枪发出，但站点没给出登录页：只有两种可能 —— 会话已失效，或会话绑死了复制 cookie 那台机器的出口 IP/UA。罐里有 c_secure_pass, c_secure_login, c_secure_ssl, c_secure_uid, c_secure_tracker_ssl；页面特征 我的空间/退出链接=0 login.php 链接=0 签到表单=0 Turnstile=0 签到按钮=0 CF组件=0 密码框=0 正文长度=26
❌ 🎬 audiences.me 登录态失效：cookie 确实随首枪发出，但站点没给出登录页：只有两种可能 —— 会话已失效，或会话绑死了复制 cookie 那台机器的出口 IP/UA。罐里有 c_secure_pass, c_secure_login, c_secure_ssl, c_secure_uid, c_secure_tracker_ssl；页面特征 我的空间/退出链接=0 login.php 链接=0 签到表单=0 Turnstile=0 签到按钮=0 CF组件=0 密码框=0 正文长度=26；请重新复制 Cookie 并更新 AUDIENCES_COOKIE
<长串已打码>
<长串已打码>
── 节点尝试 1/4 ──
✅ 已注入 Turnstile attachShadow CDP 钩子
ℹ️ 窗口没最大化: WebDriverException
📍  当前出口IP: ***.***.***.***
🍪 首次请求前 写入成功 1/1: c_secure_pass
✅ 页面就绪（1s）: xloli :: 签到 - Powered by NexusPHP
🔎 首枪后页面特征: 我的空间/退出链接=2 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=1 CF组件=1 密码框=0 正文长度=483
🧩 处理签到页 Turnstile...
🔎 Turnstile 结构: 视口=1280x753 滚动=0 iframe=0 其中CF=0  st=0 st=0 shadow根=0 影子内CFiframe=0 CF资源=2 turnstile对象=1 容器=518,316 300x65 容器子=DIV token长度=0
🧩 第 1 次尝试过验证...
🖱️ [CDP] 原生点击 Turnstile 复选框 (552,348)
✅ 拿到 Turnstile token（第 1 次尝试后）
📨 提交签到表单: clicked
🧾 mua 措辞线索: 成功/已签到/获得/连续/魔力/签到（正文 1090 字）
ℹ️  mua 签到状态: pass | 命中措辞「签到成功」
✅ 🍥 mua.xloli.cc 签到成功
#########################
完毕：audiences=❌ | mua=✅
#########################
📩 Bark 推送已送达

- commit 3b4fb92 | run 41131342301 attempt 1 | schedule
- 结束(UTC) 2026-10-30 21:30:38
