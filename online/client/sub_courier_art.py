"""Native-resolution drawing for the cargo submarine's two stations."""
import math
from functools import lru_cache

import pygame

from game_core import config
from game_core.asset_loader import cover_image_asset, image_asset, image_variant, scale_surface_cached
from game_core.render import Draw, RenderSurface
from game_core.modes.sub_courier import BOTTOM, ORDERS, POWER, STATIONS, TOP

INK = (9, 29, 43)
PANEL = (17, 48, 63)
LINE = (56, 108, 120)
MINT = (149, 241, 217)
TEXT = (228, 248, 243)
AMBER = (255, 199, 109)
RED = (255, 126, 108)
CARGO_ART = {'jelly': 'enemies/enemy_trench_jelly.png', 'calf': 'bosses/boss_ancient_whale.png'}


@lru_cache(maxsize=2)
def ocean(name, size, variant):
    return cover_image_asset(f'backgrounds/{name}.jpg', size, variant=variant) or cover_image_asset(
        f'backgrounds/{name}.png', size, variant=variant)


@lru_cache(maxsize=32)
def font(size, bold):
    return config.make_font(size, bold)


@lru_cache(maxsize=128)
def glyph(label, size, color, bold):
    return font(size, bold).render(label, True, color)


def viewport(target, portrait):
    rect = pygame.Rect(0, 0, 520 if portrait else 960, 780 if portrait else 540).fit(target.get_rect())
    rect.center = target.get_rect().center
    return rect


class Console:
    def __init__(self, target, portrait):
        self.width = 520 if portrait else 960
        self.height = 780 if portrait else 540
        self.bounds = viewport(target, portrait)
        if target.get_size() != self.bounds.size:
            target.fill(INK)
        self.pixels = target.subsurface(self.bounds)
        self.s = RenderSurface(self.pixels, (self.width, self.height), self.bounds.size, (0, 0), desktop_ui=True)

    def text(self, value, x, y, size=16, color=TEXT, bold=False):
        surface = glyph(str(value), max(1, self.s.length(size)), color, bold)
        self.pixels.blit(surface, self.s.point((x, y)))

    def rect(self, color, box, width=0, radius=0):
        Draw.rect(self.s, color, box, width, radius)

    def line(self, color, start, end, width=1):
        Draw.line(self.s, color, start, end, width)

    def circle(self, color, point, radius, width=0):
        Draw.circle(self.s, color, point, radius, width)

    def panel(self, box, fill=PANEL):
        self.rect(fill, box, radius=12)
        self.rect(LINE, box, 1, 12)

    def art(self, name, x, y, width, height):
        art = image_asset(name)
        if art:
            w, h = art.get_size()
            scale = min(width / w, height / h)
            art = scale_surface_cached(art, (self.s.length(w * scale), self.s.length(h * scale)))
            self.pixels.blit(art, art.get_rect(center=self.s.point((x, y))))

    def cargo(self, order, x, y, width, height):
        if order != 'express':
            self.art(CARGO_ART[order], x, y, width, height)
            return
        box = (x - width * .45, y - height * .25, width * .9, height * .5)
        self.rect(AMBER, box, radius=height * .16)
        self.rect((113, 70, 47), box, 2, height * .16)
        for band in (-.31, .24):
            self.rect((61, 106, 119), (x + band * width, y - height * .22, width * .075, height * .44))
        self.rect(INK, (x - width * .14, y - height * .08, width * .28, height * .16), radius=2)

    def bar(self, x, y, width, value, color):
        self.rect((8, 26, 39), (x, y, width, 6), radius=3)
        if value > 0:
            self.rect(color, (x, y, width * min(1., value), 6), radius=3)

    def button(self, rect, label, active):
        self.panel(rect, (35, 101, 108) if active else PANEL)
        self.text(label, rect.x + 10, rect.y + 11, 15, MINT if active else TEXT, True)


def helm_scene(c, w, route, tick):
    # Fit the same 960 logical pixels on both orientations, including upcoming landmarks.
    scale = (c.width - 24) / 960
    top = 82
    bg = pygame.Rect(c.s.rect((12, top, c.width - 24, 350 * scale)))
    background = ocean(route['background'], bg.size, image_variant())
    if background:
        c.pixels.blit(background, bg)
    else:
        pygame.draw.rect(c.pixels, (26, 87, 109), bg)
    old = c.pixels.get_clip()
    c.pixels.set_clip(bg)
    cam = max(0, w['x'] - 280)

    def pos(x, y):
        return 12 + (x - cam) * scale, top + (y - TOP) * scale

    def box(area, fill, edge):
        l, r, t, b = area
        if r < cam or l > cam + 960:
            return
        xx, yy = pos(max(l, cam), t)
        ww, hh = (min(r, cam + 960) - max(l, cam)) * scale, (b - t) * scale
        c.rect(fill, (xx, yy, ww, hh), radius=3)
        c.rect(edge, (xx, yy, ww, hh), 2, 3)
        for bx in range(int(l) + 27, int(min(r, cam + 960)), 35):
            if bx < cam - 60:
                continue
            p, q = pos(bx, b)
            depth = (19 + bx % 47) * scale
            Draw.polygon(c.s, (35 + bx % 7, 69 + bx % 10, 73 + bx % 11),
                         [(p - 30 * scale, q - 2), (p - 23 * scale, q - depth),
                          (p + 7 * scale, q - depth * 1.33), (p + 26 * scale, q - 2)])
            c.line(edge, (p, q - 8 * scale), (p + 9 * scale, q - 2), 1)

    for index in range(25):
        x = (index * 137 - cam * .36) % 960 + cam
        y = (index * 87 - tick * .35) % (BOTTOM - TOP) + TOP
        c.circle((149, 209, 219), pos(x, y), (2 + index % 4) * scale, 1)
    for left, right, y1, y2, vx, vy in route['flows']:
        if right < cam or left > cam + 960:
            continue
        for x in range(max(left, int(cam // 115) * 115), min(right, int(cam + 960)), 115):
            p = pos(x, y1 + (y2-y1)*.55)
            q = (p[0] + math.copysign(27 * scale, vx), p[1] + vy * scale)
            c.line(MINT, p, q, 2)
            c.circle(MINT, q, 2)
    for left, right in route.get('quiet', []):
        if cam <= left <= cam + 960:
            px, py = pos(left, BOTTOM - 12)
            c.line(AMBER, (px, py), (px, py - 42 * scale), 2)
            c.text('静音', px + 5, py - 23, 14, AMBER, True)
        if cam <= right <= cam + 960:
            px, py = pos(right, BOTTOM - 12)
            c.line(MINT, (px, py), (px, py - 42 * scale), 2)
    for obstacle in route['obstacles']:
        if w['content_id'] == 'jelly' and obstacle[0] == 5100:
            left, right, y1, y2 = obstacle
            box(obstacle, (88, 67, 47), (221, 166, 92))
            for x in (left + 12, right - 12):
                c.line(AMBER, pos(x, y1 + 4), pos(x, y2 - 3), 2)
        else:
            box(obstacle, (25, 57, 67), (121, 166, 156))
    gate = route.get('gate')
    if gate:
        left, right, top_y, bottom_y = gate['wait']
        if right >= cam and left <= cam + 960:
            px, py = pos(left, bottom_y - 8)
            qx, _ = pos(right, bottom_y - 8)
            for xx in range(round(px), round(qx), 22):
                c.line(AMBER, (xx, py), (min(xx + 12, qx), py), 2)
            c.text('压载等待区', px + 9, py - 25, 14, AMBER, True)
        open_gate = w['runtime']['gate_ticks'] > 0
        if not open_gate:
            box(gate['entry'], (44, 61, 66), AMBER)
            if not w['runtime']['gate_used']:
                box((gate['exit'], gate['exit'] + 50, 315, BOTTOM), (44, 61, 66), AMBER)
        for gx in (gate['entry'][0], gate['exit']):
            if cam <= gx < cam + 960:
                c.circle(MINT if open_gate else AMBER, pos(gx, 322), 6 * scale)
    for x, label in route['landmarks']:
        if cam - 100 <= x <= cam + 960:
            px, py = pos(x, 90)
            c.line(AMBER, (px, py + 22), (px, py + 47 * scale + 22), 2)
            c.circle(AMBER, (px, py + 20), 4)
            c.text(label, px + 8, py + 9, 13 if scale < .7 else 16, AMBER, True)
    if cam <= route.get('cargo_event', -1) <= cam + 960 and w['content_id'] == 'express':
        xx, yy = pos(route['cargo_event'], 355)
        c.art('enemies/enemy_crab.png', xx, yy, 82 * scale, 62 * scale)
    l, r, t, b = route['dock']
    if l <= cam + 960:
        for xx in (l, r):
            p, q = pos(xx, t), pos(xx, b)
            c.line(MINT, p, q, 2)
            c.circle(MINT, p, 6 * scale)
            c.circle(MINT, q, 6 * scale)
        c.line(MINT, pos(l, b), pos(r, b), 2)
    x, y = pos(w['x'], w['y'])
    if abs(w['vx']) > 8:
        for i in range(3):
            rise = (tick + 13 * i) % 39
            c.art('effects/orochi_bubble_mint.png', x - (47 + rise) * scale,
                  y - rise * .42 * scale, (9 + i * 2) * scale, (9 + i * 2) * scale)
    sprite = image_asset('modes/deep_dive/sub.png')
    if sprite:
        sprite = scale_surface_cached(sprite, (c.s.length(100 * scale), c.s.length(40 * scale)))
        c.pixels.blit(sprite, sprite.get_rect(center=c.s.point((x, y))))
        c.circle(MINT, (x + 42 * scale, y + 1 * scale), 3 * scale)
    else:
        submarine(c, x, y, scale, w)
    c.pixels.set_clip(old)
    c.rect(LINE, (12, top, c.width - 24, 350 * scale), 3, 6)
    return top + 350 * scale + 12


def submarine(c, x, y, scale, w, cutaway=False):
    def box(left, top, width, height):
        return x + left * scale, y + top * scale, width * scale, height * scale
    c.rect((17, 37, 49), box(-50, -20, 100, 40), radius=18 * scale)
    c.rect((223, 153, 69), box(-49, -19, 98, 35), radius=17 * scale)
    c.rect((143, 78, 51), box(-42, 7, 84, 10), radius=5 * scale)
    c.rect((255, 213, 131), box(-35, -17, 68, 5), radius=3 * scale)
    if cutaway:
        c.rect(INK, box(-39, -10, 72, 21), radius=3 * scale)
        for tx in (-36, -13):
            c.rect(LINE, box(tx, -8, 19, 16), 1)
            fill = 15 * w['ballast'] / 100
            if fill:
                c.rect((52, 173, 188), box(tx + 1, 7 - fill, 17, fill), radius=2)
        c.cargo(w['content_id'], x + 19 * scale, y, 23 * scale, 17 * scale)
        if w['leak']:
            c.circle(RED, (x - 38 * scale, y + 10 * scale), 2.5 * scale)
    else:
        for cx in (-19, 4, 28):
            pt = (x + cx * scale, y - 2 * scale)
            c.circle(INK, pt, 8 * scale)
            c.circle((68, 176, 191), pt, 6 * scale)
            c.circle(MINT, (pt[0] - 2 * scale, pt[1] - 2 * scale), 2 * scale)
        c.circle(AMBER, (x + 45 * scale, y + 2 * scale), 3 * scale)


def engineer_scene(c, w, route, tick):
    p = c.width < 960
    c.panel((12, 82, c.width - 24, 184))
    for x in range(30, c.width - 20, 24):
        c.line((24, 58, 71), (x, 120), (x, 215))
    for y in range(120, 215, 18):
        c.line((24, 58, 71), (24, y), (c.width - 24, y))
    c.text('艇体剖面', 28, 94, 18, MINT, True)
    c.art('side_view/water_idle.png', c.width - 63, 145, 78, 88)
    submarine(c, c.width * .48, 165, 2.85 if p else 3.5, w, cutaway=True)
    c.text('双压载水箱', c.width * .48 - (97 if p else 122), 239, 13, MINT)
    c.text('货舱', c.width * .48 + (42 if p else 53), 239, 13, MINT)
    vx, vy = w['vx'], w['vy']
    dx, dy = w['runtime']['intent']
    c.text(f'舵手输入 {dx:+.1f} / {dy:+.1f}     实际 {vx:+.0f} / {vy:+.0f} px/s', 28, 221, 15)
    x = 26
    gap = (c.width - 52) // 4
    for index, power in enumerate(POWER):
        c.rect((43, 101, 108) if index == w['power'] else INK, (x + gap * index, 275, gap - 5, 35), radius=7)
        c.text(power, x + gap * index + 10, 282, 16, MINT if index == w['power'] else TEXT)
    station = w['station']
    info = ('漏点报警，持续操作 2 秒' if w['leak'] else '泵正常',
            '卡扣松动，持续操作 1 秒' if w['cargo']['loose'] else '货架卡扣闭合',
            dock_status(w))[station]
    c.text(f'{STATIONS[station]}  ·  {info}', 27, 323, 17, AMBER, True)
    c.bar(28, 348, c.width - 56, (w['dock_ticks'] / 60 if station == 2 else
                                  w['runtime']['work'] / (120 if station == 0 else 60)), MINT)
    ahead = next(((x - w['x'], label) for x, label in route['landmarks'] if x >= w['x']), (0, '泊位'))
    c.text(f'压载 {w["ballast"]:.0f}%   进水 {"1 点" if w["leak"] else "0"}   下一地标 {ahead[1]} {ahead[0]:.0f}px',
           27, 364, 15)
    detail = {
        'jelly': '静音防震吊架已落锁' if w['power'] == 2 else '切静音可锁住防震吊架',
        'express': '货架松动：强推限为标准' if w['cargo']['loose'] else '文件筒防撞',
        'calf': '惊醒值达到 100 时订单中止',
    }[w['content_id']]
    c.text(detail, 27, 389, 14, MINT)
    return 417


def dock_status(w):
    if w['dock_ticks'] >= 60:
        return '可签收，按 E 或点交货'
    if w['dock_ticks']:
        return f'停稳 {w["dock_ticks"]}/60'
    return '整艇驶入泊位，合速度低于 15'


def draw(target, portrait, w, role, state, controls, active, status, slot):
    c = Console(target, portrait)
    c.pixels.fill(INK)
    route = ORDERS[w['content_id']]
    c.panel((12, 9, c.width - 24, 63))
    seconds = (w['remaining_ticks'] + 59) // 60
    c.text(f'{route["name"]}  /  {"舵手" if role == "helm" else "轮机员"}', 25, 15, 22, MINT, True)
    c.text(f'航段 {w["route_segment"]}/3    {seconds//60:02d}:{seconds%60:02d}    船体 {math.ceil(w["hull"])}%',
           25, 44, 15)
    cargo = w['cargo']
    condition = {'jelly': f'完整度 {cargo["integrity"]}%',
                 'express': '卡扣松动' if cargo['loose'] else '文件筒稳固',
                 'calf': f'惊醒值 {cargo["wake"]:.0f}/100'}[w['content_id']]
    c.text(condition, c.width - 130, 45, 14, AMBER if cargo['loose'] else MINT)
    if role == 'helm':
        y = helm_scene(c, w, route, state['tick'])
        fx, fy = w['runtime']['flow']
        angle = math.degrees(math.atan2(w['vy'], max(abs(w['vx']), 1)))
        c.text(f'航速 {math.hypot(w["vx"], w["vy"]):.0f}    俯仰 {angle:+.0f}°    海流 {fx:+}/{fy:+}', 22, y, 15)
        if w['leak']:
            c.text('船体进水', c.width - 108, y, 15, RED, True)
        signal_y = y + 22
    else:
        signal_y = engineer_scene(c, w, route, state['tick'])
    signal = w['slot_signals'].get(str(slot))
    message = status or w['runtime']['swap'] or (f'搭档信号 · {signal}' if signal else '')
    if message and not w['result']:
        c.rect(INK, (15, signal_y - 2, c.width - 30, 24), radius=5)
        c.text(message, 24, signal_y, 15, AMBER, True)
    if w['loading_ticks'] and not w['result']:
        y = 135 if not portrait else 215
        c.panel((c.width / 2 - 142, y, 284, 132), INK)
        progress = 1 - w['loading_ticks'] / 120
        c.text(f'正在装载 · {route["name"]}', c.width / 2 - 123, y + 10, 17, MINT, True)
        cab_x = c.width / 2 + (1 - progress) * 105
        c.rect(LINE, (c.width / 2 - 115, y + 40, 230, 61), 1, 6)
        c.cargo(w['content_id'], cab_x, y + 69, 66, 52)
        c.bar(c.width / 2 - 115, y + 109, 230, progress, MINT)
    if w['result']:
        result = w['result']
        y = 116 if not portrait else 190
        c.panel((24, y, c.width - 48, 250), INK)
        c.text(result['reason'], 48, y + 14, 29, MINT if result['success'] else AMBER, True)
        c.text(f'{result["stars"]} / 3 星    用时 {result["ticks"]/60:.1f} 秒    船体 {result["hull"]:.0f}%',
               48, y + 62, 17)
        cargo_result = {'jelly': f'货损 {100 - result["integrity"]}%',
                        'express': '短闸通过' if result['shortcut'] else '安全航道',
                        'calf': f'最高惊醒值 {result["peak_wake"]:.0f}'}[w['content_id']]
        c.text(cargo_result, 48, y + 89, 16, AMBER)
        for index, (seat, rec) in enumerate(result['records'].items()):
            yy = y + 120 + 40 * index
            c.text(f'P{seat}  掌舵 {rec["helm_ticks"]/60:.0f}秒 · 轮机 {rec["engine_ticks"]/60:.0f}秒',
                   48, yy, 15)
            c.text(f'重撞 {rec["impacts"]} · 修漏 {rec["repairs"]} · 锁扣 {rec["latches"]} · 签收 {rec["deliveries"]}',
                   48, yy + 18, 14)
        if status:
            c.text(status, 48, y + 208, 15, AMBER)
    for key, label, rect in controls:
        if key == 'stick':
            c.circle(LINE, rect.center, rect.w / 2, 2)
            dx, dy = active.get(key, (0, 0))
            c.circle(MINT, (rect.centerx + dx * rect.w * .28, rect.centery + dy * rect.h * .28), 14)
        else:
            c.button(rect, label, key in active)
