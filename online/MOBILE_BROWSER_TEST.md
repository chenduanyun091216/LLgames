# 真实 Web 构建的手机模拟测试

这份脚本用于联机战役预览的本机浏览器验收，选择首关验证基础联网流程，不是全战役通关、手机硬件或 HTML 假页面测试。当前云环境未成功打开实际游戏，不能把本脚本的存在写成浏览器测试已通过。

`online/tools/test_mobile_runtime.py` 会启动仅监听 `127.0.0.1` 的临时服务器，在同一进程环境中加载实际的 `online/build/web/`，使用两个独立的 Chromium 浏览器会话模拟触摸屏。它保留 Chromium 安全沙箱，不开放局域网或公网端口，不修改证书、防火墙、浏览器安全设置或原单机文件。

## 在电脑上运行

从项目根目录使用原联机开发环境，Python 3.12。若还未创建环境或构建，请先按 `online/README.md` 安装联机依赖并运行构建。不要修改原单机 Python 环境。

macOS / Linux：

```sh
source online/.venv/bin/activate
python -m pip install 'playwright>=1.49,<2'
python -m playwright install chromium
python -m online.tools.build_web
python -m online.tools.test_mobile_runtime
```

Windows PowerShell：

```powershell
.\online\.venv\Scripts\Activate.ps1
python -m pip install "playwright>=1.49,<2"
python -m playwright install chromium
python -m online.tools.build_web
python -m online.tools.test_mobile_runtime
```

若已经安装 Chrome，可省略 `playwright install chromium`，最后一步改用：

```sh
python -m online.tools.test_mobile_runtime --channel chrome
```

不需另开服务器，不需输入房间码。请以普通用户运行，不要用管理员/root，也不要添加 `--no-sandbox` 等降低安全性的参数。如 Linux 缺少浏览器系统依赖，请先由电脑管理员按 Playwright 官方说明检查依赖；脚本不会自动安装系统组件或更改安全设置。

## 自动覆盖

- 实际 Pygbag/WASM/Pygame 引擎加载。只在真实页面提示时触摸一次，只读检查实际渲染器就绪标记，不伪造或调用 `readyRenderer()`；加入后另行检查准备按钮。
- 两个隔离会话加入同一房间、准备、开始，实际服务器发出游戏状态。
- 两端分别同时触摸摇杆与射击；检查发出的输入、服务器角色移动与射击，并检查松手后输入归零。
- 截取真实画布并检查非空、960×720 逻辑分辨率、4:3 缩放。
- 商店让双方暂停，关闭一人的商店仍暂停，双方关闭后继续。
- P2 页面真实重载时 P1 暂停；原标签页重新加载并使用自己的临时凭证加入，仍为 P2 且保留对局。
- 390×844 与 844×390 竖横屏互换。
- 检查页面 JavaScript 异常和意外的公网 HTTP(S) 资源请求。

默认启动等待 180 秒。较慢电脑可用 `--timeout 300`。如果浏览器无法启动、引擎超时或断言失败，脚本返回非零退出码，不自动绕过限制。

## 查看结果

默认目录 `online/.test-mobile-runtime/`（已被现有 `.test-*` 忽略规则排除）：

- `report.json`：PASS/FAIL、已完成检查、浏览器版本、构建入口 SHA-256。
- PNG：大厅、两端战斗、商店暂停、断线暂停、重连、旋转后的实际截图。
- 失败时保留 `failure.txt` 和能够截取的失败画面。

只有 `report.json` 为 PASS 才表示这轮自动断言通过。仍应人工查看截图，确认中文、角色、特效、按钮未被遮挡。脚本不会修改测试结论文件或自动推送代码。

## 仍需真实设备验收

Chromium 模拟不能证明 iOS Safari、Android 机型、音频效果、后台/锁屏行为、弱 Wi-Fi 或完整 Boss 通关表现。正式接受前仍须同一 Wi-Fi 下用两台真实设备完成至少一轮：同时移动射击、技能、购买与装备互斥、死亡复活、后台暂停/恢复、断线重连、旋转。首关 Boss、后续关卡切换及全战役 Boss 通关需另行验收，不能由本脚本的 PASS 推断。
