"""Draw the race directly at presentation resolution."""
from functools import lru_cache
from math import atan2, degrees, pi, sin

import pygame

from .. import config
from ..asset_loader import cover_image_asset, image_asset, image_variant
from ..render import Draw, RenderSurface
from .tide_race import VIEW, clamp, deep_y, wave

WHITE = (234, 252, 250)
GOLD = (255, 209, 116)
CYAN = (102, 238, 245)
INK = (10, 48, 65)
WATER = {'lighthouse': (26, 130, 156), 'reef': (44, 138, 149), 'storm': (37, 100, 132)}


@lru_cache(maxsize=36)
def font(size, bold=False):
    return config.make_font(size, bold)


@lru_cache(maxsize=3)
def stage_art(track_id, background, size, variant):
    width, height = size
    sky = cover_image_asset(f'modes/tide_race/{track_id}.png', (width, round(height*.59)), variant=variant)
    water_height = height-round(height*312/540)
    stem = f'backgrounds/{background}'
    art = cover_image_asset(stem+'.jpg', (width, water_height), variant=variant)
    if art is None:
        art = cover_image_asset(stem+'.png', (width, water_height), variant=variant)
    water = None
    if art is not None:
        art = art.convert_alpha()
        alpha = pygame.Surface(art.get_size(), pygame.SRCALPHA)
        for y in range(water_height):
            a = int(215*min(1, y / max(1, height*.16)))
            pygame.draw.line(alpha, (255, 255, 255, a), (0, y), (width, y))
        art.blit(alpha, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        water = pygame.Surface(art.get_size()).convert()
        water.fill(WATER[track_id])
        water.blit(art, (0, 0))
    return sky.convert() if sky is not None else None, water


def field_rect(target):
    view = pygame.Rect((0, 0), VIEW).fit(target.get_rect())
    view.center = target.get_rect().center
    return view


def fmt(tick):
    if tick is None:
        return '—'
    return f'{tick/60:06.2f}s'


def draw_race(target, state, track, slot=1, *, ghost=None, best=None, tip=False, controls=(), overlay=None):
    view = field_rect(target)
    if view.size != target.get_size():
        target.fill((5, 24, 39))
    pixels = target.subsurface(view)
    s = RenderSurface(pixels, VIEW, view.size, (0, 0), desktop_ui=True)
    tick = state.get('visual_clock', state['clock'])
    clock = state['clock']
    track_id = state['track_id']
    racers = state['racers']
    me = next(r for r in racers if r['slot'] == slot)
    focus = me
    if me['finish_tick'] is not None and state['result'] is None:
        focus = next((r for r in racers if r['finish_tick'] is None and not r['left']), me)
    turn = clamp((focus['x']-track['landmark']+350)/700, 0, 1)
    sweep = 52*sin(pi*turn) if track_id == 'lighthouse' else 0
    camera = clamp(focus['x']-235+sweep, -115, track['length']-820)

    def label(value, x, y, size=16, color=WHITE, bold=False, center=False):
        img = font(max(1, s.length(size)), bold).render(value, True, color)
        where = s.point((x, y))
        pixels.blit(img, img.get_rect(midtop=where) if center else where)

    def sprite(name, x, y, width, height, angle=0, alpha=255):
        art = image_asset(name, (s.length(width), s.length(height)))
        if art is None:
            return
        if angle:
            art = pygame.transform.rotate(art, angle)
        if alpha < 255:
            art = art.copy()
            art.set_alpha(alpha)
        pixels.blit(art, art.get_rect(center=s.point((x, y))))

    def pill(rect, title, color=WHITE, fill=INK, size=15):
        x, y, w, h = rect
        Draw.rect(s, fill, rect, border_radius=10)
        label(title, x+w/2, y+(h-size)/2-2, size, color, True, True)

    sky, under = stage_art(track_id, track['background'], view.size, image_variant())
    if sky is None:
        pixels.fill((114, 180, 192))
    else:
        pixels.blit(sky, (0, 0))
    landmark = track['landmark']-camera
    if -130 < landmark < 1090:
        if track_id == 'lighthouse':
            beam = 120*sin(tick/31)
            Draw.polygon(s, (249, 222, 164), [(landmark, 117), (landmark+beam, 86), (landmark+beam, 127)])
            Draw.polygon(s, (58, 77, 82), [(landmark-75,276),(landmark-49,220),(landmark+29,218),(landmark+73,276)])
            Draw.polygon(s, (226, 221, 190), [(landmark-22,229),(landmark-13,128),(landmark+13,128),(landmark+22,229)])
            for y in (151, 191):
                Draw.line(s, (157, 69, 60), (landmark-15,y), (landmark+15,y), 12)
            Draw.rect(s, (46, 64, 73), (landmark-20,112,40,18))
            Draw.rect(s, GOLD, (landmark-11,113,22,12))
            Draw.polygon(s, (150, 62, 50), [(landmark-25,112),(landmark,94),(landmark+25,112)])
        else:
            color = (111, 81, 76) if track_id == 'reef' else (59, 83, 100)
            Draw.polygon(s, color, [(landmark-95,276),(landmark-55,222),(landmark-31,233),
                                    (landmark+28,193),(landmark+61,218),(landmark+107,276)])

    points = [(x, wave(track, camera+x, tick)[0]) for x in range(0, 961, 5)]
    bottom = 312 if under is not None else 540
    Draw.polygon(s, WATER[track_id], [*points, (960, bottom), (0, bottom)])
    if under is not None:
        pixels.blit(under, s.point((0, bottom)))
    for level in (7, 16, 26, 41, 55):
        strokes = [(x, y+level+sin((x+camera)/85+level/7)*level/12) for x, y in points]
        Draw.lines(s, (49+level//2, 159-level//2, 176-level//3), False, strokes, 2)
    Draw.lines(s, (85, 202, 213), False, points, 6)
    Draw.lines(s, (184, 247, 245), False, points, 2)
    for x, y in points[::3]:
        wx = x+camera
        if wave(track, wx, tick)[1]:
            Draw.line(s, (223, 252, 248), (x, y-2), (x+7, y-2), 2)
            Draw.circle(s, CYAN, (x+3, y+9+(int(wx)//7)%9), 1.2)
    if track_id == 'storm':
        for i in range(1, len(points)-1):
            x, y = points[i]
            if y <= points[i-1][1] and y < points[i+1][1] and wave(track, camera+x, tick)[1]:
                Draw.line(s, (134,178,190), (x,y-31), (x,y-5), 2)
                Draw.polygon(s, GOLD, [(x,y-31), (x-24,y-26), (x,y-21)])
        if any(lo <= me['x'] < hi for lo, hi, _ in track.get('currents', [])):
            pill((695,121,151,30), '← 逆风海域', GOLD, size=14)
    if track_id == 'lighthouse' and track['landmark']+380 <= focus['x'] < track['landmark']+820:
        pill((397,129,166,29), '绕过灯塔 · 返航', GOLD, size=14)

    start, end = track['branch']
    if start-25 <= camera+960 and end+25 >= camera:
        centerline = [(x, deep_y(track, camera+x)) for x in range(0, 961, 16) if start <= camera+x <= end]
        if len(centerline) > 1:
            for i in range(0, len(centerline)-1, 2):
                Draw.line(s, (83, 186, 199), centerline[i], centerline[i+1], 2)
        for i in range(7):
            x = start-camera-75+i*15+(tick/2)%14
            if -20 < x < 970:
                y = 294+(i%3)*9
                Draw.polygon(s, CYAN, [(x-5,y-3), (x+5,y), (x-5,y+3), (x-3,y)])
        for marker, title in ((start, '↓ 水下捷径'), (end, '航道汇合')):
            x = marker-camera
            if -80 <= x <= 1040:
                pill((x-55, 325, 110, 27), title, CYAN, size=13)
    for lane, pos, y, w, h in track['obstacles']:
        x = pos-camera
        if x+w < 0 or x > 960:
            continue
        if lane == 'deep':
            color = (149, 75, 88) if track_id == 'reef' else (42, 80, 96)
            Draw.polygon(s, color, [(x,y+h), (x,y+h*.28), (x+w*.19,y), (x+w*.64,y+h*.10),
                                    (x+w*.82,y), (x+w,y+h*.32), (x+w,y+h)])
            for j in range(1, 7):
                posx = x+w*j/7
                Draw.line(s, (color[0]+32,color[1]+25,color[2]+18), (posx,y+h*.26),(posx-6,y+h*.63),2)
        else:
            Draw.line(s, (184, 98, 54), (x+w/2, y), (x+w/2, y+h), 5)
            sprite('effects/boss_trident_gold.png', x+w/2, y+10, 16, 30)
            Draw.ellipse(s, (246, 145, 54), (x,y+h*.48,w,h*.46))
            Draw.line(s, WHITE, (x+5,y+h*.66), (x+w-5,y+h*.66), 3)
    points_of_interest = [0, *track['gates'], track['length']]
    for i, marker in enumerate(points_of_interest):
        x = marker-camera
        if not -45 <= x <= 1005:
            continue
        y = wave(track, marker, tick)[0]
        finish = i == 4
        color = GOLD if finish else CYAN
        Draw.line(s, color, (x, y-95), (x, y+45), 3)
        if finish:
            for row in range(3):
                for col in range(5):
                    Draw.rect(s, WHITE if (row+col)%2 else INK, (x+col*9,y-95+row*9,9,9))
        else:
            Draw.polygon(s, color, [(x,y-95),(x+33,y-85),(x,y-75)])
        label('终点' if finish else f'计时门 {i}' if i else '起点', x+10,y-121,14,WHITE,True)

    if ghost:
        x, y, pose, _ = ghost
        if -80 <= x-camera <= 1040:
            sprite('enemies/enemy_goldfish.png',x-camera,y,56,48,19 if pose=='glide' else -20 if pose=='dive' else 0,100)
            label('最佳航迹',x-camera,y-42,11,CYAN,center=True)
    for r in sorted(racers, key=lambda r: r['slot']==slot):
        x,y = r['x']-camera,r['y']
        if r['left'] and r['finish_tick'] is None:
            continue
        if x < -80 or x > 1040:
            label(f'{"◀" if x < 0 else "▶"} P{r["slot"]} {abs(r["x"]-me["x"]):.0f}px',
                  74 if x < 0 else 886, 231, 15, GOLD, True, True)
            continue
        if r['slot'] != slot and abs(r['x']-me['x'])<44 and abs(r['y']-me['y'])<25:
            y -= 23
        combo = r['combo']
        for j in range(9+combo*5):
            tail = x-25-j*4
            py = y+sin(j*.8+tick*.48)*(3+j*.20)
            Draw.circle(s, CYAN if j%2 else WHITE, (tail,py), max(.8,3-j*.09))
        if combo:
            sprite('effects/orochi_bubble_mint.png',x-24,y,32+combo*7,33,alpha=125)
        pose = r['pose']
        suit = 'goldfish' if r['slot']==1 else 'anglerfish'
        tilt = 0 if pose in ('swim','reset') else -clamp(degrees(atan2(r['vy'],max(1,r['speed']))),-34,42)
        if pose == 'glide':
            Draw.polygon(s, (162, 226, 226), [(x-10,y+3),(x-32,y-25),(x+15,y-4),(x+2,y+9)])
            Draw.polygon(s, (108, 187, 209), [(x-13,y+8),(x-22,y+26),(x+10,y+6)])
        sprite(f'enemies/enemy_{suit}.png',x,y,59 if pose!='dive' else 51,49 if pose!='dive' else 34,tilt)
        label(f'P{r["slot"]}' if len(racers)>1 else '',x,y-46,13,GOLD,True,True)

    Draw.rect(s, INK, (22,16,916,94), border_radius=14)
    label(track['name'],40,27,19,WHITE,True)
    label(fmt((me['finish_tick']-state['start_tick']) if me['finish_tick'] is not None else clock),
          40,57,28,GOLD,True)
    label(f'{me["speed"]:.0f} px/s',184,61,16)
    label(f'接浪 ×{me["combo"]}',307,33,20,CYAN,True)
    splits = [fmt(g-state['start_tick']) for g in me['gates']]
    label('分段  '+'  /  '.join(splits+['—']*(3-len(splits))),306,67,15)
    if best is not None:
        label(f'个人最佳 {fmt(best)}',754,34,16,GOLD)
    if len(racers)>1:
        other = next(r for r in racers if r['slot'] != slot)
        delta = other['x']-me['x']
        label(f'对手 {"领先" if delta > 0 else "落后" if delta < 0 else "并行"} {abs(delta):.0f}px',744,31,15)
        label('对手分段  '+(' / '.join(fmt(g-state['start_tick']) for g in other['gates']) or '—'),648,67,14,CYAN)
    Draw.line(s, (73, 125, 139), (38,100), (918,100), 3)
    for p in track['gates']:
        Draw.circle(s, WHITE, (38+880*p/track['length'],100),3)
    for r in racers:
        Draw.circle(s, GOLD if r['slot']==slot else CYAN, (38+880*r['x']/track['length'],100),5)

    if state['race_phase'] in ('grid','countdown'):
        count=max(1,(state['start_tick']-state['tick']+59)//60)
        pill((437,137,86,69), str(count), GOLD, size=43)
    elif tick < 50:
        pill((400,130,160,34), '出发！', GOLD, size=19)
    if tip and tick < 545:
        Draw.rect(s, INK, (305,355,350,94), border_radius=13)
        label('浪尖跃 · 下坡潜',480,366,18,GOLD,True,True)
        trace=[(i,416-13*sin((i-354)*2*pi/96)) for i in range(350,611,3)]
        Draw.lines(s,CYAN,False,trace,2)
        phase=(state['tick']%108)/108
        bx=354+phase*252
        by=416-13*sin((bx-354)*2*pi/96)-max(0, 22*sin((phase-.08)*4*pi))
        sprite('enemies/enemy_goldfish.png',bx,by-8,27,22)
    if state['race_phase']=='racing' and me['finish_tick'] is not None:
        pill((304,145,352,36),f'已冲线 · 对手剩余 {fmt(max(0,state["deadline_tick"]-state["tick"]))}',GOLD)
    if controls and max(rect[1]+rect[3] for _, rect in controls) > VIEW[1]:
        extended = pygame.Rect(view.x, view.y, view.w, target.get_height()-view.y)
        pixels = target.subsurface(extended)
        s = RenderSurface(pixels, VIEW, view.size, (0, 0), desktop_ui=True)
    for name, rect in controls:
        if name == '方向':
            x,y,w,h=rect
            Draw.circle(s, (19,64,83), (x+w/2,y+h/2), w/2)
            Draw.circle(s, (74,155,170), (x+w/2,y+h/2), w/2, 2)
            label('↔',x+w/2,y+h*.09,21,CYAN,True,True)
            label('↓',x+w/2,y+h*.32,18,CYAN,True,True)
        else:
            pill(rect, name, WHITE, size=16)
    if overlay:
        title, detail, buttons = overlay
        Draw.rect(s, (9,42,58), (224,157,512,247), border_radius=18)
        Draw.rect(s, (70,144,158), (224,157,512,247), 2, border_radius=18)
        label(title,480,179,28,GOLD,True,True)
        for i, row in enumerate(detail):
            label(row,480,226+i*25,15,WHITE,center=True)
        for caption, rect, focused in buttons:
            pill(rect, caption, WHITE, (45,121,137) if focused else (25,77,94), 15)
