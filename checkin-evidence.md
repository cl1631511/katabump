#########################
PT 每日签到（attendance.php）
#########################
🔗 挂载代理: http://***.***.***.***:8080
<长串已打码>
🎬 audiences.me
<长串已打码>
── 节点尝试 1/1 ──
✅ 已注入 Turnstile attachShadow CDP 钩子
📍  当前出口IP: ***.***.***.***
🍪 首次请求前 写入成功 5/5: c_secure_login, c_secure_pass, c_secure_ssl, c_secure_tracker_ssl, c_secure_uid｜不注入 CF 凭证: cf_clearance
✅ 页面就绪（1s）: Audiences :: 签到 - Powered by NexusPHP
🔎 首枪后页面特征: 我的空间/退出链接=1 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=0 CF组件=1 密码框=0 正文长度=819
🧩 处理签到页 Turnstile...
🧩 第 1 次尝试过验证...
⚠️ 定位不到 Turnstile 复选框（iframe 读不到矩形）
🧩 第 2 次尝试过验证...
❌ 点过两次仍没有 token
🧾 audiences 措辞线索: 获得/奖励/连续/爆米花/签到/验证（正文 819 字）
ℹ️  audiences 签到状态: verify_fail | Turnstile 未签发 token
❌ 🎬 audiences.me 人机验证未通过：Turnstile 未签发 token
<长串已打码>
<长串已打码>
── 节点尝试 1/1 ──
✅ 已注入 Turnstile attachShadow CDP 钩子
📍  当前出口IP: ***.***.***.***
🍪 首次请求前 写入成功 1/1: c_secure_pass
✅ 页面就绪（1s）: xloli :: 签到 - Powered by NexusPHP
🔎 首枪后页面特征: 我的空间/退出链接=2 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=1 CF组件=1 密码框=0 正文长度=504
🧩 处理签到页 Turnstile...
🧩 第 1 次尝试过验证...
⚠️ 定位不到 Turnstile 复选框（iframe 读不到矩形）
🧩 第 2 次尝试过验证...
❌ 点过两次仍没有 token
🧾 mua 措辞线索: 魔力/签到/验证（正文 504 字）
ℹ️  mua 签到状态: verify_fail | Turnstile 未签发 token
❌ 🍥 mua.xloli.cc 人机验证未通过：Turnstile 未签发 token
#########################
完毕：audiences=❌ | mua=❌
#########################
ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID（或缺 requests），跳过 Telegram 推送。

- commit b8cd0c8 | run 37224382894 attempt 1 | push
- 结束(UTC) 2026-10-04 18:27:54
## git 渠道
