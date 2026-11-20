# 海洋生物入侵 · TTgames

PC 和 Web 单人版共用画面、战斗规则和数值。PC 端在原生窗口中运行，Web 端支持浏览器横竖屏触控和离线游玩。原生 PC 与 Web 共用单机和局域网双人入口。「创建房间」可分享电脑的局域网地址与四位房间码。

战役共十二关。第十一关「沉骨海沟」有十二种小怪和首领远古盾鱼·断颚，第十二关「大蛇之巢」直接迎战八岐大蛇。关卡机制、Boss 技能和难度参数见 [战役与无限模式](docs/战役与无限模式.md)。

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

首次开发运行请先执行一次 `python run_web.py --build-only`，并按下方部署文档配置局域网证书。PC 到首页后会复用正在运行的 HTTPS 8001 服务，或用已有 Web 包启动服务。手机首次从 `http://电脑IP:8000/` 安装证书，随后从 `https://电脑IP:8001/` 游玩。PC 和网页共用同一个房间服务，可输入四位房间号加入，也可使用房间底部的邀请链接。

手机浏览器在联机暂停菜单中可切换标准、默认和高清画质。画质选择保存在当前浏览器。

PC 版支持键盘和鼠标。战斗中用键盘移动、射击和施放技能，右侧角色图标下方显示当前技能冷却。可点击「自动关」开启自动射击。

首页按 `1`、`2`、`3` 选择简单、中等或困难，按 `4` 直接进入无限模式。按 `K` 打开按键设置。战役默认选中第一关，用方向键或 `WASD` 切换，按回车出击。也可以点击或触摸对应按钮。

商店可在战斗中打开。角色商品下方的「看技能」可预览图文，点击商品本身会购买并装备，已拥有的商品可以直接切换。

本机浏览器可打开 `http://localhost:8001/`。首次 Web 构建需要联网获取运行时和字体，产物位于 `build/web-offline/`。

Web 游戏由浏览器中的 Python 3.12（WASM）执行。通过 HTTPS 或本机 `localhost` 打开，等页面显示「离线资源已保存」后，可以在同一浏览器离线重开原地址。手机访问、证书和部署细节见 [网页版使用与部署](docs/网页版使用与部署.md)。

## 项目目录

| 路径 | 内容 |
| --- | --- |
| `game_core/` | 两端共用的游戏循环、画面、战斗规则、数值和音效 |
| `pc/` | 原生窗口启动入口和测试 |
| `web/` | 浏览器外壳、构建与服务代码、测试 |
| `online/` | PC 与 Web 共用的局域网服务、快照适配和联机测试；也保留独立战役预览入口 |
| `phaser/` | 独立 Phaser 网页版及其构建和测试 |
| `assets/` | 两端共用的素材和工具，`images/` 下按动画、背景、Boss、敌人、玩家、武器、特效和界面分类 |
| `docs/` | Web 部署说明和玩法数值文档 |

## 测试

```sh
python -m unittest discover
node --test web/tests/test_loading_progress.js online/tools/test_*.cjs
(cd phaser && npm run build && npm test)
```

Python 测试包含 PC、Web 和联机，部分用例需要在本机回环地址绑定临时端口。
