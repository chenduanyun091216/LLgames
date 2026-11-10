# Windows Web HTTPS 证书配置

以下步骤在 Windows PowerShell 中执行，命令从项目根目录运行。先按 [项目 README](../README.md) 安装 Python 依赖并激活 `.venv`。

## 1. 安装 mkcert

使用 Windows 包管理器安装：

```powershell
winget install --id FiloSottile.mkcert -e
```

安装后重新打开 PowerShell，进入项目根目录并重新激活 `.venv`。如果没有 `winget`，可从 [mkcert 官方发布页面](https://github.com/FiloSottile/mkcert/releases) 下载 Windows 版本，按官方说明配置后确认 `mkcert -version` 可以运行。

## 2. 查看电脑的局域网 IP

```powershell
ipconfig
```

找到当前 Wi-Fi 或以太网连接的 IPv4 地址。以下使用 `192.168.1.23` 举例，请替换为实际地址；不要使用 `127.0.0.1` 作为手机访问地址。

## 3. 生成证书并启动

```powershell
New-Item -ItemType Directory -Force .web-build\tls
$env:CAROOT = (Resolve-Path .web-build\tls).Path
mkcert -cert-file .web-build\tls\cert.pem -key-file .web-build\tls\key.pem localhost 127.0.0.1 198.18.0.1
python run_web.py
```

`mkcert` 会在 `.web-build\tls` 中生成根证书、服务器证书和私钥。请保管好 `rootCA-key.pem` 和 `key.pem`，不要发送给其他人。重复签发时保留同一目录中的根证书和根私钥；电脑 IP 改变后，用新 IP 重新运行上述签发命令。

## 4. 在手机上安装并访问

手机与电脑连接同一局域网，在手机浏览器中打开终端显示的 HTTP 安装入口，默认是 `http://电脑IP:8000/`。下载并信任公共根证书，然后点击「进入 HTTPS 游戏」：

- iPhone：用 Safari 下载，在设置中安装已下载的描述文件，再到「通用 → 关于本机 → 证书信任设置」开启完全信任。
- Android：在系统设置中搜索「安装 CA 证书」，选择下载的 `rootCA.cer`。

游戏默认地址为 `https://电脑IP:8001/`。若手机无法连接，请检查 IP、网络连接及 Windows 防火墙是否允许 Python 的局域网访问。首次构建需要联网；看到「离线资源已保存」后，同一浏览器可离线重开原地址。

已有证书时，也可使用 `python run_web.py --cert 证书路径 --key 私钥路径 --setup-ca 根证书路径`。仅在本机调试可使用 `python run_web.py --http --host 127.0.0.1`。更多说明见 [Web 使用说明](WEB.md)。
