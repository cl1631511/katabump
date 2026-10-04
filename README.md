# Katabump Server Auto-Renewal Tool

基于[XCQ0607/katabump](https://github.com/XCQ0607/katabump)优化：增加singbox全协议代理、随机时间签到、**ALTCHA验证码自动绕过**

### 重要提醒：提示 未找到"See" 按钮...说明代理ip质量有问题，请按要求添加、更换

## 🚀 GitHub Actions 云端运行 (推荐)

这是最省心的方式，配置一次即可每天自动执行。

1. **Fork 本仓库** 到你的 GitHub 账号。
2. 进入你的仓库，点击 **Settings** -> **Secrets and variables** -> **Actions**。
3. 点击 **New repository secret**，添加一个名为 `USERS_JSON` 的 Secret。
4. **Value** 的格式必须是 JSON 数组（请尽量压缩为一行）：
   ```json
   [{"username": "your_email@example.com", "password": "your_password"}, {"username": "another@example.com", "password": "pwd"}]
   ```
5. **(可选) 配置代理**:

  支持两种代理方式：

  **全协议代理 (推荐)**
  添加名为 `PROXY_URL` 的 Secret，支持 vmess、vless、hy2、tuic、socks5 等所有主流协议。
  脚本会自动下载 sing-box 并在本地启动 HTTP 代理，无需手动配置。
  - **格式示例**:
    - vmess: `vmess://base64EncodedJSON`
    - vless: `vless://uuid@host:port?security=tls&type=ws&...#name`
    - hy2: `hy2://password@host:port?sni=xxx`
    - socks5: `socks5://user:pass@host:port`

6. **(可选) Telegram 消息推送**:
   如果你希望在续期成功、失败或跳过时收到 Telegram 通知（包含截图），请配置以下 Secret：
   - `TG_BOT_TOKEN`: 你的 Telegram Bot Token (从 @BotFather 获取)。
   - `TG_CHAT_ID`: 你的 Chat ID (用户 ID 或群组 ID)。
   > 如果未配置，脚本将跳过发送通知。

### 4. 运行结果与截图

- **运行日志**: 在 Actions 中的 `Run Renew Script` 步骤查看。
- **截图留存**: 每次运行（无论成功与否），通过 `Upload Screenshots` 步骤自动上传截图。
  - 你可以在 Workflow 运行详情页的 **Artifacts** 区域下载 `screenshots` 压缩包。
  - 每个账号对应一张截图（`username.png`），方便确认状态。

5. 保存后，进入 **Actions** 页面，启用 Workflow。它会在**每天北京时间 08:00 (UTC 00:00)** 自动运行。
6. 你也可以手动点击 "Run workflow" 立即测试。
7. **随机延迟**: 定时任务触发时，脚本会随机延迟 0-3 小时后执行，防止被目标站识别为自动化。手动触发时不会有延迟，立即执行。

---

## 🎫 PT 每日签到 (`attendance_checkin.py`)

已接入站点：**audiences.me**、**mua.xloli.cc**（都在 `attendance.php`）。两站机制同构 ——
「登录态 cookie + Cloudflare Turnstile」，签到就是把 token 交回表单，没有别的动作。
本仓库已有 Turnstile 绕过和 sing-box 出口池，签到直接复用，`app.py` 未改动。

1. **取 Cookie**（一次即可，失效再换）：浏览器登录该站 → F12 → **Network** → 刷新
   `attendance.php` → 点该请求 → **Request Headers** 里的整条 `Cookie` 值复制出来。
2. **加 Secret**：Settings → Secrets and variables → Actions，一站一个：
   - `AUDIENCES_COOKIE`、`MUA_COOKIE` —— 整条 `Cookie` 头原样贴进去即可，脚本只检查
     里面有没有登录字段：NexusPHP 的「安全 cookie」模式是 `c_secure_pass`（配合 `c_secure_uid`），
     老模式是 `passkey`（配合 `uid`）；有 pass 那一个就算有登录态。
   ```
   c_secure_uid=ZmFrZVVpZA...; c_secure_pass=...; c_secure_login=...; cf_clearance=...
   ```
   `cf_clearance` 可不带 —— 它是 IP/UA 绑定的，CI 出口和浏览器不一样，过期了浏览器会自己重新过 CF。
   缺哪个站 secret 就只有那个站报红，另一站照签。
3. **Workflow**：`.github/workflows/attendance.yml`，每天北京时间 09:17 逐站串行跑，
   与续期共用 `PROXY_URL` / `PROXY_CHAIN_URL` / `TG_BOT_TOKEN` / `TG_CHAT_ID`。
   手动触发：Actions → PT Attendance Check-in → Run workflow；只想跑一站就在 step env 加
   `CHECKIN_SITES: "mua"`。
4. **判定规则**：签到成功 ✅ 通知；今日已签 ⏳ 静默；cookie 失效 / 人机验证没过 / 流程没跑通
   → ❌ 告警 + CI 红灯。TG 一条消息汇总所有站点。结果页措辞未知时会把页面文本存成 artifact
   `attendance-evidence`（`attendance_result_<站点>.txt` + `attendance_<站点>_*.png`），据此再收紧关键词。
5. **加新站点**：在 `attendance_checkin.py` 的 `SITES` 表里加一条（key/域名/cookie 环境变量名/
   必需的登录 cookie 字段），再配同名 secret。表单结构两种都认：有提交按钮就点按钮
   （mua），没按钮靠 widget 回调自动提交（audiences）。
6. **本地调试**（PowerShell）：先只验 cookie 粘得对不对（不开浏览器、不打印码值），再真跑
   ```powershell
   $env:AUDIENCES_COOKIE="c_secure_uid=...; c_secure_pass=..."
   $env:MUA_COOKIE="c_secure_pass=..."
   python attendance_checkin.py --cookie-check
   python attendance_checkin.py
   ```
7. **回归测试**（不需要浏览器/网络）：
   ```powershell
   python tests/test_attendance_classify.py
   python tests/test_attendance_flow.py
   ```

> 仓库是公开的：新加站点快照后**必须先洗掉个人信息**再提交——
> `python tests/scrub_fixture.py tests/fixtures/<新快照>.html`
> 它会把账号名、userdetails id/uuid、邀请 id、流量/积分/排名等替换成占位值，并校验签到判定依赖的结构标记没被洗坏。

> 启用后建议把 PT-Checkin 里对应的 `audiences` / `mua` 站点关掉，避免两边同一天重复抢签到。

---

## 💻 Windows 本地运行指南

如果你想在本地观察运行过程或进行调试，请按以下步骤操作。

### 1. 环境准备

确保你已经安装了 [Node.js](https://nodejs.org/) (建议版本 v18+)。

### 2. 安装依赖

在项目根目录打开终端 (PowerShell 或 CMD)，运行：

```bash
npm install
```

### 3. 配置账号

项目中有一个 `login.json.template` 模板文件。

1. 将其**重命名**为 `login.json`。
2. 用记事本或编辑器打开，填入你的账号密码：
   ```json
   [
       {
           "username": "myemail@gmail.com",
           "password": "mypassword123"
       }
   ]
   ```

   > **注意**: `login.json` 已被加入 `.gitignore`，不会被上传到 GitHub，请放心使用。
   >

### 4. 配置 Chrome 路径

打开 `renew.js` 文件，找到第 11-12 行：

```javascript
const CHROME_PATH = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const USER_DATA_DIR = path.join(__dirname, 'ChromeData_Katabump');
const HEADLESS = true;
```

* **CHROME_PATH**: 这是你本地 Chrome 浏览器的安装路径。如果你的安装位置不同，请务必修改！
* **USER_DATA_DIR**:
  * 这是一个用于存放 Script 运行时产生的浏览器数据（缓存、Cookie、登录状态等）的文件夹。
  * **作用**: 它能让你的登录状态保持更久，不需要每次运行都重新输入密码。
  * **能不能删？**: **可以删**。如果你想要重置所有状态（彻底清除缓存），只需删除这个文件夹即可。脚本下次运行时会自动重新创建它。
* **HEADLESS**:
  * `false`: 脚本运行时会弹出一个 Chrome 窗口，你可以看到它在做什么。
  * `true`: (默认)脚本在后台无头运行，界面不可见（适合只想静默完成任务时开启）。

### 3. 运行脚本

如果你需要使用代理运行脚本，请设置环境变量 `HTTP_PROXY`：

**Powershell:**
```powershell
$env:HTTP_PROXY="http://user:pass@127.0.0.1:7890"
node renew.js
```

**CMD:**
```cmd
set HTTP_PROXY=http://user:pass@127.0.0.1:7890
node renew.js
```

如果不设置代理，直接运行：
```bash
node renew.js
```

脚本会自动启动 Chrome (如果需要)，逐个处理账号，并在根目录下的 `photo/` 文件夹中保存每个账号运行结束时的截图（`账号名.png`）。窗口（默认无头模式为 false，你可以看到操作过程），并依次为列表中的用户续期。

---

## 🛠️ 项目结构

* `renew.js`: Windows 本地运行的主程序。
* `action_renew.js`: 专门用于 GitHub Actions 环境的脚本（适配 Linux/Headless），支持随机延迟和 sing-box 代理。
* `proxy_handler.py`: 代理协议解析器，将 vmess/vless/hy2/tuic/socks5 等协议转换为 sing-box 配置。
* `attendance_checkin.py`: PT 每日签到（audiences.me / mua.xloli.cc，复用 app.py 的 Turnstile 绕过与代理池）。
* `.github/workflows/attendance.yml`: 签到的定时任务。
* `tests/fixtures/*_attendance_pre_submit.html`: 各站未签到态页面快照，防假绿的回归测试素材。
* `tests/scrub_fixture.py`: 把新快照里的账号标识洗成占位值（公开仓库提交前必跑）。
* `.github/workflows/renew.yml`: GitHub Actions 的定时任务配置文件。
* `login.json`: (需手动创建) 存放本地运行的账号信息。
