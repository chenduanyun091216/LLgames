"""Fixed-step, window-independent rules for a single salvage expedition."""
import heapq
import json
import math
from pathlib import Path
from uuid import uuid4


CONTENT_PATH = Path(__file__).resolve().parents[2] / 'assets/modes/deep_dive/content.json'
CONTENT = json.loads(CONTENT_PATH.read_text(encoding='utf-8'))
RULES = CONTENT['rules']
TREASURES = CONTENT['treasures']
HZ = RULES['hz']
RADIUS = 12


def inside(rect, x, y, inset=0):
    left, top, width, height = rect
    return left + inset <= x <= left + width - inset and top + inset <= y <= top + height - inset


def center(rect):
    x, y, w, h = rect
    return x + w / 2, y + h / 2


class Dive:
    def __init__(self, sea, tools, seed=0, teaching=False, run_id=None):
        self.sea = sea
        self.map = CONTENT['maps'][sea]
        self.tools = tuple(tools)
        self.seed = seed & 0xFFFFFFFF
        self.teaching = teaching
        self.run_id = run_id or uuid4().hex
        self.variant = 0 if teaching else self.seed % len(self.map['placements'])
        self.items = {entry['instance_id']: dict(entry, state='world')
                      for entry in self.map['placements'][self.variant]}
        eligible = [p['treasure_id'] for p in self.items.values()
                    if TREASURES[p['treasure_id']][1] <= RULES['capacity'] or 'lift_bag' in self.tools]
        self.contract = eligible[0] if teaching else eligible[self.seed // len(self.map['placements']) % len(eligible)]
        self.phase = 'diving'
        self.tick = 0
        self.oxygen = RULES['oxygen'] * HZ
        self.x, self.y = center(self.map['dock'])
        self.vx = self.vy = 0
        self.facing = (0, 1)
        self.rooms = self.map['rooms']
        self.edges = self.map['edges']
        self.opened = {e['id'] for e in self.edges if not e['gate']}
        self.cut = {}
        self.seen_edges = set()
        self.seen_rooms = {'dock'}
        self.seen_items = set()
        self.bags = RULES['bags']
        self.air_ticks = 0
        self.air_active = self.air_used = False
        self.bind_id = None
        self.bind_ticks = 0
        self.sonar_at = -RULES['sonarCooldown'] * HZ
        self.selected = None
        self.notice = ''
        self.notice_until = 0
        self.events = []
        self.pending = []
        self.result = None
        self.demo_at = None

    @property
    def hold(self):
        return [p for p in self.items.values() if p['state'] == 'hold']

    @property
    def weight(self):
        return sum(TREASURES[p['treasure_id']][1] for p in self.hold)

    @property
    def speed(self):
        return RULES['speed'] * (1 - RULES['weightDrag'] * self.weight)

    @property
    def docked(self):
        return inside(self.map['dock'], self.x, self.y) and math.hypot(self.vx, self.vy) < 15

    def near(self, point, distance=58):
        return math.dist((self.x, self.y), point) <= distance

    def message(self, message):
        self.notice, self.notice_until = message, self.tick + 150

    def can_fit(self, x, y):
        for sx, sy in ((-1,-1), (-1,1), (1,-1), (1,1), (0,0)):
            px, py = x + sx * RADIUS, y + sy * RADIUS
            if not (any(inside(rect, px, py) for rect in self.rooms.values()) or
                    any(e['id'] in self.opened and inside(e['rect'], px, py) for e in self.edges)):
                return False
        return True

    def move(self, dx, dy):
        scale = self.speed / max(1, math.hypot(dx, dy))
        self.vx += (dx * scale - self.vx) * .24
        self.vy += (dy * scale - self.vy) * .24
        if dx or dy:
            norm = math.hypot(dx, dy)
            self.facing = (dx / norm, dy / norm)
        nx, ny = self.x + self.vx / HZ, self.y + self.vy / HZ
        if self.can_fit(nx, self.y):
            self.x = nx
        else:
            self.vx = 0
        if self.can_fit(self.x, ny):
            self.y = ny
        else:
            self.vy = 0

    def visible(self, x, y):
        dx, dy = x - self.x, y - self.y
        distance = math.hypot(dx, dy)
        if distance > 320 or (distance > 75 and dx*self.facing[0]+dy*self.facing[1] < distance*.59):
            return False
        regions = [*self.rooms.values(), *(e['rect'] for e in self.edges if e['id'] in self.opened)]
        samples = max(1, math.ceil(distance/16))
        return all(any(inside(r,self.x+dx*i/samples,self.y+dy*i/samples) for r in regions)
                   for i in range(1,samples))

    def beacon(self, edge):
        x, y = center(edge['rect'])
        if edge['id'] in self.opened:
            return self.visible(x,y)
        ex,ey,ew,eh = edge['rect']
        for name in (edge['a'],edge['b']):
            if inside(self.rooms[name],self.x,self.y):
                rx,ry,rw,rh = self.rooms[name]
                bx,by = min(rx+rw,max(rx,x)),min(ry+rh,max(ry,y))
                if inside((ex,ey,ew,eh),bx,by) and self.visible(bx,by):
                    return True
        return False

    def scanned(self, x, y):
        return (self.tick - self.sonar_at < RULES['sonarSeconds'] * HZ
                and self.near((x, y), RULES['sonarRange']))

    def discover(self):
        for name, rect in self.rooms.items():
            if inside(rect, self.x, self.y):
                self.seen_rooms.add(name)
        for edge in self.edges:
            x, y = center(edge['rect'])
            if self.beacon(edge) or self.scanned(x, y):
                self.seen_edges.add(edge['id'])
        for p in self.items.values():
            if p['state'] == 'world' and (self.visible(p['x'], p['y']) or self.scanned(p['x'], p['y'])):
                self.seen_items.add(p['instance_id'])

    def rank(self, x, y, identifier):
        dx, dy = x - self.x, y - self.y
        return (math.hypot(dx, dy), -dx * self.facing[0] - dy * self.facing[1], identifier)

    def nearest_item(self):
        candidates = [p for p in self.items.values() if p['state'] == 'world'
                      and inside(self.rooms[p['room']], self.x, self.y) and self.near((p['x'], p['y']))]
        return min(candidates, key=lambda p: self.rank(p['x'], p['y'], p['instance_id']), default=None)

    def nearest_gate(self):
        candidates = []
        for edge in self.edges:
            if not edge['gate'] or edge['id'] in self.opened:
                continue
            x, y, w, h = edge['rect']
            point = (min(x+w, max(x, self.x)), min(y+h, max(y, self.y)))
            if self.near(point, 38):
                candidates.append((self.rank(*point, edge['id']), edge))
        return min(candidates, default=(None, None), key=lambda item: item[0])[1]

    def lift_target(self):
        if not self.near(self.map['shaft'], 86):
            return None
        overhead = self.selected or (self.hold[0]['instance_id'] if self.hold else None)
        cargo = self.items.get(overhead)
        if cargo and cargo['state'] == 'hold':
            return cargo
        item = self.nearest_item()
        if item and TREASURES[item['treasure_id']][1] <= RULES['maxLift'] and self.near((item['x'], item['y']), 86):
            return item
        return None

    def target(self):
        if inside(self.map['dock'], self.x, self.y):
            return 'dock', None
        candidates = []
        if self.near(self.map['air']) and not self.air_used:
            candidates.append((self.rank(*self.map['air'], 'air'), 'air', None))
        item = self.nearest_item()
        if item:
            candidates.append((self.rank(item['x'], item['y'], item['instance_id']), 'item', item))
        if candidates:
            _, kind, obj = min(candidates)
            return kind, obj
        return 'hold', None

    def unload(self, identifier):
        item = self.items.get(identifier)
        if not item or item['state'] != 'hold':
            return
        offsets = [(0,0)]
        for distance in (24,48,72,96,120):
            offsets.extend((distance*dx,distance*dy) for dx,dy in
                           ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)))
        for dx, dy in offsets:
            x, y = self.x + dx, self.y + dy
            room = next((name for name, rect in self.rooms.items() if inside(rect, x, y, RADIUS)), None)
            samples = max(1, math.ceil(math.hypot(dx,dy)/12))
            if room and all(self.can_fit(self.x+dx*i/samples,self.y+dy*i/samples)
                            for i in range(1,samples+1)):
                item.update(state='world', x=x, y=y, room=room)
                self.selected = None
                self.message('已卸下 ' + TREASURES[item['treasure_id']][0])
                return
        self.message('请开到附近舱室卸货')

    def interact(self):
        kind, item = self.target()
        if kind == 'dock':
            if self.docked:
                return True
            self.message('松开方向键，停稳后确认返港')
        elif kind == 'air':
            self.air_active = True
        elif kind == 'item':
            name, weight, _, _ = TREASURES[item['treasure_id']]
            excess = self.weight + weight - RULES['capacity']
            if excess > 0:
                self.message(f'{name} 超出舱容 {excess}' + (' · 需浮袋' if weight > RULES['capacity'] else ''))
            else:
                item['state'] = 'hold'
                self.message('装舱 ' + name)
                self.events.append('pickup')
        else:
            self.events.append('hold')
        return False

    def use_tools(self, held, pressed):
        extra = 0
        if 'sonar' in pressed and self.tick - self.sonar_at >= RULES['sonarCooldown'] * HZ:
            self.sonar_at = self.tick
            extra += RULES['sonarOxygen'] * HZ
            self.events.append('sonar')
            self.message('声呐扫描 · 轮廓保持 3 秒')
        gate = self.nearest_gate() if 'cutter' in held else None
        if gate:
            identifier = gate['id']
            self.cut[identifier] = self.cut.get(identifier, 0) + 1
            extra += RULES['cutterOxygen']
            if self.cut[identifier] == HZ * RULES['cutterSeconds']:
                self.opened.add(identifier)
                self.events.append('cut')
                self.message('闸门已打开')
        item = self.lift_target() if 'lift_bag' in held and self.bags else None
        identifier = item['instance_id'] if item else None
        self.bind_ticks = self.bind_ticks + 1 if identifier and self.bind_id == identifier else int(bool(identifier))
        self.bind_id = identifier
        if item and self.bind_ticks >= HZ * RULES['bindSeconds']:
            item.update(state='in_transit', arrival=self.tick + HZ * RULES['transitSeconds'])
            self.bags -= 1
            self.selected = None
            self.events.append('launch')
            self.message('浮袋运输中 · 5 秒后签收')
        return extra

    def deliver(self, cargo):
        for item in cargo:
            item['state'] = 'delivered'
            self.pending.append((item['instance_id'], item['treasure_id']))
            self.events.append('delivery')
            self.message('母船已签收 ' + TREASURES[item['treasure_id']][0])

    def finish(self, reason):
        if self.phase != 'diving':
            return
        safe = reason == 'safe'
        if safe:
            self.deliver([p for p in self.items.values() if p['state'] in ('hold', 'in_transit')])
        arrived = [p['treasure_id'] for p in self.items.values() if p['state'] == 'delivered']
        lost = [p['treasure_id'] for p in self.items.values() if p['state'] in ('hold', 'in_transit')]
        for p in self.items.values():
            if p['state'] in ('hold', 'in_transit'):
                p['state'] = 'world'
                p['lost'] = True
        self.result = dict(reason=reason, delivered=arrived, lost=lost,
                           income=sum(TREASURES[t][2] for t in arrived), complete=self.contract in arrived)
        self.phase = 'debrief'

    def step(self, dx=0, dy=0, held=(), pressed=(), interact=False):
        if self.phase != 'diving':
            return
        self.tick += 1
        self.move(dx, dy)
        self.oxygen -= 1 + self.use_tools(held, pressed)
        self.deliver([p for p in self.items.values()
                      if p['state'] == 'in_transit' and p['arrival'] <= self.tick])
        safe = interact and self.interact()
        if self.air_active and not self.air_used:
            if self.near(self.map['air']) and math.hypot(self.vx, self.vy) < 15:
                self.air_ticks += 1
                if self.air_ticks == 2 * HZ:
                    self.air_used = True
                    self.oxygen = min(RULES['oxygen'] * HZ, self.oxygen + RULES['air'] * HZ)
                    self.message('已补充 20 点氧气')
                    self.events.append('air')
            else:
                self.air_ticks = 0
                self.air_active = False
        if self.teaching and self.sea == 'wreck':
            if self.demo_at is None and self.y > 275:
                self.demo_at = self.tick + HZ * RULES['transitSeconds']
                self.events.append('launch')
            elif self.demo_at == self.tick:
                self.events.append('delivery')
        self.discover()
        if safe:
            self.finish('safe')
        elif self.oxygen <= 0:
            self.finish('oxygen')

    def return_route(self):
        """Route only through charted open passages, with one waypoint per opening."""
        start = self.x, self.y
        home = center(self.map['dock'])
        nodes = {'start': start, 'home': home}
        groups = {name: [] for name in self.rooms}
        groups['dock'].append('home')
        for name, rect in self.rooms.items():
            if inside(rect, *start):
                groups[name].append('start')
        links = []
        for edge in self.edges:
            key = edge['id']
            if key not in self.seen_edges or key not in self.opened:
                continue
            ex, ey, ew, eh = edge['rect']
            pair = []
            for name in (edge['a'], edge['b']):
                rx, ry, rw, rh = self.rooms[name]
                left, right = max(ex, rx), min(ex + ew, rx + rw)
                top, bottom = max(ey, ry), min(ey + eh, ry + rh)
                point = ((left + right) / 2, (top + bottom) / 2)
                node = key + ':' + name
                nodes[node] = point
                groups[name].append(node)
                pair.append(node)
            links.append(pair)
            if inside(edge['rect'], *start):
                links.extend(('start', node) for node in pair)
        graph = {key: set() for key in nodes}
        for group in groups.values():
            for key in group:
                graph[key].update(other for other in group if other != key)
        for a, b in links:
            graph[a].add(b)
            graph[b].add(a)
        pending = [(0, 'start', ())]
        seen = set()
        while pending:
            distance, key, route = heapq.heappop(pending)
            if key in seen:
                continue
            seen.add(key)
            if key == 'home':
                return route, math.ceil(distance / self.speed)
            for neighbor in graph[key] - seen:
                heapq.heappush(pending, (distance + math.dist(nodes[key], nodes[neighbor]),
                                         neighbor, (*route, nodes[neighbor])))
        known = [nodes[key] for key in nodes if key not in ('start', 'home')]
        return ((min(known, key=lambda point: math.dist(home, point)),) if known else (home,)), None
