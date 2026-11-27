"""Fixed-step Boss Duel rules. Coordinates never depend on the client viewport."""
import json
import math
from pathlib import Path

RULES = json.loads((Path(__file__).resolve().parents[2] / 'assets/modes/boss_duel/rules.json')
                   .read_text(encoding='utf-8-sig'))
BOSSES = RULES['bosses']
WIDTH, HEIGHT = 800, 540
HERO_RADIUS = 12
HERO_SPEED = 3.5
HERO_BOUNDS = 18, 170, 782, 520
BOSS_BOUNDS = 100, 65, 700, 125
WEAK = 108, 58
LIMIT = 5400
READY = 180
SWAP = 300
ULTIMATES = ('crescent', 'ring', 'storm')
ERRORS = {
    'role': '当前角色无法使用', 'phase': '稍候再出手', 'energy': '能量不足',
    'cooldown': '技能冷却中', 'interval': '施放间隔中',
    'slots': '场上技能已满', 'route': '通道占用',
}


def clip(value, lo, hi):
    return min(hi, max(lo, value))


def move(point, delta, bounds):
    x, y = point
    dx, dy = delta
    l, t, r, b = bounds
    return clip(x + dx, l, r), clip(y + dy, t, b)


def unit(x, y):
    scale = math.hypot(x, y) or 1
    return x / scale, y / scale


def nearest_on_segment(x, y, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = clip(((x - ax) * dx + (y - ay) * dy) / length, 0, 1) if length else 0
    return ax + t * dx, ay + t * dy


def hits(shape, point):
    kind, *coords = shape
    x, y = point
    if kind == 'rect':
        l, t, r, b = coords
        return (x - clip(x, l, r)) ** 2 + (y - clip(y, t, b)) ** 2 <= HERO_RADIUS ** 2
    if kind == 'line':
        ax, ay, bx, by, half = coords
        px, py = nearest_on_segment(x, y, ax, ay, bx, by)
        return (x - px) ** 2 + (y - py) ** 2 <= (half + HERO_RADIUS) ** 2
    if kind == 'circle':
        cx, cy, radius = coords
        return (x - cx) ** 2 + (y - cy) ** 2 <= (radius + HERO_RADIUS) ** 2
    cx, cy, radius, angle, gap = coords
    dx, dy = x - cx, y - cy
    if abs(math.hypot(dx, dy) - radius) > 9 + HERO_RADIUS:
        return False
    difference = abs(math.remainder(math.atan2(dy, dx) - angle, math.tau))
    if difference >= gap:
        return True
    distance = math.hypot(dx, dy)
    offset = gap - difference
    closest = clip(distance * math.cos(offset), max(0, radius - 9), radius + 9)
    return distance**2 + closest**2 - 2 * distance * closest * math.cos(offset) <= HERO_RADIUS**2


def pearl_track(origin, target):
    """Three straight segments, using the same wall reflection for telegraph and hit."""
    radius = 14
    x, y = origin
    dx, dy = unit(target[0] - x, target[1] - y)
    if not (dx or dy):
        dy = 1
    track = [(0, x, y)]
    distance = 0
    for _ in range(3):
        sides = ((WIDTH - radius - x if dx > 0 else radius - x) / dx if dx else math.inf,
                 (HEIGHT - radius - y if dy > 0 else radius - y) / dy if dy else math.inf)
        length = min(*sides, 705 - distance)
        x, y = x + length * dx, y + length * dy
        distance += length
        track.append((distance * 60 / 235, x, y))
        if distance >= 705:
            break
        if abs(length - sides[0]) < 1e-7:
            dx = -dx
        if abs(length - sides[1]) < 1e-7:
            dy = -dy
    return track


def crescent_gap(hero, target_x, warning):
    earliest = warning + max(0, math.ceil((hero[1] - HERO_RADIUS - 158) / 4))
    distance = HERO_SPEED * max(0, earliest - 12)
    lo = max(HERO_BOUNDS[0], hero[0] - distance)
    hi = min(HERO_BOUNDS[2], hero[0] + distance)
    return clip(clip(target_x, 56, 744), lo - 40, hi + 40)


def make_cast(ident, index, skill, origin, target, hero, tick):
    _, kind, warning, duration, _, _ = skill
    x, y = target
    cast = dict(cast_id=ident, index=index, kind=kind, origin=origin, target=target,
                start_tick=tick, active_tick=tick + warning, end_tick=tick + warning + duration)
    if kind == 'pearl':
        cast['track'] = pearl_track(origin, target)
        cast['end_tick'] = cast['active_tick'] + math.ceil(cast['track'][-1][0])
    elif kind == 'crescent':
        center = crescent_gap(hero, x, warning)
        cast['safe'] = (center - 56, center + 56)
    elif kind == 'lash':
        ox, oy = origin
        cast['points'] = (origin, (ox + (x - ox) * .48, oy + (y - oy) * .48 + 18), target)
    elif kind == 'missile':
        x, y = clip(x, 78, 722), clip(y, 34, 506)
        cast['centers'] = ((x - 44, y), (x + 44, y))
    elif kind == 'ring':
        # Aim the gap toward the interior, along a direction with room to move.
        x, y = clip(x, 170, 630), clip(y, 190, 360)
        angle = math.atan2(330 - y, 400 - x)
        cast['center'] = (x, y)
        cast['safe'] = (angle, math.pi / 3)
    elif kind == 'cross':
        cast['points'] = tuple((0, y - x * slope, WIDTH, y + (WIDTH - x) * slope)
                               for slope in (.72, -.72))
    elif kind == 'storm':
        x, y = clip(x, 146, 654), clip(y, 218, 458)
        cast['centers'] = ((x - 98, y), (x, y - 32), (x + 98, y))
        cast['safe'] = (18, x - 146) if x >= 400 else (x + 146, 782)
    return cast


def shapes(cast, tick, preview=False):
    kind = cast['kind']
    age = tick - cast['active_tick']
    if not preview and (age < 0 or tick >= cast['end_tick']):
        return ()
    x, y = cast['target']
    if kind == 'geyser':
        return (('rect', x - 28, 150, x + 28, HEIGHT),)
    if kind == 'pearl':
        track = cast['track']
        if preview:
            return tuple(('line', ax, ay, bx, by, 2)
                         for (_, ax, ay), (_, bx, by) in zip(track[:2], track[1:3]))
        for (start, ax, ay), (end, bx, by) in zip(track, track[1:]):
            if age <= end:
                t = (age - start) / (end - start)
                return (('circle', ax + (bx - ax) * t, ay + (by - ay) * t, 14),)
        return ()
    if kind == 'crescent':
        left, right = cast['safe']
        if preview:
            return (('rect', 0, 158, left, HEIGHT), ('rect', right, 158, WIDTH, HEIGHT))
        rows = []
        for delay in (0, 18):
            tip = 158 + (age - delay) * 4
            if age >= delay and tip - 26 <= HEIGHT:
                rows.extend((('rect', 0, tip - 26, left, tip), ('rect', right, tip - 26, WIDTH, tip)))
        return tuple(shape for shape in rows if shape[3] > shape[1])
    if kind == 'lash':
        points = cast['points']
        return tuple(('line', *a, *b, 16) for a, b in zip(points, points[1:]))
    if kind in ('missile', 'storm'):
        spacing, duration, radius = (24, 12, 34) if kind == 'missile' else (30, 30, 48)
        return tuple(('circle', *point, radius) for i, point in enumerate(cast['centers'])
                     if preview or i * spacing <= age < i * spacing + duration)
    if kind == 'ring':
        return (('ring', *cast['center'], 145 if preview else 145 * (age + 1) / 84, *cast['safe']),)
    if kind == 'slam':
        return (('circle', x, y, 42),)
    return tuple(('line', *line, 11) for line in cast['points'])


def safe_route(hero, casts, tick):
    """Accept overlap only after finding a walkable route through both timelines."""
    timeline = [tuple(shape for cast in casts for shape in shapes(cast, frame))
                for frame in range(tick, max(cast['end_tick'] for cast in casts))]
    # Walk toward edges, gaps and evenly spaced headings. Stops and one turn at
    # a safe waypoint allow crossing moving hazards as they clear.
    goals = [(x, y) for x in (18, 195, 400, 605, 782) for y in (170, 345, 520)]
    for cast in casts:
        if cast['kind'] == 'crescent':
            left, right = cast['safe']
            goals.extend((x, hero[1]) for x in (left+14, (left+right)/2, right-14))
    headings = [(0, 0)] + [(math.cos(i * math.pi / 8), math.sin(i * math.pi / 8)) for i in range(16)]

    def clear(point, threats):
        return not any(hits(shape, point) for shape in threats)

    def walk(point, heading, start, end, goal=None):
        dx, dy = (component * HERO_SPEED for component in heading)
        for i in range(start, end):
            if i >= 12:
                if goal is not None and math.dist(point, goal) <= HERO_SPEED:
                    point = goal
                else:
                    point = move(point, (dx, dy), HERO_BOUNDS)
            if not clear(point, timeline[i]):
                return None
        return point

    end = len(timeline)
    if any(walk(hero, heading, 0, end) is not None for heading in headings):
        return True
    for goal in goals:
        heading = unit(goal[0] - hero[0], goal[1] - hero[1])
        if walk(hero, heading, 0, end, goal) is not None:
            return True
        turn = min(end, 12 + math.ceil(math.dist(hero, goal) / HERO_SPEED))
        waypoint = walk(hero, heading, 0, turn, goal)
        if waypoint is not None and any(walk(waypoint, direction, turn, end) is not None for direction in headings):
            return True
    return False


def compare(first, second):
    if first['defeated'] != second['defeated']:
        return (first if first['defeated'] else second)['slot'], 'defeated'
    fields = (('defeat_tick', -1), ('hp', 1)) if first['defeated'] else (
        ('survival_tick', 1), ('damage', 1), ('hp', 1))
    for key, sign in fields:
        if first[key] != second[key]:
            return (first if sign * (first[key] - second[key]) > 0 else second)['slot'], key
    return None, 'draw'


class BossDuel:
    @classmethod
    def from_room(cls, *, mode_options, **room_options):
        return cls(mode_options['boss'])

    def __init__(self, boss='whale'):
        self.boss = boss
        self.skills = BOSSES[boss]['skills']
        self.round_id = self.epoch = 1
        self.tick = 0
        self.cast_id = self.event_id = 0
        self.events = []
        self.feedback = {}
        self.results = []
        self.result = None
        self.departed = set()
        self.reset_round()

    def reset_round(self):
        self.phase = 'playing'
        self.stage = 'countdown'
        self.remaining = READY
        self.clock = 0
        self.boss_slot = self.round_id
        self.hero_slot = 3 - self.boss_slot
        self.hero = (400, 430)
        self.position = (400, 90)
        self.hero_hp, self.boss_hp = 5, 150
        self.energy = 70 * 60
        self.cooldowns = [0, 0, 0]
        self.next_cast = self.next_shot = self.next_dash = 0
        self.dash_until = self.invulnerable = 0
        self.last_direction = self.dash_direction = (0, -1)
        self.ready = set()
        self.casts, self.shots = [], []
        self.hit_casts = set()
        self.invalidate(advance=False)

    def invalidate(self, advance=True):
        self.epoch += int(advance)
        self.inputs = {1: (0, 0, 0), 2: (0, 0, 0)}
        self.actions = []
        self.feedback.clear()

    def set_input(self, slot, x, y, shoot):
        self.inputs[slot] = x, y, int(shoot)

    def mode_input(self, slot, message):
        if message['type'] == 'mode_input':
            self.set_input(slot, message['x'], message['y'], message['held'] & 1)
        elif message['action'] in ('dash', 'round_ready', 'cast_1', 'cast_2', 'cast_3'):
            self.actions.append((slot, message['action'], message.get('target')))
        else:
            return 'unexpected_action'
        return None

    def action(self, slot, name, key=None):
        return 'unexpected_action'

    def emit(self, name):
        self.event_id += 1
        self.events = (self.events + [(self.event_id, name)])[-16:]

    def reject(self, slot, action, reason):
        self.feedback[slot] = (action, reason, self.tick + 95)

    def cast(self, slot, index, target):
        skill = self.skills[index]
        _, kind, _, _, cooldown, cost = skill
        if slot != self.boss_slot:
            reason = 'role'
        elif self.stage != 'combat' or self.clock < 60:
            reason = 'phase'
        elif self.cooldowns[index] > self.clock:
            reason = 'cooldown'
        elif self.next_cast > self.clock:
            reason = 'interval'
        elif self.energy < cost * 60:
            reason = 'energy'
        elif len(self.casts) >= 2 or (kind in ULTIMATES and any(c['kind'] in ULTIMATES for c in self.casts)):
            reason = 'slots'
        else:
            position = (target[0] * WIDTH / 1000, target[1] * HEIGHT / 1000)
            origin = (self.position[0], self.position[1] + 22)
            candidate = make_cast(self.cast_id + 1, index, skill, origin, position, self.hero, self.clock)
            if not self.casts or safe_route(self.hero, [*self.casts, candidate], self.clock):
                self.cast_id += 1
                self.casts.append(candidate)
                self.energy -= cost * 60
                self.cooldowns[index] = self.clock + cooldown
                self.next_cast = self.clock + 24
                self.feedback.pop(slot, None)
                self.emit('warning')
                return
            reason = 'route'
        self.reject(slot, f'cast_{index + 1}', reason)

    def dash(self):
        if self.clock < self.next_dash:
            self.reject(self.hero_slot, 'dash', 'cooldown')
            return
        x, y, _ = self.inputs[self.hero_slot]
        self.dash_direction = unit(x, y) if x or y else self.last_direction
        self.next_dash = self.clock + 150
        self.dash_until = self.clock + 12
        self.emit('dash')

    def step(self):
        if self.result:
            return
        self.tick += 1
        actions, self.actions = self.actions, []
        self.casts = [cast for cast in self.casts if cast['end_tick'] > self.clock]
        self.hit_casts.intersection_update(cast['cast_id'] for cast in self.casts)
        for slot, action, target in actions:
            if action == 'round_ready' and self.stage == 'swap':
                self.ready.add(slot)
            elif action == 'dash':
                if slot == self.hero_slot and self.stage == 'combat':
                    self.dash()
                else:
                    self.reject(slot, action, 'role' if slot != self.hero_slot else 'phase')
            elif action in ('cast_1', 'cast_2', 'cast_3'):
                self.cast(slot, int(action[-1]) - 1, target)
        if self.stage in ('countdown', 'swap'):
            self.remaining -= 1
            if self.stage == 'swap' and (not self.remaining or len(self.ready) == 2):
                self.round_id += 1
                self.epoch += 1
                self.reset_round()
            elif self.stage == 'countdown' and not self.remaining:
                self.stage = 'combat'
                self.emit('start')
            return
        hx, hy, shoot = self.inputs[self.hero_slot]
        bx, by, _ = self.inputs[self.boss_slot]
        if hx or hy:
            self.last_direction = unit(hx, hy)
        dashing = self.clock < self.dash_until
        delta = tuple(n * 6 for n in self.dash_direction) if dashing else (
            hx * HERO_SPEED / max(1, math.hypot(hx, hy)),
            hy * HERO_SPEED / max(1, math.hypot(hx, hy)))
        self.hero = move(self.hero, delta, HERO_BOUNDS)
        self.position = move(self.position, (bx * 1.5 / max(1, math.hypot(bx, by)),
                                             by * 1.5 / max(1, math.hypot(bx, by))), BOSS_BOUNDS)
        self.energy = min(6000, self.energy + 8)
        if self.clock >= 60:
            self.combat(shoot, dashing)
        self.clock += 1
        if not self.hero_hp or not self.boss_hp or self.clock == LIMIT:
            self.finish_round()

    def combat(self, shoot, dashing):
        if shoot and self.clock >= self.next_shot:
            self.shots.append(self.hero)
            self.next_shot = self.clock + 12
            self.emit('shot')
        bx, by = self.position
        damage = 0
        shots = []
        for x, y in self.shots:
            upper, lower = by + 11 - WEAK[1] / 2, by + 11 + WEAK[1] / 2
            if abs(x - bx) <= WEAK[0] / 2 and y >= upper and y - 11 <= lower:
                damage += 1
            elif y > 11:
                shots.append((x, y - 11))
        self.shots = shots
        protected = self.clock < self.invulnerable or (dashing and self.dash_until - self.clock > 6)
        hurt = 0
        for cast in self.casts:
            if self.clock == cast['active_tick'] or (cast['kind'] in ('missile', 'storm')
                    and self.clock - cast['active_tick'] in ((24,) if cast['kind'] == 'missile' else (30, 60))):
                self.emit('impact')
            if not protected and not hurt and cast['cast_id'] not in self.hit_casts:
                if any(hits(shape, self.hero) for shape in shapes(cast, self.clock)):
                    self.hit_casts.add(cast['cast_id'])
                    hurt = 1
        self.hero_hp -= hurt
        self.boss_hp = max(0, self.boss_hp - damage)
        if hurt:
            self.invulnerable = self.clock + 54
            self.emit('hurt')
        if damage:
            self.emit('hit')

    def round_result(self):
        return dict(slot=self.hero_slot, survival_tick=self.clock, defeated=not self.boss_hp,
                    defeat_tick=self.clock if not self.boss_hp else None,
                    damage=150 - self.boss_hp, hp=self.hero_hp)

    def finish_round(self):
        self.results.append(self.round_result())
        self.invalidate()
        if self.round_id == 1:
            self.stage, self.remaining = 'swap', SWAP
            self.casts.clear()
            self.shots.clear()
            self.emit('swap')
        else:
            self.finish(*compare(*self.results))

    def finish(self, winner, metric):
        if self.result is None:
            rounds = list(self.results)
            if len(rounds) < self.round_id and self.clock:
                rounds.append(dict(self.round_result(), partial=True))
            self.result = dict(winner=winner, metric=metric, rounds=rounds)
            self.phase = 'won'
            self.stage = 'result'
            self.casts.clear()
            self.shots.clear()
            self.emit('result')

    def remove_player(self, slot):
        self.departed.add(slot)
        self.invalidate()
        if not self.result:
            self.finish(3 - slot, 'forfeit')

    def snapshot(self):
        roles = {self.boss_slot: 'boss', self.hero_slot: 'hero'}
        feedback = {slot: details for slot, details in self.feedback.items() if details[2] > self.tick}
        return dict(tick=self.tick, phase=self.phase, players=[
            dict(slot=self.hero_slot, hp=self.hero_hp, max_hp=5, alive=self.hero_hp > 0),
            dict(slot=self.boss_slot, hp=self.boss_hp, max_hp=150, alive=self.boss_hp > 0)],
            world=dict(kind='mode', schema=1, mode='boss_duel', content_id=self.boss,
                       content_version=RULES['version'], epoch=self.epoch, round_id=self.round_id,
                       role_by_slot=roles, arena=[WIDTH, HEIGHT], view_size=[WIDTH, HEIGHT],
                       phase=self.stage, remaining=self.remaining, clock=self.clock, tick=self.tick,
                       hero_hp=self.hero_hp, boss_hp=self.boss_hp, energy=self.energy / 60,
                       hero=self.hero, boss=self.position, dash_until=self.dash_until,
                       invulnerable=self.invulnerable, dash_cooldown=max(0, self.next_dash - self.clock),
                       cooldowns=[max(0, until - self.clock) for until in self.cooldowns],
                       pending_casts=list(self.casts),
                       active_shapes=[dict(cast_id=c['cast_id'], shapes=shapes(c, max(0, self.clock - 1)))
                                      for c in self.casts if c['active_tick'] < self.clock],
                       shots=list(self.shots), first_round_result=self.results[0] if self.results else None,
                       result=self.result, final_result=self.result, round_ready=sorted(self.ready),
                       feedback=feedback, events=list(self.events)))
