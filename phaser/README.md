# 海洋生物入侵 · Phaser Web 单机版

从根目录的 `assets/images/` 读取正式图片，从 `game_core/config.py` 读取战役数值，并用原版的合成器导出背景音乐和音效。浏览器运行 Phaser 3.90.0 和 JavaScript，构建结果是可独立部署的静态文件。

## 本机运行

在仓库根目录执行：

```sh
python3 -m pip install 'pygame==2.6.1' 'Pillow>=11,<13'
cd phaser
npm ci
npm run build
npm start
```

打开 <http://127.0.0.1:8010/>。已有 TTgames 的 Python 虚拟环境时，可先激活它并跳过安装 Python 依赖。需要 Node.js 18 或更新版本。部署时发布 `phaser/dist/`，不需要 Python 服务、CDN 或 Pygbag。手机通过 HTTPS 访问后，可点首页的「保存离线资源」，等保存完成，再用同一浏览器离线打开原地址。

## 手机 HTTPS 和离线游玩

手机和 Mac 连同一个 Wi-Fi。在仓库根目录用原项目的 mkcert CA 为 Mac 的当前 Wi-Fi IP 签发证书。将下面的 IP 改为实际地址：

```sh
CAROOT="$PWD/.web-build/tls" mkcert -cert-file .web-build/tls/phaser-cert.pem -key-file .web-build/tls/phaser-key.pem 192.168.0.172
cd phaser
npm run start:https -- --host 192.168.0.172 --cert ../.web-build/tls/phaser-cert.pem --key ../.web-build/tls/phaser-key.pem
```

手机打开 `https://192.168.0.172:8011/`。若手机已经信任原版 TTgames 的根证书，可以沿用。首次配置参阅 [证书信任说明](../docs/WEB.md)。在首页点「保存离线资源」，等页面显示「离线资源已保存」后，即可断网并用同一浏览器重开相同地址。

## 游玩

- 十一关均可从战役菜单出击，通关后保留装备并进入下一关。第 6、11 关直接进入 Boss 战，其余关卡先有 40 秒小怪战。
- 支持简单、中等、困难、自定义难度和无限模式。无限模式装备全开，十一关循环，Boss 血量随轮次增加。
- 方向键或 WASD 移动，J 射击，K / L 施放技能，辐射工程师可用空格发射激光。R 可释放飞镖护盾。Q / E 切换已拥有的武器，T 切换自动射击，B 开商店，Esc 暂停。手机默认自动射击，左下半区触碰后拖动可用摇杆，已拥有的武器和角色可以在战场两侧直接切换。
- 掉落金币后靠近拾取，礼包可以射击打开或靠近拾取。失败后可消耗续关次数，或恢复关卡开始时的装备和金币重打。

## 实现和验证

`src/battle.js` 负责固定 60 Hz 的战斗推进，`src/bosses.js` 定义各 Boss 的招式，`src/scene.js` 负责 Phaser 的资源加载和绘制，`src/main.js` 负责菜单、触控和键盘。PC、原 Web 单机和联机仍从原入口启动。

构建后运行 `npm test`，会用实际移动、射击和碰撞走完十一关，并单独检查各 Boss 招式、工厂合体、神庙裂隙、商店、续关和无限循环。自动通关测试屏蔽玩家受伤，以隔离进度和碰撞逻辑。

Phaser 版按原版 Web 的首页、选关、商店和触控布局实现。移动、常规射击、主要角色技能和前六关的 Boss 招式已按原版规则对照调整。Phaser 独立执行战斗，后期 Boss 的完整出招时序、动画、部分角色被动和判定仍有差异。
