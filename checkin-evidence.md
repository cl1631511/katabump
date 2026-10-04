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
🔎 Turnstile 结构: 视口=1280x753 滚动=0 iframe=2 其中CF=0 [audiences.me  0x0@1644][audiences.me  0x0@1644] st=0 st=0 shadow根=0 影子内CFiframe=0 CF资源=2 turnstile对象=1 容器=483,1033 300x65 容器子=DIV token长度=0
🧩 第 1 次尝试过验证...
🖱️ [CDP] 原生点击 Turnstile 复选框 (516,376)
⚠️ 页面上没有 Turnstile 组件、也没签发 token —— 不做点击尝试
🧾 audiences 措辞线索: 成功/已签到/获得/奖励/连续/爆米花/签到（正文 838 字）
ℹ️  audiences 签到状态: unknown | 签到页有入口，但 10s 内既没出现 Turnstile 组件也没拿到 token，没点任何东西不能猜结果（宁红不绿）；页面特征 我的空间/退出链接=1 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=0 CF组件=1 密码框=0 正文长度=819
❌ 🎬 audiences.me 流程未跑通，需查看：签到页有入口，但 10s 内既没出现 Turnstile 组件也没拿到 token，没点任何东西不能猜结果（宁红不绿）；页面特征 我的空间/退出链接=1 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=0 CF组件=1 密码框=0 正文长度=819
<长串已打码>
<长串已打码>
── 节点尝试 1/1 ──
✅ 已注入 Turnstile attachShadow CDP 钩子
📍  当前出口IP: ***.***.***.***
🍪 首次请求前 写入成功 1/1: c_secure_pass
✅ 页面就绪（1s）: xloli :: 签到 - Powered by NexusPHP
🔎 首枪后页面特征: 我的空间/退出链接=2 login.php 链接=0 签到表单=0 Turnstile=0 签到按钮=0 CF组件=0 密码框=0 正文长度=1037
🧾 mua 措辞线索: 成功/已签到/获得/连续/魔力/签到（正文 1037 字）
ℹ️ 页面已显示签到结果，跳过提交
ℹ️  mua 签到状态: pass | 命中措辞「签到成功」
✅ 🍥 mua.xloli.cc 签到成功
#########################
完毕：audiences=❌ | mua=✅
#########################
ℹ️ 未配置 TG_BOT_TOKEN 或 TG_CHAT_ID（或缺 requests），跳过 Telegram 推送。

- commit 7a939ab | run 37225536366 attempt 1 | push
- 结束(UTC) 2026-10-04 18:45:19
## git 渠道
