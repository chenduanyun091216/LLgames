"""Full-resolution presentation for salvage. Layout and collisions live in content."""
from functools import lru_cache
import math

import pygame

from ..asset_loader import cover_image_asset, image_asset, image_variant, scale_surface_cached
from ..render import Draw, RenderSurface
from ..run_gun_art import flipped, font_at
from .deep_dive import CONTENT, HZ, RULES, TREASURES, center, inside

SIZE = (800, 540)
INK = (224, 245, 242)
MINT = (114, 235, 205)
GOLD = (248, 201, 119)
MUTED = (143, 178, 192)
PANEL = (9, 29, 44)
THEMES = {'wreck': ((33, 31, 39), (117, 79, 64)),
          'grotto': ((29, 25, 51), (109, 85, 143)),
          'observatory': ((16, 34, 44), (68, 126, 143))}
TOOL_SYMBOL = {'cutter': '◇', 'lift_bag': '◈', 'sonar': '◎'}
ART = 'modes/deep_dive/'


@lru_cache(maxsize=2)
def background(key, size, variant):
    stem = 'backgrounds/' + key
    for suffix in ('.jpg', '.png'):
        art = cover_image_asset(stem + suffix, size, variant=variant)
        if art is not None:
            break
    else:
        return None
    tinted = art.convert()
    tinted.fill((120, 158, 177), special_flags=pygame.BLEND_RGB_MULT)
    return tinted


@lru_cache(maxsize=24)
def walls(sea, open_ids):
    data = CONTENT['maps'][sea]
    rooms = [*data['rooms'].values(), *(edge['rect'] for edge in data['edges'] if edge['id'] in open_ids)]
    width, height = data['size']
    xs = sorted({0, width, *(v for x, y, w, h in rooms for v in (x, x+w))})
    ys = sorted({0, height, *(v for x, y, w, h in rooms for v in (y, y+h))})
    occupied = {(i, j) for i in range(len(xs)-1) for j in range(len(ys)-1)
                if not any(inside(rect, (xs[i]+xs[i+1])/2, (ys[j]+ys[j+1])/2) for rect in rooms)}
    tiles, edges = [], []
    for i, j in sorted(occupied):
        x, y, right, bottom = xs[i], ys[j], xs[i+1], ys[j+1]
        tiles.append((x, y, right-x, bottom-y))
        for neighbor, line in (((i-1,j),(x,y,x,bottom)), ((i+1,j),(right,y,right,bottom)),
                               ((i,j-1),(x,y,right,y)), ((i,j+1),(x,bottom,right,bottom))):
            a, b = neighbor
            if 0 <= a < len(xs)-1 and 0 <= b < len(ys)-1 and neighbor not in occupied:
                edges.append(line)
    return tiles, edges


@lru_cache(maxsize=12)
def wall_pattern(sea, size, variant):
    art = image_asset(ART + 'wall_' + sea + '.png')
    if art is None:
        return None
    tile = scale_surface_cached(art, size)
    mirror = flipped(tile)
    combined = pygame.Surface((size[0]*2,size[1]*2)).convert()
    combined.blit(tile, (0,0))
    combined.blit(mirror, (size[0],0))
    combined.blit(pygame.transform.flip(tile,False,True), (0,size[1]))
    combined.blit(pygame.transform.flip(mirror,False,True), size)
    return combined


@lru_cache(maxsize=2)
def lamp():
    art = pygame.Surface((360, 320), pygame.SRCALPHA)
    for n in range(32, 0, -1):
        distance = n * 10
        color = (int((33-n)*1.6), int((33-n)*1.9), int((33-n)*1.5), 255)
        pygame.draw.polygon(art, color, [(20,160),
            *((20+distance*math.cos(a/100), 160+distance*math.sin(a/100))
              for a in range(-74, 75, 7))])
    return art


@lru_cache(maxsize=10)
def rotated_lamp(size, angle):
    art = pygame.transform.rotate(lamp(), angle)
    return pygame.transform.smoothscale(art, (max(1,round(art.get_width()*size)),
                                               max(1,round(art.get_height()*size))))


class Paint:
    def __init__(self, target):
        view = pygame.Rect((0, 0), SIZE).fit(target.get_rect())
        view.center = target.get_rect().center
        if view.size != target.get_size():
            target.fill((5, 18, 29))
        self.pixels = target.subsurface(view)
        self.s = RenderSurface(self.pixels, SIZE, view.size, (0, 0), desktop_ui=True)

    def text(self, value, x, y, size=16, color=INK, bold=False):
        face = font_at(max(1, self.s.length(size)), bold)
        self.pixels.blit(face.render(str(value), True, color), self.s.point((x,y)))

    def rect(self, color, box, width=0, radius=0):
        Draw.rect(self.s, color, box, width, radius)

    def line(self, color, a, b, width=1):
        Draw.line(self.s, color, a, b, width)

    def circle(self, color, point, radius, width=0):
        Draw.circle(self.s, color, point, radius, width)

    def art(self, key, x, y, width, height, reverse=False, external=False):
        sprite = image_asset(key if external else ART + key + '.png')
        if sprite is None:
            return
        fitted = sprite.get_rect().fit((0,0,self.s.length(width),self.s.length(height)))
        if not fitted.width or not fitted.height:
            return
        image = scale_surface_cached(sprite, fitted.size)
        if reverse:
            image = flipped(image)
        self.pixels.blit(image, image.get_rect(center=self.s.point((x,y))))

    def backdrop(self, key):
        art = background(key, self.pixels.get_size(), image_variant())
        if art is None:
            self.pixels.fill((17,50,70))
        else:
            self.pixels.blit(art, (0,0))

    def button(self, box, label, selected=False):
        x,y,w,h = box
        self.rect((25,71,84) if selected else (15,42,58), box, radius=7)
        self.rect(MINT if selected else (65,109,126), box, 1, 7)
        self.text(label, x+10,y+(h-17)/2, 15, MINT if selected else INK, True)

    def world(self, dive, pilot):
        self.backdrop(dive.map['background'])
        ox = max(0, min(dive.x-400, dive.map['size'][0]-800))
        oy = max(0, min(dive.y-240, dive.map['size'][1]-540))

        def point(x, y):
            return x-ox, y-oy

        def visible(x,y, margin=28):
            return -margin <= x-ox <= 800+margin and -margin <= y-oy <= 540+margin

        base, trim = THEMES[dive.sea]
        tiles, seams = walls(dive.sea, tuple(sorted(dive.opened)))
        fx, fy = dive.facing
        angle = round(math.degrees(math.atan2(-fy, fx))/15)*15
        light = rotated_lamp(round(self.s.scale, 4), angle)
        reach = pygame.Vector2(160,0).rotate(-angle)
        self.pixels.blit(light, light.get_rect(center=self.s.point(point(dive.x+reach.x,dive.y+reach.y))),
                         special_flags=pygame.BLEND_RGB_ADD)
        for i in range(40):
            x = (i*137-ox*.28+7*math.sin(dive.tick*.018+i))%800
            y = (i*83-oy*.22-dive.tick*(.12+i%4*.05))%540
            self.circle((79,155,169),(x,y),1+i%3,1)
        art = wall_pattern(dive.sea, (self.s.length(205),self.s.length(410)),image_variant())
        world_offset = self.s.point(point(0,0))
        for x,y,w,h in tiles:
            if x < ox+800 and x+w > ox and y < oy+540 and y+h > oy:
                if art is None:
                    self.rect(base, (*point(x,y),w,h))
                    continue
                left,top = self.s.point(point(x,y))
                right,bottom = self.s.point(point(x+w,y+h))
                area = pygame.Rect(left,top,right-left,bottom-top).clip(self.pixels.get_rect())
                tw,th = art.get_size()
                for x0 in range(area.left-(area.left-world_offset[0])%tw, area.right, tw):
                    for y0 in range(area.top-(area.top-world_offset[1])%th, area.bottom, th):
                        rect = pygame.Rect(x0,y0,tw,th).clip(area)
                        self.pixels.blit(art,rect.topleft,(rect.x-x0,rect.y-y0,rect.w,rect.h))
        for x,y,r,b in seams:
            if max(x,r)<ox or min(x,r)>ox+800 or max(y,b)<oy or min(y,b)>oy+540:
                continue
            self.line(trim,point(x,y),point(r,b),5)
            length = math.hypot(r-x,b-y)
            interval = 25 if dive.sea == 'grotto' else 42
            for offset in range(12, round(length), interval):
                a, c = x+(r-x)*offset/length, y+(b-y)*offset/length
                if visible(a,c):
                    if dive.sea == 'grotto':
                        Draw.polygon(self.s, (88,120,143), [point(a-5,c+5),point(a+2,c-4),point(a+6,c+4)])
                    else:
                        self.circle((159,142,117) if dive.sea == 'wreck' else (100,169,177),point(a,c),2)
        for edge in dive.edges:
            x,y,w,h = edge['rect']
            cx,cy = center(edge['rect'])
            if not visible(cx,cy,140):
                continue
            if edge['gate'] and edge['id'] not in dive.opened:
                horizontal = w>h and edge['a'] in ('entry','lower') and edge['b'] in ('vault','far','middle')
                box = (cx-12,y,24,h) if horizontal else (x,cy-12,w,24)
                self.rect((76,71,70),(*point(*box[:2]),*box[2:]),radius=4)
                if horizontal:
                    self.line(GOLD,point(cx,y+7),point(cx,y+h-7),3)
                else:
                    self.line(GOLD,point(x+7,cy),point(x+w-7,cy),3)
                progress = dive.cut.get(edge['id'],0)/(HZ*RULES['cutterSeconds'])
                if progress:
                    self.rect(MINT,(*point(cx-24,cy-20),48*progress,4))
                if dive.scanned(cx,cy):
                    self.rect(MINT,(*point(*box[:2]),*box[2:]),2,4)
            elif edge['id'] in dive.seen_edges:
                self.circle(MINT,point(cx,cy),5,1)
                self.circle((42,139,139),point(cx,cy),10,1)
        home_x,home_y = center(dive.map['dock'])
        self.rect((37,94,103),(*point(*dive.map['dock'][:2]),*dive.map['dock'][2:]),1,8)
        self.art('side_view/dock.png',home_x-ox,home_y-oy-48,190,55,external=True)
        self.text('母船 · 泊位',*point(home_x-44,home_y-35),13,MINT,True)
        ax,ay = dive.map['air']
        if visible(ax,ay):
            self.art('air',*point(ax,ay),32,45)
            self.text('补气' if not dive.air_used else '已用',*point(ax-15,ay+23),13,MINT)
        sx,sy = dive.map['shaft']
        if visible(sx,sy):
            for k in range(3):
                yy=sy-27-k*15
                Draw.lines(self.s,GOLD,False,[point(sx-11,yy+6),point(sx,yy),point(sx+11,yy+6)],2)
            self.text('起吊井',*point(sx-25,sy+26),13,GOLD)
        glass = dive.map['glass']
        if glass and dive.x > 860 and visible(glass[0],glass[1]):
            gx,gy,gw,gh = glass
            self.rect((63,165,179),(*point(gx,gy-12),gw,gh+24),2,8)
            crown = next(item for item in dive.items.values() if item['treasure_id']=='crown')
            if crown['state']=='world':
                self.art('crown',*point(gx+gw/2,gy+5),32,25)
                self.text('观察窗',*point(gx+1,gy+26),11,MUTED)
        if dive.tick - dive.sonar_at < HZ*RULES['sonarSeconds']:
            wave = ((dive.tick-dive.sonar_at)%60)/60
            self.circle((84,180,185),point(dive.x,dive.y),max(2,420*wave),1)
        for item in dive.items.values():
            x,y = item['x'],item['y']
            if item['state']=='in_transit':
                remaining = (item['arrival']-dive.tick)/(HZ*RULES['transitSeconds'])
                y = sy*remaining
                if visible(sx,y):
                    self.art('bag',*point(sx,y),43,45)
                    self.art(item['treasure_id'],*point(sx,y+22),28,24)
            elif item['state']=='world' and visible(x,y) and (dive.visible(x,y) or dive.scanned(x,y)):
                self.circle((97,161,161),point(x,y),25,1)
                self.art(item['treasure_id'],*point(x,y),55,49)
                if dive.scanned(x,y):
                    self.circle(MINT,point(x,y),29,2)
                    self.text(TREASURES[item['treasure_id']][0],*point(x-26,y-44),12,MINT)
        if dive.demo_at and dive.demo_at-300 <= dive.tick < dive.demo_at:
            self.art('bag', *point(1045, 314-(dive.tick-dive.demo_at+300)*.7), 40, 43)
        route, seconds = dive.return_route()
        if route:
            nx,ny=next((p for p in route if math.dist(p,(dive.x,dive.y)) > 20),route[-1])
            direction = pygame.Vector2(nx-dive.x,ny-dive.y)
            if direction.length() > 20:
                direction.scale_to_length(42)
                arrow = pygame.Vector2(point(dive.x,dive.y)) + direction
                wing = direction.normalize().rotate(144)*11
                Draw.lines(self.s,MINT,False,[arrow+wing,arrow,arrow+wing.rotate(72)],2)
        self.art('sub',*point(dive.x,dive.y),73,55,reverse=fx<0)
        self.art(pilot,*point(dive.x+(-17 if fx<0 else 17),dive.y+1),19,20,external=True)
        return seconds

    def minimap(self, dive):
        box = (608, 10, 180, 118)
        self.rect(PANEL, box, radius=8)
        self.text('已探索海图',620,15,12,MUTED)
        scale = min(154/dive.map['size'][0], 82/dive.map['size'][1])
        def point(x,y): return 620+x*scale,35+y*scale
        for name in dive.seen_rooms:
            x,y,w,h = dive.rooms[name]
            self.rect((27,74,85),(*point(x,y),w*scale,h*scale),radius=2)
        for edge in dive.edges:
            if edge['id'] in dive.seen_edges:
                x,y,w,h=edge['rect']
                self.rect(MINT if edge['id'] in dive.opened else GOLD,(*point(x,y),w*scale,h*scale))
        route,_=dive.return_route()
        if route:
            Draw.lines(self.s,(80,167,152),False,[point(dive.x,dive.y),*(point(x,y) for x,y in route)])
        self.circle(GOLD,point(*center(dive.map['dock'])),4)
        self.circle(INK,point(dive.x,dive.y),3)
