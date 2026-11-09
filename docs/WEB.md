# TTgames Web 使用说明

先按 [项目 README](../README.md) 安装依赖并激活共用的 `.venv`。以下命令均从项目根目录执行。

## 局域网 HTTPS

内置服务默认使用 HTTPS，监听 `0.0.0.0:8001`。如果已有手机信任的 PEM 证书和私钥，可以直接启动：

```sh
python run_web.py --cert /path/to/cert.pem --key /path/to/key.pem
```

在自己的局域网测试时，可用 [mkcert](https://github.com/FiloSottile/mkcert) 生成证书。将下面的 `192.168.1.23` 改成这台电脑实际的 Wi-Fi IP：

```sh
brew install mkcert
mkdir -p .web-build/tls
CAROOT="$PWD/.web-build/tls" mkcert -cert-file .web-build/tls/cert.pem -key-file .web-build/tls/key.pem localhost 127.0.0.1 192.168.1.23
python run_web.py
```

手机和电脑连接同一 Wi-Fi 后，首次使用请打开终端显示的 HTTP 安装入口（默认 `http://电脑IP:8000/`），下载并信任根证书，再点击「进入 HTTPS 游戏」。安装入口只提供说明和公共证书。自备证书时可用 `--setup-ca /path/to/rootCA.pem` 开启此入口，端口可通过 `--setup-port` 修改。

电脑 IP 改变后，需要用同一 CA 为新 IP 重新签发证书，新地址也会单独缓存。加载完成后点击或触摸一次，浏览器才允许游戏播放音频。

Web 端提供单人游玩、摇杆、手动和自动射击、武器切换、角色技能和商店。横屏时战斗集中在中间半屏，角色和敌人缩为 PC 端尺寸的 64%；竖屏为 80%。菜单、商店和战斗文字在独立画布上按设备像素比绘制，最高 3×；战斗画面缩放使用平滑采样，水下气泡和战斗光效只参与绘制；战斗和触控继续使用原来的逻辑坐标。

首次构建需要联网下载固定版本的 Pygbag、Pygame 和中文字体，生成的 `build/web-offline/` 自带这些资源。Web 副本将关卡背景转为高质量 JPEG，最长边限制为 1920 像素。角色和动画保留原始 PNG，素材原图不变。修改 Web 源码或原图后，重启会自动重新构建；`--force` 强制重建，`--build-only` 只生成文件。

- **HTTPS 或本机 localhost**：游戏加载后会自动保存离线资源。看到“离线资源已保存”后，可以关闭电脑服务，手机断网也能在同一浏览器中重新打开原地址。浏览器清理站点数据后需要联网重新保存。上线新版本时，浏览器会在联网访问时下载新版，关闭所有游戏页面再打开可让已下载的新版接管。
- **普通局域网 HTTP**：可用 `python run_web.py --http` 调试，后续访问仍需连接服务器加载入口。

自托管时，将 `build/web-offline/` 作为站点目录，保留 `Cross-Origin-Opener-Policy: same-origin`、`Cross-Origin-Embedder-Policy: require-corp`，为 WASM 返回 `application/wasm`。入口和 `sw.js` 应重新校验，带版本的资源可长期缓存。内置服务器已提供这些响应头和 gzip 传输，可放在 HTTPS 反向代理后使用。
