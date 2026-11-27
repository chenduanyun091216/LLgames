"""Fixed-step flying fish race. Rendering and storage consume this state."""
from dataclasses import asdict, dataclass, field
from functools import lru_cache
import json
from math import floor, sin, tau
from pathlib import Path

HZ = 60
COUNTDOWN = 3 * HZ
LIMIT = 210 * HZ
GRACE = 20 * HZ
BASELINE = 276
DEPTH = 397
VIEW = (960, 540)
TRACK_IDS = ('lighthouse', 'reef', 'storm')


@lru_cache(maxsize=1)
def content():
    path = Path(__file__).resolve().parents[2] / 'assets/modes/tide_race/tracks.json'
    return json.loads(path.read_text(encoding='utf-8'))


def clamp(value, low, high):
    return min(high, max(low, value))


def approach(value, target, amount):
    return value + clamp(target - value, -amount, amount)


def pixel(value):
    return floor(value + .5)


def wave(track, x, tick):
    waves = track['waves']
    index = next((i for i in range(len(waves)-1, 0, -1) if x >= waves[i][0]), 0)

    def profile(segment):
        start, amplitude, length, speed, phase = segment
        angle = tau * (x - start - speed * tick / HZ) / length + phase
        return amplitude * sin(angle), angle, length

    height, angle, length = profile(waves[index])
    if index:
        amount = clamp((x - waves[index][0]) / 160, 0, 1)
        amount = amount * amount * (3 - 2 * amount)
        previous, _, _ = profile(waves[index-1])
        height = previous + (height - previous) * amount
    peak = abs((angle / tau) % 1 - .25)
    return BASELINE - height, min(peak, 1 - peak) <= .14 and waves[index][1] > 0


def deep_y(track, x):
    start, end = track['branch']
    amount = clamp(min((x-start)/240, (end-x)/240), 0, 1)
    return BASELINE + (DEPTH - BASELINE) * amount


@dataclass
class Racer:
    slot: int
    x: float = 0
    y: float = BASELINE
    speed: float = 175
    vy: float = 0
    branch: str = 'surface'
    route: str = 'surface'
    route_distance: float = 0
    pose: str = 'swim'
    combo: int = 0
    combo_until: int = 0
    gates: list = field(default_factory=list)
    finish_tick: int | None = None
    freeze: int = 0
    launch_until: int = -1
    contact: int | None = None
    left: bool = False
    joined: bool = False
    entry: bool = False


class Race:
    def __init__(self, track_id='lighthouse', slots=(1,)):
        self.track_id = track_id
        self.track = content()['tracks'][track_id]
        self.rules_version = content()['rules_version']
        self.racers = {slot: Racer(slot) for slot in slots}
        self.tick = 0
        self.start_tick = COUNTDOWN
        self.deadline_tick = COUNTDOWN + LIMIT
        self.phase = 'grid'
        self.result = None
        self.samples = []

    @property
    def clock(self):
        return max(0, self.tick - self.start_tick)

    def sample(self, racer):
        row = [self.clock, pixel(racer.x), pixel(racer.y), racer.pose, racer.branch]
        if self.samples and self.samples[-1][0] == row[0]:
            self.samples[-1] = row
        else:
            self.samples.append(row)

    def step(self, inputs=None, launches=(), departures=()):
        if self.result is not None:
            return
        self.tick += 1
        if self.tick < self.start_tick:
            self.phase = 'countdown'
            self.depart(departures)
            return
        if self.tick == self.start_tick:
            self.phase = 'racing'
            for racer in self.racers.values():
                racer.y = wave(self.track, 0, 0)[0]
            if len(self.racers) == 1:
                self.sample(next(iter(self.racers.values())))
            self.depart(departures)
            return
        inputs = inputs or {}
        for slot, racer in self.racers.items():
            if racer.left or racer.finish_tick is not None:
                continue
            previous_branch = racer.branch
            self.drive(racer, *inputs.get(slot, (0, 0, 0)), slot in launches)
            if len(self.racers) == 1 and (self.clock % 6 == 0 or racer.finish_tick is not None
                    or racer.branch != previous_branch or racer.pose == 'reset'):
                self.sample(racer)
        self.depart(departures)

    def depart(self, slots):
        for slot in slots:
            self.racers[slot].left = True
        if self.result is None:
            self.resolve()

    def drive(self, racer, horizontal, vertical, held, launch):
        track = self.track
        clock = self.clock
        if racer.freeze:
            racer.freeze -= 1
            racer.pose = 'dive' if racer.branch == 'deep' else 'swim'
            if racer.branch == 'surface':
                racer.y = wave(track, racer.x, clock)[0]
            return
        if racer.combo and clock >= racer.combo_until:
            racer.combo = 0
        if launch and racer.pose in ('swim', 'reset') and racer.branch == 'surface':
            racer.launch_until = clock + 5
        diving = bool(held & 2)
        previous_x, previous_y = racer.x, racer.y
        start, end = track['branch']
        pace = 185 + horizontal * (30 if horizontal >= 0 else 40) + 12 * racer.combo
        racer.speed = approach(racer.speed, pace, 60 / HZ)
        drift = next((v for lo, hi, v in track.get('currents', []) if lo <= racer.x < hi), 0)
        remaining = max(0, racer.speed + drift) / HZ

        # Approach and exit use public coordinates. Only the shared branch interval
        # maps local distance to public progress at a route-specific ratio.
        racer.x += min(remaining, max(0, start - racer.x))
        remaining -= racer.x - previous_x
        if previous_x < start <= racer.x and not racer.entry:
            racer.entry = True
            racer.route = racer.branch = 'deep' if diving or vertical > .5 else 'surface'
            if racer.branch == 'deep':
                racer.pose, racer.vy, racer.launch_until = 'dive', 0, -1
        if start <= racer.x < end:
            ratio = 1 - track['shortcut'] if racer.branch == 'deep' else 1
            part = min(remaining, (end - racer.x) * ratio)
            racer.route_distance += part
            racer.x += part / ratio
            remaining -= part
        racer.x = min(track['length'], racer.x + remaining)
        if previous_x < end <= racer.x:
            racer.branch, racer.joined = 'surface', True
            if racer.route == 'deep':
                racer.pose, racer.vy = 'swim', 0

        surface, strong = wave(track, racer.x, clock)
        if racer.branch == 'deep':
            base = deep_y(track, racer.x)
            racer.y = approach(racer.y, base + (10 if diving else -6) + vertical * 24, 260 / HZ)
        elif racer.pose == 'swim':
            racer.y = surface
            if racer.launch_until >= clock and (strong or racer.launch_until == clock):
                racer.vy = -285 if strong else -145
                racer.pose, racer.launch_until = 'glide', -1
        else:
            racer.pose = 'dive' if diving else 'glide'
            racer.vy += (680 + 460 * diving) / HZ
            racer.y += racer.vy / HZ
            previous_surface = wave(track, previous_x, clock-1)[0]
            if racer.vy > 0 and previous_y <= previous_surface and racer.y >= surface:
                slope = (wave(track, racer.x + .5, clock)[0] - wave(track, racer.x - .5, clock)[0])
                if slope > .12 and diving:
                    racer.speed = min(320, racer.speed+22)
                    racer.combo = min(3, racer.combo+1)
                    racer.combo_until = clock+120
                else:
                    racer.combo = 0
                racer.pose, racer.vy, racer.y = 'swim', 0, surface
            elif racer.vy > 0 and racer.y >= surface:
                racer.pose, racer.vy, racer.y, racer.combo = 'swim', 0, surface, 0

        for gate in track['gates'][len(racer.gates):]:
            if not previous_x < gate <= racer.x:
                break
            racer.gates.append(self.tick)
        self.collide(racer)
        if (racer.x >= track['length'] and racer.joined and len(racer.gates) == len(track['gates'])
                and self.tick <= self.deadline_tick):
            racer.finish_tick = self.tick

    def collide(self, racer):
        contact = next((i for i, (branch, x, y, w, h) in enumerate(self.track['obstacles'])
                        if branch == racer.branch and x-9 <= racer.x <= x+w+9
                        and y-7 <= racer.y <= y+h+7), None)
        if contact is not None:
            fresh = contact != racer.contact
            if fresh:
                racer.speed, racer.combo, racer.launch_until = 110, 0, -1
            _, x, y, w, h = self.track['obstacles'][contact]
            if x <= racer.x <= x+w and y <= racer.y <= y+h:
                racer.x = max(p for p in self.track['safe'][racer.branch] if p <= x-9)
                racer.y = deep_y(self.track, racer.x) if racer.branch == 'deep' else wave(self.track, racer.x, self.clock)[0]
                start, end = self.track['branch']
                if racer.x < start:
                    racer.entry = False
                racer.route_distance = clamp(racer.x-start, 0, end-start) * (
                    1-self.track['shortcut'] if racer.branch == 'deep' else 1)
                racer.freeze, racer.pose, racer.vy = 24, 'reset', 0
        racer.contact = contact

    def ranking(self):
        def score(racer):
            if racer.finish_tick is not None:
                return (2, -racer.finish_tick, 0)
            if racer.left:
                return (0, 0, 0)
            return (1, len(racer.gates), floor(racer.x))
        ordered = sorted(self.racers.values(), key=score, reverse=True)
        return [dict(slot=r.slot, rank=1 + sum(score(other) > score(r) for other in ordered),
                     finish_tick=r.finish_tick, gates=len(r.gates), progress=floor(r.x),
                     status='finished' if r.finish_tick is not None else 'departed' if r.left else 'racing')
                for r in ordered]

    def resolve(self):
        first = min((r.finish_tick for r in self.racers.values() if r.finish_tick is not None), default=None)
        if first is not None and len(self.racers) > 1:
            self.deadline_tick = min(self.start_tick+LIMIT, first+GRACE)
        unfinished = [r for r in self.racers.values() if r.finish_tick is None]
        if (not unfinished or self.tick >= self.deadline_tick or any(r.left for r in unfinished)):
            self.phase = 'finished'
            self.result = self.ranking()
            for row in self.result:
                if row['status'] == 'racing':
                    row['status'] = 'timeout' if self.tick >= self.deadline_tick else 'won_by_forfeit'

    def snapshot(self):
        return dict(race_phase=self.phase, start_tick=self.start_tick, deadline_tick=self.deadline_tick,
                    track_id=self.track_id, track_version=self.track['version'], rules_version=self.rules_version,
                    clock=self.clock, tick=self.tick, racers=[asdict(r) for r in self.racers.values()],
                    ranking=self.ranking(), result=self.result)
