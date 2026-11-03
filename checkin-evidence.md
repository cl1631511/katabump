#########################
PT 每日签到（attendance.php）
#########################
🔗 挂载代理: http://***.***.***.***:8080
<长串已打码>
🎬 audiences.me
<长串已打码>
⏭️ 🎬 audiences.me 未配 cookie，已跳过：AUDIENCES_COOKIE 未配置
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
🔎 Turnstile 结构: 视口=1280x753 滚动=0 iframe=0 其中CF=0  st=0 shadow根=0 影子内CFiframe=0 CF资源=1 turnstile对象=0 容器=zero 容器子=empty token长度=-1
🧩 第 1 次尝试过验证...
⚠️ 定位不到 Turnstile 复选框（iframe 读不到矩形）
🧩 第 2 次尝试过验证...
🧩 第 3 次尝试过验证...
🧩 [API] turnstile.execute -> no-api
🔎 Turnstile 结构: 视口=1280x753 滚动=0 iframe=0 其中CF=0  st=0 shadow根=0 影子内CFiframe=0 CF资源=1 turnstile对象=0 容器=zero 容器子=empty token长度=-1
❌ 试过 3 招仍没有 token
🧾 mua 措辞线索: 魔力/签到/验证（正文 483 字）
ℹ️  mua 签到状态: unknown | 签到页有入口，但 30s 内既没出现可点的 Turnstile 组件也没拿到 token，没点任何东西不能猜结果（宁红不绿）；页面特征 我的空间/退出链接=2 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=1 CF组件=1 密码框=0 正文长度=483
── 节点尝试 2/4 ──
✅ 已注入 Turnstile attachShadow CDP 钩子
ℹ️ 窗口没最大化: WebDriverException
📍  当前出口IP: ***.***.***.***
🍪 首次请求前 写入成功 1/1: c_secure_pass
✅ 页面就绪（1s）: xloli :: 签到 - Powered by NexusPHP
🔎 首枪后页面特征: 我的空间/退出链接=2 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=1 CF组件=1 密码框=0 正文长度=483
🧩 处理签到页 Turnstile...
🔎 Turnstile 结构: 视口=1280x753 滚动=0 iframe=0 其中CF=0  st=0 st=0 shadow根=0 影子内CFiframe=0 CF资源=2 turnstile对象=1 容器=zero 容器子=DIV token长度=0
🧩 第 1 次尝试过验证...
⚠️ 定位不到 Turnstile 复选框（iframe 读不到矩形）
🧩 第 2 次尝试过验证...
🧩 第 3 次尝试过验证...
🧩 [API] turnstile.execute -> executed
🔎 Turnstile 结构: 视口=1280x753 滚动=0 iframe=0 其中CF=0  st=0 st=0 shadow根=0 影子内CFiframe=0 CF资源=2 turnstile对象=1 容器=zero 容器子=DIV token长度=0
❌ 试过 3 招仍没有 token
🧾 mua 措辞线索: 魔力/签到/验证（正文 483 字）
ℹ️  mua 签到状态: verify_fail | 试过 3 招仍没拿到 token，页面也没给出结果措辞；特征 我的空间/退出链接=2 login.php 链接=0 签到表单=1 Turnstile=1 签到按钮=1 CF组件=1 密码框=0 正文长度=483
── 节点尝试 3/4 ──
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
🧾 mua 措辞线索: 成功/已签到/获得/连续/魔力/签到（正文 1029 字）
ℹ️  mua 签到状态: pass | 命中措辞「签到成功」
✅ 🍥 mua.xloli.cc 签到成功
#########################
完毕：audiences=⏭️ | mua=✅
#########################
📩 Bark 推送已送达

- commit 7d66e73 | run 41729504479 attempt 1 | schedule
- 结束(UTC) 2026-11-03 22:21:20
