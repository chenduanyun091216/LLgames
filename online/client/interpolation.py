"""Bounded interpolation for positions and background scrolling."""
import math
from collections import deque


class PositionBuffer:
    delay_ms = 100

    def __init__(self):
        self.frames = deque(maxlen=12)
        self.context = None
        self.offset = None

    def push(self, state, now):
        world = state['world']
        stamp = world['time_ms']
        game = world['game']
        scroll = game.get('background_scroll_ticks', 0)
        context = (state.get('match_id'), state.get('orientation'),
                   game.get('current_level'), game.get('infinite_background_level'),
                   game.get('infinite_mode'), state.get('phase'), state.get('paused'))
        if (context != self.context or self.offset is None
                or self.frames and (stamp < self.frames[-1][0]
                                    or now - self.frames[-1][2] > 250
                                    or scroll < self.frames[-1][3])):
            self.frames.clear()
            self.offset = now - stamp
            self.context = context
        if self.frames and stamp == self.frames[-1][0]:
            return
        # Anchor to the least delayed arrival, without following packet jitter.
        self.offset = min(self.offset, now - stamp)
        points = {}
        for record in world['objects']:
            fields = record['fields']
            if 'x' in fields and 'y' in fields:
                points[record['id']] = (fields['x'], fields['y'])
        self.frames.append((stamp, points, now, scroll))

    def sample(self, now):
        if not self.frames:
            return {}, None
        target = now - self.offset - self.delay_ms
        while len(self.frames) > 2 and self.frames[1][0] <= target:
            self.frames.popleft()
        first, last = self.frames[0], self.frames[-1]
        for frame in self.frames:
            if frame[0] >= target:
                last = frame
                break
            first = frame
        span = last[0] - first[0]
        alpha = max(0, min(1, (target - first[0]) / span)) if span else 1
        result = {}
        for ident, end in last[1].items():
            start = first[1].get(ident, end)
            # Respawns/teleports snap instead of sweeping across the arena.
            if abs(end[0] - start[0]) + abs(end[1] - start[1]) > 160:
                start = end
            result[ident] = tuple(a + (b - a) * alpha for a, b in zip(start, end))
        scroll = first[3] + (last[3] - first[3]) * alpha
        return result, scroll


class LocalPrediction:
    """Predict movement locally and reconcile against acknowledged input time."""

    def __init__(self):
        self.position = None
        self.history = deque(maxlen=180)
        self.sent = deque(maxlen=120)
        self.correction = (0, 0)
        self.history_offset = (0, 0)
        self.last_frame = None
        self.received = None

    def sent_input(self, sequence, now):
        if type(sequence) is int:
            self.sent.append((sequence, now))

    def reconcile(self, position, sequence, age_ms, now):
        self.received = now
        if self.position is None:
            self.position = position
            return
        sent_at = next((at for seq, at in reversed(self.sent) if seq == sequence), None)
        if sent_at is None or not self.history:
            return
        acknowledged_at = sent_at + age_ms / 1000
        before = after = self.history[-1]
        for row in reversed(self.history):
            before = row
            if row[0] <= acknowledged_at:
                break
            after = row
        span = after[0] - before[0]
        alpha = max(0, min(1, (acknowledged_at - before[0]) / span)) if span else 1
        expected = tuple(a + (b - a) * alpha + offset
                         for a, b, offset in zip(before[1], after[1], self.history_offset))
        error = tuple(a - b for a, b in zip(position, expected))
        if max(map(abs, error)) > 160:
            self.position = position
            self.history.clear()
            self.history_offset = (0, 0)
            self.correction = (0, 0)
            return
        self.position = tuple(a + b for a, b in zip(self.position, error))
        # Rebase the recorded path without rewriting it on every snapshot.
        self.history_offset = tuple(a + b for a, b in zip(self.history_offset, error))
        self.correction = tuple(a - b for a, b in zip(self.correction, error))

    def advance(self, now, axis, speed, clamp):
        elapsed = 0 if self.last_frame is None else min(.05, max(0, now - self.last_frame))
        self.last_frame = now
        if self.position is None:
            return None
        if self.received is None or now - self.received > .25:
            axis = (0, 0)
        length = max(1, math.hypot(*axis))
        self.position = clamp(tuple(p + v / length * speed * elapsed
                                    for p, v in zip(self.position, axis)))
        self.history.append((now, tuple(p - offset for p, offset in zip(self.position, self.history_offset))))
        decay = max(0, 1 - elapsed / .08)
        self.correction = tuple(value * decay for value in self.correction)
        return clamp(tuple(a + b for a, b in zip(self.position, self.correction)))
