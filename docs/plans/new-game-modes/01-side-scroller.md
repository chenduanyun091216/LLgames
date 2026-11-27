# M1 · 横版突围

[总任务书](README.md) · [共用运行时](00-shared-runtime.md) · [跨端验收](06-integration.md)

## 一局如何成立

`run_gun` 是单人／双人合作的侧视卷轴动作模式。开局从货轮甲板左端出发，跑到右侧断桥时，玩家可以等吊箱摆回、跳上高路，也可以从断口主动落入下层货舱。镜头允许等候、回头救人和重新起跳。到达撤离点才结束这一幕。连续模式从所选幕打到隧道出口。练习模式完成所选幕即结算。目标每幕约 2–4 分钟，按有效游戏时间计分。

第一段可玩内容取港口前 2,400 像素，必须包含实心地板、可穿越平台、移动吊箱、能从下路回去的梯子、一种敌人和可以实际到达的出口。此段用于校准手感。正式交付包含下表三幕全长及联机合作。

## 场景和推进

| 幕 ID | 长度与路线 | 中段和检查点 | 终段目标 |
| --- | --- | --- | --- |
| `harbor` 港口货轮 | 12,000 px。前段在甲板学跑跳。断桥上方为摆动吊箱，下方为慢慢灌水的货舱。两路约在 x=5,400 汇合 | x=3,000、7,800 设安全舱门。上路可放下舷梯，给后面的人一条捷径。低路始终有可爬回高处的固定梯 | 到尾甲板开启救生艇绞盘，顶住约 6 秒压力，登艇完成 |
| `rig` 钻井平台 | 14,400 px。外侧为风中的栈桥，内侧穿过泵房。用升降台换层，风向由旗帜和浮粒提前显示 | x=4,000、9,600 设值班间。升降台上下往复，错过可等下一趟。维修通道能避开迎风段 | 越过回转吊臂，操作两只相邻阀门泄压，抵达下降吊笼。单人依次开阀即可 |
| `tunnel` 海底隧道 | 16,800 px。上层是检修轨，下层是玻璃走廊。破窗进水先给明显水线，再沿局部走廊上涨 | x=4,800、11,200 设隔水门。每个进水区都有上行或回撤出口，上一道门只在队伍通过后关闭 | 对付守门机械蟹。躲开横扫后从高低两个高度攻击发光阀芯，打掉两处耐久各 10 的阀芯即可开门撤离 |

每幕至少有一条能用基础跳跃通过的主路线、一条有实际差异的支路、一次会合、一处恢复落脚点。单向门为未通过的队友保留通路。单人通关录像中应能分别走通两路，过场不检查击杀总数。

## 操作、角色与碰撞

| 动作 | 键盘默认 | 触控和判定 |
| --- | --- | --- |
| 左右移动、瞄准 | A/D 或左右键。上下／W、S 和左右组合给出方向 | 左摇杆取八向。空中可回身。地面下压趴下，松开且头顶有空间才站起 |
| 射击 | 按住 J，`held` 位 1 | 右侧射击区可按住。手机默认开启可切换的自动射击，左拇指移动、右拇指跳跃时仍能开火。射击节奏和弹速沿用当前武器的 Player.can_shoot 与 Player.shoot，散弹保留角度分布，侧视瞄准旋转弹道 |
| 换角色、换枪、技能 | C 切换角色，Tab 切换武器，U／I 释放当前角色技能 | 触屏有对应按钮，渔夫的第一技能为手雷，元素角色各有两个技能。横版配装仅用于当前游戏。 |
| 跳跃／下穿 | K 或空格的按下边沿触发 `jump`。下＋跳可从单向板下穿 | 右侧独立跳键。手指按住该键的时长决定跳跃高度，自动射击时仍可两指跑跳。下穿只放行脚下那块单向板，下面的下一层仍能接住玩家 |
| 原地瞄准 | 按住 L，`held` 位 2，方向只改瞄向 | 手机在射击区按住后拖动选择八向，左摇杆仍能移动。联网独立瞄向用 `aim8` 发送。方向中立时沿上次朝向平射 |
| 开门、放梯、救援 | E，`held` 位 4 | 靠近时出现同一交互键。阀门／梯子持续 0.4 秒生效，救人持续 1.2 秒。一次按住最多完成当前一个目标 |

建议初值为跑速 245 px/s，地面加速度 1,800 px/s²，松开减速度 2,100 px/s²，重力 1,550 px/s²，起跳向上 590 px/s，松开跳键时向上速度最多保留 310 px/s。用 `held` 位 8 表示跳仍按住，`jump` 只负责起跳边沿。每个 60 Hz 固定步先处理起跳／松键，再加重力，再按新速度更新坐标。持续按跳的最高点约 107.40 px，满速平地跳在第 45 步落地，脚底中心前进 183.75 px。离台容错与提前按跳各 6 tick。

主路线同时限制净缺口和落台高差。同高时缺口最大 145 px，高出 1–55 px 时最大 140 px，高出 56–85 px 时最大 120 px。满速起跳点在边缘前 8 px 或 16 px 时，下降跨过落台顶面的那一步都应有至少 8 px 水平重叠。强制跳点留足平地助跑。移动平台另用实际运动轨迹检查到达窗口。港口灰盒用高 85、宽 120 的组合做一次可重复的验收跳。

角色脚底中心为位置原点，站姿碰撞框 28×54、趴姿 40×26。没有站立空间就保持趴姿。先移动平台并转移上一步站在平台上的角色，再按 X、Y 两轴处理实体碰撞，明确墙、顶、地和单向板的接触法线。高速弹对整步线段做碰撞。上下表面同时接触时用上一步脚底与移动方向选接触面。移动吊箱撞顶时把玩家送回最后的安全落脚点并走一次受伤流程。梯子区域用上下控制攀爬，离开梯子恢复重力。原战役的自由移动角色碰撞不能直接用于这一套规则。

## 炮台、掩体与关底战

港口轻炮先锁定再发一枚直射弹。钻井平台重炮发两枚分叉弹，隧道将一部分炮台固定在高位检修台上，以三发扇形覆盖上下两条路。每座炮台有 4 点耐久，锁定时显示瞄准线。货箱挡住敌我双方的弹道，可以跳上箱顶、爬梯换层或前进拆炮。方向键支持八向射击。小键盘 2、4、6、8 可独立于移动瞄准，触屏可在射击键上拖动选方向。

三幕关底依次为铁钳船长、熔炉守卫、深渊巨鲸。铁钳发低位冲击波，熔炉在锁定位置落钻，巨鲸在锁定位置两侧升起水柱，危险区生效前会给出预警。击破首领后分别完成绞盘、双阀、双阀芯撤离。双方共享炮台耐久、首领耐久、危险区和敌弹，由房间推进一次模拟步。

## 战斗、恢复与合作镜头

- 两人选用战役中的渔夫、火人、冰人、水人或辐射工程师，各自保留角色技能，每人 3 HP。同一次受伤扣 1，随后 72 tick 保护。坠出世界将个人送回最近安全落脚点并扣 1 HP，耗尽生命进入倒地。首版三种敌人各有清楚轮廓。横向巡逻蟹有 2 HP，吐泡水母有 3 HP，固定喷口有 4 HP。喷口攻击先闪灯 36 tick。远离镜头的触发器按区段唤醒，一只敌人的稳定 ID 在同一次区段内只结算一次。
- 每幕有两次全队从检查点重整的机会。单人倒地或全队倒地消耗一次。用尽进入失败页，可从本幕重开。仍有人存活时可以靠近拉起队友，恢复 1 HP 并获得保护。活人通过下一检查点时，倒地者一同回到安全点并恢复 1 HP。终点至少一名活人抵达，其他活人也进入出口后完成。倒地者视为随队撤离。
- 检查点记录幕、出生坐标、已开启的必经阀门／梯子和推进段。重整时恢复全员 3 HP，重建这一段的危险物，清除旧子弹。本幕耗时继续。恢复后至少有一个整身安全站位。两人同时倒地只扣一次机会。
- 单人镜头让前进方向留约 35% 视野，停止后镜头稳定。合作用两名活人的包围框，目标位置限在关卡边界内。活人间距达 660 px 时提示集合，达到 720 px 时限制领先者继续拉大距离。后方可自由追回。下路与上路的设计高度须同时落在共享视口内。镜头进入战斗区前两人均有安全站位。
- 房间暂断按公共约定冻结。有人确认离席或超过重连期限，剩余玩家得到「独自继续／结束本局」。继续时把所选模式转为同局单人规则，移除队友对镜头、门和出口的占位。PC/主 Web 单人入口与继续中的房间使用同一内容和移动规则。

## 数据、呈现与制作顺序

建议文件为 `game_core/modes/run_gun.py` 与 `assets/modes/run_gun/{harbor,rig,tunnel}.json`。把世界坐标、碰撞和相机计算彼此分开。每幕数据包含 `id / version / length / spawn / solids / one_way / ladders / moving_platforms / encounters / checkpoints / triggers / exit`。运动平台带端点、周期、初始相位，开关以稳定 ID 引用目标。快照传角色位置与速度、姿态、朝向、生命、当前站立平台、共同镜头、激活触发器、检查点与剩余机会。联机客户端可从 tick 计算装饰运动，碰撞跟随服务端位置。

横版角色以战役立绘为准，保留渔夫头巾、背篓以及四名元素角色的头盔、配色和装备。站立、跨步、蹲姿和施法使用独立侧身画稿，脚底为共同锚点。枪械挂在手部，掉头时同时改变枪口和弹道。跳、落、攀爬、受伤与救援也应按侧视姿势验收。两名队员须能区分。PC 使用主游戏的画质设置，在 3840×2160 直接绘制背景、角色、武器和界面。用三层横向可拼接远景、与落脚面贴合的前景、吊箱绳索和阀门状态构成场景。战役中的子弹、泡泡、命中特效可复用。在灰盒先用人物脚底、平台边和弹道验证动作，正式交付替换主角与三幕的关键地形。HUD 显示 HP、队友倒地位置、检查点和出口目标，蓄水依靠场景水线与声音提示。

| 实施段 | 产物和过线条件 |
| --- | --- |
| S-A 手感 | 完成 F0 和港口样段，键盘与手机双指都能实现短跳、长跳、移动射击、下穿与回头 |
| S-B 单人全程 | 数据驱动铺完三幕、检查点和结算，练习与连续模式分别从首页走一遍 |
| S-C 合作 | 完成 F1、共享镜头、救援和中途离席，双端过同一座断桥并能走不同路线 |
| S-D 跨端 | 使用同一地图给 Phaser 做单人移植，完成主 Web 离线、画质和触控验收 |

## 验收 S1–S8

| 编号 | 从哪里做什么 | 通过表现 |
| --- | --- | --- |
| S1 | 首页选港口练习，在第一座桥边停留 8 秒再往左走 | 玩家可原地等待和回头，画面跟随玩家，出口由空间位置触发 |
| S2 | 对同一空地短按、长按跳，试一次落地前 4 tick 提前按跳，再以满速从边前 8／16 px 起跳到高 85、净宽 120 的平台 | 两种高度可辨，提前输入只产生一次跳跃。两次高台跳均在第 33 步落稳，撞顶和下穿后也能正常落地 |
| S3 | 分别走吊箱上路与货舱下路，再从检查点重整 | 两路都能到达，角色站在安全点，必经装置状态一致 |
| S4 | 手机开启自动射击，双指边移动边跳。再关自动射击，双指移动并拖动射击区瞄准，旋转或后台后松手 | 可完成边跑边跳射。恢复时角色和射击不会卡在按住态 |
| S5 | 双人一高一低拉开、落后者倒地、队友放梯并救援 | 两人均可见或有明确倒地标记。镜头跟随活人，救援只恢复一次 |
| S6 | 同 tick 全队倒地、最后一次机会后再倒地。各试一次主动离席和重连 | 正确扣一次机会、给出失败或继续选择。重连回到原位置，无门禁死锁 |
| S7 | 连续模式从港口打通三幕，再单开平台练习 | 连续模式只在最后撤离后出总结果，练习仅结算该幕。可重试也可返回大厅 |
| S8 | PC、主 Web、Phaser 对同一跳跃与同一平台运行相同输入 | 同一 tick 落地误差至多 1 tick、位置差至多 2 px。断网可从两个网页单人入口进港口 |


<details>
<summary>横版美术源提示词（内置 ImageGen）</summary>

成品位于 `assets/images/side_view/`。五个角色按渔夫、火、冰、水、辐射排列。站立和跑动使用战役原画对照，蹲姿和施法以首张侧身图为参照。

**侧身站立／跑动**

Reference image is the exact character costume and color lineup from an existing game. Make ONE production sprite atlas, all FIVE of these specific characters in same LEFT TO RIGHT order, each a full body facing to the RIGHT, visibly SIDE PROFILE nose and gaze oriented right, not front or back. Portraits forbidden; include feet. 5 equal columns x 2 equal rows on real transparent background, landscape 2.5:1 canvas, 10 isolated full-body figures. Same baseline and head size in each cell, all ten separated by clear space. Row 1 relaxed standing shooting stance holding imaginary gun, arms forward hands empty to attach separate weapon. Row 2 same characters running to the right mid-stride with separated legs and arms forward for a modular gun. Col1 adorable young fisherman yellow kerchief with knot behind his head, dark tousled hair, teal rolled sleeves, woven basket on his BACK, shorts and yellow boots. Col2 original shiny red fire suit dark blue visor. Col3 heavy navy ice dive armor glowing cyan round helmet window and ice crystals. Col4 bright turquoise aqua suit reflective royal blue visor and rebreather. Col5 purple-black radiation engineer hazard-yellow accents tiny radiation symbol and violet visor. Preserve the reference costume silhouettes, glossy highlights, chibi proportions, clean bold outlines and colorful polished mobile game style. ONLY 10 sprites, no text, weapons, ground, shadows outside figures, border or labels. Animations must read clearly at 65 logical pixels but be beautifully crisp at 4K.

**蹲姿／施法**

Use supplied existing two-row model sheet as strict identity and exact scale/color rendering reference. Production side-view game sprite atlas with FIVE equal columns in exact same lineup as reference: yellow kerchief basket fisherman, red fire diver, navy ice diver, cyan water diver, black violet and yellow radiation diver. Two new animation poses only. Same right-facing complete side profile for all ten. TOP ROW crouching low on bent knees, hands forward aiming empty hands horizontally; keep full boots in view. BOTTOM ROW braced standing and casting: forward arm extended with open hand, rear arm bent, no weapons or glowing effects baked into image. Match original face, silhouette, outlines, proportions and costume details precisely. Ten sprites in a clean 5 columns x 2 rows orthographic grid on genuine transparent background, ample gutters, 2.5:1 wide canvas. Each sprite's feet near its cell bottom. No text, boxes, shadows, background, guns or effects.

**平台**

A single horizontal modular underwater dock platform sprite on real transparent background. Wide landscape canvas. Side elevation orthographic, straight continuous absolutely flat walkable top with bright thin rim and bevel, width to height about 7:1, clean vertical cut ends at same height, suited for repeating. Hand painted high fidelity 2D ocean adventure game environment art, rich teal patinated structural iron surrounding deep honey brown ship timbers, legible large shapes, scale blue green mussels and warm barnacle clusters, sparse peach coral on underside only, hanging short fronds. Strong painted material and color gradients, light from above. Isolated, no legs below, no scenery, no text, no characters, no background, no contact shadow.

**重炮**

A single large side-view sprite of a hostile automated harbor sentry gun, on true transparent background. Exact orthographic profile, barrel points LEFT. A squat bolted cast-iron pedestal with heavy bronze rings, two short outriggers holding it to the deck, swivel turret steel blue enamel armoured cowling, large distinct round red glowing aiming lens and one ribbed horizontal barrel. Clear, instantly readable silhouette at 65px screen height. Rich handpainted high-resolution colorful 2D undersea adventure game art, golden rim highlights and sea-green oxidized brass, strong contours like chibi combat divers. Entire object isolated, no water, no environment, no words, no figures, no floor shadow, no muzzle flash.

**轻炮与场景物件**

A production game asset atlas, six separate 2D side-view level props for an illustrated ocean platform run and gun adventure. 3 equal columns by 2 equal rows in a wide 3:2 canvas, all isolated on real transparency, gutters. TOP ROW: 1 a compact hostile stationary naval turret on squat iron base, barrel pointing horizontally LEFT with glowing orange lens; 2 a wooden reinforced fishing port supply crate frontal view square stackable with rope and painted detail; 3 a docked small rusted maritime crane with winch and hook facing right on a heavy base, empty interior transparent. BOTTOM ROW: 1 a diving bell lift cage with platform floor open front and vertical support posts; 2 a vertical ladder segment front elevation weathered brass matching a navy ship with evenly spaced rungs; 3 a broken cylindrical glass undersea tunnel section with blue glowing ribs and cracked glass, seen side on, suited as foreground architectural trim. No people, text, UI, scenery, panel dividers or lettering. High quality 2D painted colorful marine adventure game style consistent dense shapes, crisp outlines, golden corroded brass, deep turquoise occlusion and warm light highlights, readable silhouettes. Each prop fully contained in its cell, no overlap.

</details>
