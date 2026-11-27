"""One authoritative submarine shared by the helm and engineering seats."""
import json
import math
from pathlib import Path

HZ = 60
HALF_W, HALF_H = 50, 20
TOP, BOTTOM = 58, 405
POWER = ('标准', '强推', '静音', '关机')
STATIONS = ('泵', '货架', '交货台')
SIGNALS = {
    'signal_dive': '下潜', 'signal_slow': '减速',
    'signal_cargo': '货舱异常', 'signal_dock': '可以靠港',
}
CONTENT = json.loads((Path(__file__).resolve().parents[2] / 'assets' / 'modes' /
                      'sub_courier' / 'routes.json').read_text(encoding='utf-8-sig'))
ORDERS = CONTENT['orders']


def toward(value, target, amount):
    return value + max(-amount, min(amount, target - value))


class SubCourier:
    def __init__(self, order='jelly', *, swapped=False):
        self.order = order
        self.route = ORDERS[order]
        self.role_by_slot = {1: 'engineer' if swapped else 'helm',
                             2: 'helm' if swapped else 'engineer'}
        self.epoch = 0
        self.phase = 'playing'
        self.tick = 0
        self.loading_ticks = 120
        self.remaining_ticks = self.route['limit'] * HZ
        self.x, self.y = 65., 230.
        self.vx = self.vy = 0.
        self.ballast = 50.
        self.power = self.station = 0
        self.hull = 100.
        self.integrity = 100
        self.wake = self.peak_wake = 0.
        self.leak = False
        self.loose = self.cargo_triggered = False
        self.dock_ticks = self.work = self.gate_until = 0
        self.gate_used = self.gate_attempted = False
        self.contacts = set()
        self.slot_signals = {}
        self.records = {s: dict(helm_ticks=0, engine_ticks=0, impacts=0, repairs=0, latches=0, deliveries=0)
                        for s in self.role_by_slot}
        self.swap = None
        self.swap_status = ('', 0)
        self.result = None
        self.event_id = 0
        self.events = []
        self.inputs = {}
        self.actions = []
        self.operated = False
        self.operation_locked = False
        self.intent = (0, 0)

    def cue(self, name):
        self.event_id += 1
        self.events.append((self.event_id, name))
        self.events = self.events[-12:]

    def reset_input(self):
        self.epoch += 1
        self.inputs.clear()
        self.actions.clear()
        self.swap = None
        self.swap_status = ('', 0)
        self.intent = (0, 0)
        self.work = 0
        self.operated = self.operation_locked = False

    def slots(self):
        helm = 1 if self.role_by_slot[1] == 'helm' else 2
        return helm, 3 - helm

    def contained(self, box):
        left, right, top, bottom = box
        return (left <= self.x - HALF_W and self.x + HALF_W <= right
                and top <= self.y - HALF_H and self.y + HALF_H <= bottom)

    def flow(self):
        for left, right, top, bottom, vx, vy in self.route['flows']:
            if left <= self.x < right and top <= self.y < bottom:
                return vx, vy
        return 0, 0

    def gate_open(self):
        return self.tick < self.gate_until

    def finish(self, reason, engineer=None):
        if self.result:
            return
        success = reason == '已签收'
        ticks = self.route['limit'] * HZ - self.remaining_ticks
        stars = 0
        if success:
            self.records[engineer]['deliveries'] += 1
            self.cue('deliver')
            if self.order == 'jelly':
                stars = 1 + (self.integrity >= 85) + (ticks <= 145 * HZ)
            elif self.order == 'express':
                stars = 1 + (ticks <= 112 * HZ) + (self.hull >= 75)
            else:
                stars = 1 + (self.peak_wake < 60) + (ticks <= 175 * HZ)
        self.phase = 'won' if success else 'lost'
        self.result = dict(result_id=f'courier-{self.tick}', success=success, reason=reason,
                           ticks=ticks, stars=stars, integrity=self.integrity,
                           hull=self.hull, peak_wake=self.peak_wake, shortcut=self.gate_used,
                           records={slot: rec.copy() for slot, rec in self.records.items()})

    def commands(self, engineer):
        # A confirmed swap invalidates the old epoch before any other command
        # from that tick can touch the machinery.
        for slot, action in self.actions:
            if action != 'swap_request':
                continue
            if self.swap is None:
                self.swap = (slot, self.tick + 3 * HZ)
                self.swap_status = ('已申请换岗，搭档按 L 或「换岗」确认', self.tick + 3 * HZ)
            elif self.swap[0] != slot:
                self.role_by_slot[1], self.role_by_slot[2] = self.role_by_slot[2], self.role_by_slot[1]
                self.reset_input()
                self.swap_status = ('岗位已交换', self.tick + 2 * HZ)
                return False, True
        deliver = False
        for slot, action in self.actions:
            if action in SIGNALS:
                self.slot_signals[3 - slot] = (SIGNALS[action], self.tick + 2 * HZ)
            elif slot == engineer:
                if action == 'power_next':
                    self.power = (self.power + 1) % len(POWER)
                    self.cue('power')
                elif action == 'station_next':
                    self.station = (self.station + 1) % len(STATIONS)
                    self.work = 0
                    self.operation_locked = self.operated
                    deliver = False
                elif action == 'deliver' and self.station == 2 and not self.operation_locked:
                    deliver = True
        self.actions.clear()
        return deliver, False

    def machinery(self, engineer, dy, operating):
        self.ballast = min(100., max(0., self.ballast + dy * .5))
        if not operating:
            self.work = 0
            self.operation_locked = False
        elif not self.operation_locked:
            duration = 120 if self.station == 0 and self.leak else 60 if self.station == 1 and self.loose else 0
            if duration:
                self.work += 1
                if self.work == duration:
                    if self.station == 0:
                        self.leak = False
                        self.records[engineer]['repairs'] += 1
                    else:
                        self.loose = False
                        self.records[engineer]['latches'] += 1
                    self.cue('latch')
                    self.operation_locked = True
                    self.work = 0
        self.operated = operating
        gate = self.route.get('gate')
        if gate and not self.gate_attempted and self.contained(gate['wait']) and self.ballast >= 70 and dy > 0:
            self.gate_attempted = True
            self.gate_until = self.tick + gate['duration'] * HZ
            self.cue('latch')

    def move(self, helm, dx, dy, slow):
        power = 0 if self.order == 'express' and self.loose and self.power == 1 else self.power
        forward = (108, 150, 70, 0)[power]
        reverse = min(50, forward)
        self.intent = (dx, dy)
        fx, fy = self.flow()
        target_x = dx * (forward if dx >= 0 else reverse)
        if slow:
            target_x = max(-12, min(12, target_x))
        self.vx = toward(self.vx, fx + target_x, 65 / HZ)
        self.vy = toward(self.vy, fy + (self.ballast - 50) * 1.1 + (dy * 26 if forward else 0), 65 / HZ)
        gate = self.route.get('gate')
        boxes = [*self.route['obstacles'], (-100, 0, TOP, BOTTOM),
                 (self.route['dock'][1] + 65, self.route['dock'][1] + 200, TOP, BOTTOM),
                 (-100, 14000, -50, TOP), (-100, 14000, BOTTOM, 500)]
        # When the timer expires, an uncompleted transit can still back out.
        if gate and not self.gate_open() and not self.gate_used:
            if self.x <= gate['entry'][0] - HALF_W:
                boxes.append(gate['entry'])
            boxes.append((gate['exit'], gate['exit'] + 50, 315, BOTTOM))
        contacts = set()
        for axis in (0, 1):
            velocity = self.vx if axis == 0 else self.vy
            if axis == 0:
                self.x += velocity / HZ
            else:
                self.y += velocity / HZ
            for index, (left, right, top, bottom) in enumerate(boxes):
                if (self.x + HALF_W <= left or self.x - HALF_W >= right
                        or self.y + HALF_H <= top or self.y - HALF_H >= bottom):
                    continue
                if not velocity:
                    continue
                face = index, axis, velocity > 0
                contacts.add(face)
                if abs(velocity) > 35 and face not in self.contacts:
                    self.impact(helm)
                if axis == 0:
                    self.x, self.vx = (left - HALF_W if velocity > 0 else right + HALF_W), 0.
                else:
                    self.y, self.vy = (top - HALF_H if velocity > 0 else bottom + HALF_H), 0.
        self.contacts = contacts
        if gate and self.gate_open() and self.x - HALF_W >= gate['exit'] and self.y - HALF_H >= 315:
            self.gate_used = True

    def impact(self, helm):
        self.cue('impact')
        self.hull = max(0., self.hull - 15)
        self.records[helm]['impacts'] += 1
        if sum(r['impacts'] for r in self.records.values()) == 2:
            self.leak = True
            self.cue('leak')
        if self.order == 'jelly':
            self.integrity = max(0, self.integrity - (5 if self.power == 2 else 12) - (5 if self.loose else 0))
        elif self.order == 'calf':
            self.wake += 15

    def step(self):
        if self.result:
            return
        self.tick += 1
        if self.loading_ticks:
            self.loading_ticks -= 1
            self.actions.clear()
            return
        if self.swap and self.tick > self.swap[1]:
            self.swap = None
            self.swap_status = ('换岗请求已超时', self.tick + 2 * HZ)
        helm, engineer = self.slots()
        deliver, swapped = self.commands(engineer)
        if swapped:
            helm, engineer = self.slots()
        dx, dy, held = self.inputs.get(helm, (0, 0, 0))
        _, ballast, operating = self.inputs.get(engineer, (0, 0, 0))
        self.records[helm]['helm_ticks'] += 1
        self.records[engineer]['engine_ticks'] += 1
        self.machinery(engineer, ballast, bool(operating & 4))
        self.move(helm, dx, dy, bool(held & 1))
        if not self.cargo_triggered and self.x >= self.route.get('cargo_event', math.inf):
            self.cargo_triggered = self.loose = True
            self.cue('cargo')
        if self.leak:
            self.hull = max(0., self.hull - 1 / HZ)
        if self.order == 'calf':
            quiet = any(a <= self.x < b for a, b in self.route['quiet'])
            if self.wake >= 100:
                self.wake = 100.
            elif self.power >= 2:
                self.wake -= 6 / HZ
            elif quiet:
                self.wake += (12 if self.power == 1 else 3) / HZ
            self.wake = max(0., min(100., round(self.wake, 8)))
            if int(self.wake // 25) > int(self.peak_wake // 25):
                self.cue('whale')
            self.peak_wake = max(self.peak_wake, self.wake)
        self.dock_ticks = min(60, self.dock_ticks + 1) if (
            self.contained(self.route['dock']) and math.hypot(self.vx, self.vy) < 15) else 0
        self.remaining_ticks -= 1
        if self.hull <= 0:
            self.finish('船体损毁')
        elif self.integrity <= 0:
            self.finish('货物破损')
        elif self.wake >= 100:
            self.finish('幼鲸惊醒')
        elif self.dock_ticks == 60 and deliver:
            self.finish('已签收', engineer)
        elif self.remaining_ticks == 0:
            self.finish('订单超时')

    def world(self):
        return dict(
            kind='mode', schema=1, mode='sub_courier', content_id=self.order,
            content_version=CONTENT['version'], view_size=[960, 540], epoch=self.epoch,
            phase='loading' if self.loading_ticks and not self.result else self.phase,
            actors=[dict(id='submarine', x=self.x, y=self.y, vx=self.vx, vy=self.vy)],
            role_by_slot=self.role_by_slot.copy(), loading_ticks=self.loading_ticks,
            route_segment=min(3, 1 + sum(self.x >= x for x, _ in self.route['landmarks'][:-1])),
            hull=self.hull, x=self.x, y=self.y, vx=self.vx, vy=self.vy,
            ballast=self.ballast, power=self.power, station=self.station, leak=self.leak,
            cargo=dict(integrity=self.integrity, wake=self.wake, loose=self.loose, triggered=self.cargo_triggered),
            slot_signals={s: label for s, (label, until) in self.slot_signals.items() if self.tick < until},
            dock_ticks=self.dock_ticks, remaining_ticks=self.remaining_ticks, result=self.result,
            runtime=dict(flow=self.flow(), intent=self.intent, work=self.work,
                         swap=self.swap_status[0] if self.tick < self.swap_status[1] else '',
                         gate_ticks=max(0, self.gate_until - self.tick), gate_used=self.gate_used,
                         gate_attempted=self.gate_attempted, events=list(self.events)))
