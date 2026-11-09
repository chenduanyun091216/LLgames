# 海洋生物入侵 · TTgames

PC 和 Web 端均为单人游戏，共用原 Web 版的画面、战斗规则和数值。PC 端在原生窗口中运行，Web 端支持浏览器横竖屏触控和离线游玩。

## 安装

在项目根目录操作。PC 端运行、Web 构建和本地服务共用 Python 3.12 的 `.venv`，依赖统一从 `requirements.txt` 安装。已有其他 Python 版本的 `.venv` 时，先备份旧目录，再创建新环境。

**macOS / Linux**

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

**Windows PowerShell**

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## 启动

激活 `.venv` 后，从项目根目录运行对应脚本。

| 用途 | 命令 |
| --- | --- |
| 启动 PC 版 | `python run_pc.py` |
| 在本机浏览器游玩 | `python run_web.py --http --host 127.0.0.1` |
| 通过 HTTPS 提供局域网访问 | `python run_web.py --cert /path/to/cert.pem --key /path/to/key.pem` |
| 只构建 Web 版 | `python run_web.py --build-only` |

本机浏览器可打开 `http://localhost:8001/`。首次 Web 构建需要联网获取运行时和字体，产物位于 `build/web-offline/`。

Web 游戏由浏览器中的 Python 3.12（WASM）执行。通过 HTTPS 或本机 `localhost` 打开，等页面显示「离线资源已保存」后，可以在同一浏览器离线重开原地址。手机访问、证书和部署细节见 [Web 使用说明](docs/WEB.md)。

## 项目目录

| 路径 | 内容 |
| --- | --- |
| `game_core/` | 两端共用的游戏循环、画面、战斗规则、数值和音效 |
| `pc/` | 原生窗口启动入口和测试 |
| `web/` | 浏览器外壳、构建与服务代码、测试 |
| `assets/` | 两端共用的素材和工具，`images/` 下按动画、背景、Boss、敌人、玩家、武器、特效和界面分类 |
| `docs/` | Web 部署说明和玩法数值文档 |

## 测试

```sh
python -m unittest discover
node --test web/tests/test_loading_progress.js
```
