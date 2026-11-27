"""Paint the original campaign art and authoritative hazards at output resolution."""
from functools import lru_cache
from math import ceil, cos, sin, tau

import pygame

from game_core import config
from game_core.animation import frame, square_frame
from game_core.asset_loader import cover_image_asset, image_asset, image_variant, scale_surface_cached
from game_core.modes.boss_duel import BOSSES, ERRORS, HEIGHT, WEAK, WIDTH, clip, shapes, unit
from game_core.render import Draw, RenderSurface

ARENA = pygame.Rect(0, 0, WIDTH, HEIGHT)
HUD_HEIGHT = 60
DESKTOP_CONTROLS = 72
TOUCH_CONTROLS = 102
CREAM = (237, 251, 251)
MUTED = (170, 211, 224)
INK = (7, 25, 42)
PALETTE = {'whale': (118, 225, 255), 'mecha': (255, 185, 103), 'orochi': (219, 168, 255)}
EFFECTS = {
    'geyser': 'effects/whale_rune_geyser.png', 'pearl': 'effects/whale_ancient_pearl.png',
    'crescent': 'effects/whale_tidal_crescent.png', 'missile': 'effects/mecha_guided_missile.png',
    'slam': 'animations/bosses/boss_orochi_slam.png',
}
NAMES = {skill[1]: skill[0] for boss in BOSSES.values() for skill in boss['skills']}
METRICS = {'defeated': '击倒首领', 'defeat_tick': '击倒用时', 'hp': '剩余生命',
           'survival_tick': '生存时间', 'damage': '实际伤害', 'draw': '两席成绩相同',
           'forfeit': '对方弃权', 'aborted': '比赛中止'}


@lru_cache(maxsize=32)
def font(size, bold):
    return config.make_font(size, bold)


@lru_cache(maxsize=3)
def background(size, variant):
    art = cover_image_asset('backgrounds/trench-boss-wide.png', size, variant=variant)
    if art is None:
        return None
    matte = art.convert()
    matte.fill((149, 173, 190), special_flags=pygame.BLEND_RGB_MULT)
    return matte


@lru_cache(maxsize=128)
def sprite_at(art, width, height, angle, stretch):
    box = art.get_bounding_rect(min_alpha=12)
    if box.width and box.height:
        art = art.subsurface(box)
    size = (width, height) if stretch else art.get_rect().fit((0, 0, width, height)).size
    image = scale_surface_cached(art, size)
    return pygame.transform.rotate(image, angle) if angle else image


@lru_cache(maxsize=16)
def sheet_pose(art, columns, rows, index):
    w, h = art.get_width()//columns, art.get_height()//rows
    return art.subsurface((index % columns*w, index // columns*h, w, h))


def boss_sprite(boss, clock, cast=None):
    if boss == 'whale':
        sheet = image_asset('animations/bosses/anim_boss_ancient_whale.png')
        if sheet is not None:
            row = {'crescent':1, 'geyser':2, 'pearl':3}.get(cast['kind'], 0) if cast else 0
            return square_frame(sheet, clock//7 % 8, min(sheet.get_width()//8, sheet.get_height()//6), row=row)
    elif boss == 'mecha':
        sprite = frame('boss_mecha_lizard', (clock//6 % 4+4) if cast else clock//8 % 4)
        if sprite is not None:
            return sprite
    else:
        sheet = image_asset('animations/bosses/anim_boss_orochi_idle.png')
        if sheet is not None:
            return sheet_pose(sheet, 6, 4, clock//4 % 24)
    return image_asset(BOSSES[boss]['art'])


def fit(area, height):
    bounds = pygame.Rect(0, 0, WIDTH, height).fit(area)
    bounds.center = area.center
    return bounds


class Painter:
    def __init__(self, surface, header=0):
        self.surface = surface
        top = round(header * surface.get_width() / WIDTH)
        self.s = RenderSurface(surface, (WIDTH, HEIGHT), surface.get_size(), (0, top), desktop_ui=True)

    def text(self, text, x, y, size=15, color=CREAM, center=False, bold=False):
        label = font(self.s.length(size), bold).render(text, True, color)
        position = self.s.point((x, y))
        self.surface.blit(label, label.get_rect(midtop=position) if center else position)

    def panel(self, rect, accent=(69, 127, 146), fill=INK):
        Draw.rect(self.s, fill, rect, border_radius=9)
        Draw.rect(self.s, accent, rect, 1.5, border_radius=9)

    def button(self, rect, label, accent=MUTED):
        self.panel(rect, accent, (16, 44, 64))
        self.text(label, rect.centerx, rect.centery-10, 15, accent, True, True)

    def sprite(self, art, x, y, w, h, angle=0, stretch=False):
        if art is not None:
            image = sprite_at(art, self.s.length(w), self.s.length(h), angle, stretch)
            self.surface.blit(image, image.get_rect(center=self.s.point((x, y))))

    def bar(self, box, amount, color):
        Draw.rect(self.s, (37, 63, 80), box, border_radius=4)
        if amount:
            x, y, w, h = box
            Draw.rect(self.s, color, (x, y, w*amount, h), border_radius=4)

    def shape(self, shape, color, active, beat):
        kind, *p = shape
        s = self.s
        edge = CREAM if active else color
        dark = tuple(channel//4 for channel in color)
        if kind == 'rect':
            l, t, r, b = p
            if active:
                Draw.rect(s, dark, (l, t, r-l, b-t))
                for y in range(round(t)+round(beat*12), round(b), 15):
                    Draw.line(s, color, (l, y), (r, y), 1)
            else:
                for y in range(round(t)+round(beat*20), round(b), 27):
                    for x in range(round(l)+5, round(r)-10, 30):
                        Draw.line(s, dark, (x, y), (x+10, min(b, y+7)), 1.5)
            Draw.rect(s, edge, (l, t, r-l, b-t), 2)
        elif kind == 'line':
            ax, ay, bx, by, width = p
            Draw.line(s, dark, (ax, ay), (bx, by), width*2)
            dx, dy = unit(bx-ax, by-ay)
            for sign in (-1, 1):
                ux, uy = -dy*width*sign, dx*width*sign
                Draw.line(s, color, (ax+ux, ay+uy), (bx+ux, by+uy), 1.5)
            Draw.line(s, edge, (ax, ay), (bx, by), 4 if active else 1)
        elif kind == 'circle':
            x, y, radius = p
            if active:
                Draw.circle(s, dark, (x, y), radius)
            Draw.circle(s, edge, (x, y), radius, 2)
            Draw.circle(s, color, (x, y), max(1, radius*(.3+beat*.55)), 1)
        else:
            x, y, radius, angle, gap = p
            start, end = angle+gap, angle+tau-gap
            def arc(r):
                return [(x+cos(start+(end-start)*i/36)*r, y+sin(start+(end-start)*i/36)*r)
                        for i in range(37)]
            if active:
                Draw.lines(s, dark, False, arc(radius), 18)
            for delta in (-9, 9):
                Draw.lines(s, color, False, arc(max(1, radius+delta)), 1.5)
            Draw.lines(s, edge, False, arc(radius), 4 if active else 1.5)
            for a in (angle-gap, angle+gap):
                Draw.line(s, color, (x, y), (x+cos(a)*radius, y+sin(a)*radius), 1)

    def hazard(self, cast, clock, active_shapes, color):
        age = clock-cast['active_tick']
        kind = cast['kind']
        beat = clock % 18/18
        if kind in ('missile', 'storm'):
            spacing = 24 if kind == 'missile' else 30
            for i, shape in enumerate(shapes(cast, clock, preview=True)):
                if age < i*spacing:
                    self.shape(shape, color, False, beat)
                    self.text(str(i+1), shape[1], shape[2]-10, 16, CREAM, True, True)
                    if kind == 'missile' and i*spacing-age <= 18:
                        self.sprite(image_asset(EFFECTS[kind]), shape[1], shape[2]-(i*spacing-age)*4, 20, 44)
        elif age < 0:
            for shape in shapes(cast, clock, preview=True):
                self.shape(shape, color, False, beat)
        if age < 0:
            x, y = cast['target']
            self.text(f'{NAMES[kind]}  {-age/60:.1f}s', clip(x, 84, 716), clip(y-28, 154, 494),
                      13, CREAM, True, True)
            if kind == 'crescent':
                left, right = cast['safe']
                for x, dx in ((left, 1), (right, -1)):
                    for y in range(170, 519, 30):
                        Draw.lines(self.s, CREAM, False, ((x, y), (x+dx*5, y+4), (x, y+8)), 1.5)
            elif kind == 'storm':
                left, right = cast['safe']
                for x in range(round(left)+16, round(right), 21):
                    Draw.line(self.s, color, (x, 510), (x+10, 510), 1.5)
        for i, shape in enumerate(active_shapes):
            self.shape(shape, color, True, beat)
            if kind == 'geyser':
                l, t, r, b = shape[1:]
                self.sprite(image_asset(EFFECTS[kind]), (l+r)/2, (t+b)/2, 53, b-t, stretch=True)
            elif kind == 'pearl':
                self.sprite(image_asset(EFFECTS[kind]), shape[1], shape[2], 28, 28)
            elif kind == 'crescent':
                l, t, r, b = shape[1:]
                for x in range(round(l)+18+(i//2)*6, round(r)-11, 35):
                    self.sprite(image_asset(EFFECTS[kind]), x, (t+b)/2, 25, 47, -90)
            elif kind == 'slam':
                sheet = image_asset(EFFECTS[kind])
                if sheet is not None:
                    self.sprite(sheet, shape[1], shape[2]-18, 102, 105)


def boss_cards(game, events, selected, choose, close):
    from .duel_view import event_pos, pointer_down

    area = config.SCR.get_rect()
    p = Painter(config.SCR.surface)
    p.s = config.SCR
    wide = area.w >= 700
    w = min(264, (area.w-42)//3) if wide else min(380, area.w-40)
    h = 235 if wide else min(156, (area.h-112)//3)
    cards = []
    p.text('选择本场首领', area.centerx, 24, 25, CREAM, True, True)
    for i, (boss, data) in enumerate(BOSSES.items()):
        x = (area.w-3*w-20)//2+i*(w+10) if wide else (area.w-w)//2
        y = area.centery-h//2 if wide else 65+i*(h+10)
        rect = pygame.Rect(x, y, w, h)
        color = PALETTE[boss]
        cards.append((boss, rect))
        p.panel(rect, color if selected == boss else (69, 112, 132))
        if wide:
            p.sprite(image_asset(data['art']), rect.centerx, y+79, w-20, 140)
            p.text(data['name'], rect.centerx, y+152, 21, color, True, True)
            p.text('  '.join(s[0] for s in data['skills']), rect.centerx, y+185, 13, CREAM, True)
            p.text(f'{i+1}  ' + ('当前选择' if selected == boss else '选择'), rect.centerx, y+208, 13, MUTED, True)
        else:
            p.sprite(image_asset(data['art']), x+64, rect.centery, 114, h-16)
            p.text(data['name'], x+132, y+19, 20, color, bold=True)
            for j, skill in enumerate(data['skills']):
                p.text(skill[0], x+132, y+49+j*20, 14)
            if selected == boss:
                p.text('当前选择', x+132, y+114, 13, MUTED)
    back = pygame.Rect(area.centerx-68, area.h-48, 136, 34)
    p.button(back, '返回房间')
    for event in events:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                close()
                return
            if event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
                choose(cards[event.key-pygame.K_1][0])
                close()
                return
        if pointer_down(event):
            point = event_pos(game, event)
            if back.collidepoint(point):
                close()
                return
            for boss, rect in cards:
                if rect.collidepoint(point):
                    choose(boss)
                    close()
                    return


def reticle(s, boss, point, color):
    x, y = point
    if boss == 'whale':
        Draw.circle(s, CREAM, point, 12, 2)
    elif boss == 'mecha':
        Draw.rect(s, CREAM, (x-11, y-11, 22, 22), 2)
    else:
        Draw.polygon(s, CREAM, ((x,y-15),(x+15,y),(x,y+15),(x-15,y)), 2)
    for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
        Draw.line(s, color, (x+dx*8,y+dy*8), (x+dx*21,y+dy*21), 2)
    Draw.circle(s, CREAM, point, 2)


def draw_scene(p, state, world, slot, boss, touch, view, buttons, paused):
    s = p.s
    board = pygame.Rect(s.rect(ARENA))
    art = background(board.size, image_variant())
    if art:
        p.surface.blit(art, board)
    else:
        p.surface.fill((16, 49, 69), board)
    old_clip = p.surface.get_clip()
    p.surface.set_clip(board)
    clock = world['clock']
    boss_id = world['content_id']
    color = PALETTE[boss_id]
    bx, by = world['boss']
    hx, hy = world['hero']
    stage = world['phase']
    for i in range(17):
        x, y = (i*137)%WIDTH, (i*87-clock*.29)%HEIGHT
        Draw.circle(s, (78, 139, 162), (x, y), 1+i%3, 1)
    Draw.rect(s, (93, 158, 178), (6, 158, 788, 374), 1)
    for x in range(25, 785, 34):
        Draw.line(s, (111, 170, 181), (x, 158), (x+10, 158), 1)
    active = {entry['cast_id']:entry['shapes'] for entry in world['active_shapes']}
    casts = world['pending_casts']
    for cast in casts:
        p.hazard(cast, max(0, clock-1), active.get(cast['cast_id'], ()), color)
    pose = next((c for c in reversed(casts) if c['active_tick']+14 > clock), None)
    p.sprite(boss_sprite(boss_id, clock, pose), bx, by, 248 if boss_id=='orochi' else 206, 145)
    weak = pygame.Rect(bx-WEAK[0]/2, by+11-WEAK[1]/2, *WEAK)
    for x, sx in ((weak.left, 1), (weak.right, -1)):
        for y, sy in ((weak.top, 1), (weak.bottom, -1)):
            Draw.lines(s, CREAM, False, [(x, y+sy*8), (x, y), (x+sx*11, y)], 1.5)
    if world['hero_hp']:
        if clock < world['invulnerable'] or clock < world['dash_until']:
            Draw.circle(s, (127, 213, 246), (hx, hy), 21, 2)
        p.sprite(frame('player1_back', clock//11) or image_asset('players/player1.png'), hx, hy, 36, 40)
        p.sprite(image_asset('weapons/weapon_pistol.png'), hx+11, hy-8, 18, 17, 90)
        Draw.arc(s, CREAM, (hx-12, hy-12, 24, 24), 3.42, 5.99, 1.5)
    for x, y in world['shots']:
        Draw.line(s, (124, 226, 255), (x, y-5), (x, y+9), 4)
        Draw.line(s, CREAM, (x, y-5), (x, y+2), 2)
    if boss and stage in ('combat', 'countdown'):
        reticle(s, boss_id, view.aim, color)
    p.surface.set_clip(old_clip)

    strip = (8, 27, 45)
    Draw.rect(s, strip, (0, -HUD_HEIGHT, WIDTH, HUD_HEIGHT))
    Draw.rect(s, strip, (0, HEIGHT, WIDTH, TOUCH_CONTROLS if touch else DESKTOP_CONTROLS))
    p.panel((109, -55, 582, 49))
    p.text(f"第 {world['round_id']} 回合 · {BOSSES[boss_id]['name']}", 125, -50, 14, color, bold=True)
    p.text(f"{world['boss_hp']} / 150", 346, -50, 14)
    p.bar((125, -25, 272, 7), world['boss_hp']/150, color)
    p.text(f"生命 {world['hero_hp']} / 5", 422, -50, 14)
    p.bar((422, -25, 96, 7), world['hero_hp']/5, (126, 232, 177))
    p.text(f"{(5400-clock)/60:04.1f} 秒", 604, -44, 21, CREAM, True, True)
    if stage == 'combat' and boss and not view.confirm_leave:
        skill_hud(p, world, buttons, slot, touch, color)
    elif stage == 'combat' and not boss:
        label = '自动射击开启' if view.auto else 'J 射击 · K 闪避'
        remaining = world['dash_cooldown']
        feedback = world['feedback'].get(str(slot), world['feedback'].get(slot))
        if remaining:
            label += f'  ·  闪避 {remaining/60:.1f}s'
        if feedback:
            label += '  ·  ' + ERRORS[feedback[1]]
        p.text(label, 183 if touch else 15, 557, 14)
        incoming = min((c for c in casts if c['active_tick'] >= clock),
                       key=lambda c: c['active_tick'], default=None)
        if incoming:
            x, y = incoming['target']
            direction = '左侧' if x < hx-45 else '右侧' if x > hx+45 else '近身'
            p.text(f"{direction}预警 · {NAMES[incoming['kind']]}", 185 if touch else 15, 580, 14, color)
    labels = {'exit':'退出', 'leave':'确认离开', 'cancel':'取消', 'pause':'继续' if paused else '暂停',
              'move':'移动摇杆', 'aim':'拖动准星', 'dash':'闪避', 'shoot':'射击',
              'auto':'自动开' if view.auto else '自动关', 'round_ready':'已了解',
              'rematch_ready':'等待队友' if slot in world.get('rematch', []) else '同首领再赛',
              'back_lobby':'等待确认' if world.get('back_lobby') else '回房间'}
    if view.confirm_leave and stage != 'result':
        p.panel((170, 190, 460, 193), (230, 160, 105))
        p.text('离开将判为弃权', 400, 238, 25, CREAM, True, True)
    elif stage == 'result':
        result_panel(p, world)
    elif stage == 'swap':
        p.panel((129, 171, 542, 253), color)
        p.text('交换岗位', 400, 190, 29, color, True, True)
        round_line(p, world['first_round_result'], 249)
        p.text('下一轮你是' + ('冒险者' if boss else '首领') +
               f" · {ceil(world['remaining']/60)} 秒后开始倒计时", 400, 305, 17, CREAM, True)
        if slot in world['round_ready']:
            labels['round_ready'] = '已了解 · 等待队友'
    elif stage == 'countdown':
        p.panel((155, 177, 490, 174), color)
        p.text('你的岗位 · ' + ('首领' if boss else '冒险者'), 400, 198, 25, color, True, True)
        line = ('WASD 移动 · 鼠标或方向键瞄准 · J/K/L 施放' if boss else
                'WASD 或方向键移动 · J 射击 · K 闪避')
        if touch:
            line = '移动摇杆 · 点场地或拖准星 · 轻点技能' if boss else '移动摇杆 · 射击或自动射击 · 闪避'
        p.text(line, 400, 243, 17, CREAM, True)
        p.text(str(ceil(world['remaining']/60)), 400, 272, 43, CREAM, True, True)
    elif clock < 60:
        p.text(f'准备期 · {(60-clock)/60:.1f}s', 400, 205, 25, color, True, True)
    for name, rect in buttons.items():
        if name in labels:
            p.button(rect, labels[name], color if name in ('aim', 'dash', 'round_ready') else MUTED)
    if 'move' in buttons:
        rect = buttons['move']
        dx, dy = view.stick
        Draw.circle(s, (57, 103, 124), (rect.centerx, rect.y+62), 24, 1.5)
        Draw.circle(s, MUTED, (rect.centerx+dx*16, rect.y+62+dy*16), 8)
        # The label sits above the joystick's motion range.
        Draw.rect(s, (16, 44, 64), (rect.x+27, rect.y+29, rect.w-54, 24))
        p.text('移动摇杆', rect.centerx, rect.y+7, 15, MUTED, True, True)
    if paused and stage != 'result' and not view.confirm_leave:
        reason = {'disconnected':'等待队友重连', 'suspended':'对局因后台挂起而暂停',
                  'orientation_mismatch':'请双方切回房间指定的屏幕方向',
                  'server_error':'服务异常'}.get(state['pause_reason'], '对局已暂停')
        p.panel((202, 424, 396, 57), color)
        p.text(reason, 400, 440, 18, CREAM, True, True)


def skill_hud(p, world, buttons, slot, touch, color):
    feedback = world['feedback'].get(str(slot), world['feedback'].get(slot))
    energy = world['energy']
    p.text(f'能量 {int(energy)} / 100', 181 if touch else 15, 544, 14, color, bold=True)
    p.bar((298 if touch else 131, 549, 105, 8), energy/100, color)
    pending = sorted((c for c in world['pending_casts'] if c['active_tick'] >= world['clock']),
                     key=lambda c: c['active_tick'])
    if pending:
        p.text('  →  '.join(NAMES[c['kind']] for c in pending),
               183 if touch else 15, 565, 13, CREAM)
    for i, (skill, cd) in enumerate(zip(BOSSES[world['content_id']]['skills'], world['cooldowns'])):
        name, _, _, _, _, cost = skill
        action = f'cast_{i+1}'
        info = f'{cost} 能量' + (f' · {cd/60:.1f}s' if cd else '')
        if feedback and feedback[0] == action:
            info = ERRORS[feedback[1]]
        rect = buttons[action] if touch else pygame.Rect(263+i*172, 550, 164, 49)
        accent = color if not cd and energy >= cost else MUTED
        p.panel(rect, accent)
        p.text(f'{chr(74+i)}  {name}', rect.centerx, rect.y+6, 15, accent, True, True)
        p.text(info, rect.centerx, rect.y+(43 if touch else 27), 13, CREAM, True)


def round_line(p, row, y, metric=None):
    items = [
        (187, f"P{row['slot']} 冒险者", None), (323, f"{row['survival_tick']/60:.2f}s", 'survival_tick'),
        (425, f"{row['damage']} 伤害", 'damage'), (518, f"{row['hp']} HP", 'hp'),
        (608, '已击倒' if row['defeated'] else '未击倒', 'defeated')]
    for x, label, key in items:
        decisive = key is not None and (key == metric or key == 'survival_tick' and metric == 'defeat_tick')
        p.text(label, x, y, 15, (255, 217, 138) if decisive else CREAM, True, decisive)


def result_panel(p, world):
    result = world['result']
    metric = result['metric']
    p.panel((118, 128, 564, 338), (117, 205, 227))
    winner = result['winner']
    title = f'P{winner} 获胜' if winner else '比赛中止' if metric == 'aborted' else '平局'
    p.text(title, 400, 150, 34, CREAM, True, True)
    p.text(METRICS[metric], 400, 206, 19, (255, 217, 138), True, True)
    for i, row in enumerate(result['rounds']):
        y = 247+i*61
        p.text(f"第 {i+1} 回合 · P{3-row['slot']} 首领" + (' · 未完成' if row.get('partial') else ''),
               142, y, 13, MUTED)
        round_line(p, row, y+22, metric)
