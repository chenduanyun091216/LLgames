"""Authoritative room adapter for flying fish racing."""
from game_core.modes.tide_race import Race, VIEW


class TideRaceRoom:
    def __init__(self, mode_options, **_):
        self.race = Race(mode_options['track'], (1, 2))
        self.epoch = 0
        self.inputs = {}
        self.launches = set()

    @property
    def phase(self):
        return 'finished' if self.result is not None else 'playing'

    @property
    def result(self):
        return self.race.result

    def required_slots(self):
        return {r.slot for r in self.race.racers.values() if r.finish_tick is None and not r.left}

    def invalidate(self):
        self.epoch += 1
        self.inputs.clear()
        self.launches.clear()
        for racer in self.race.racers.values():
            racer.launch_until = -1

    def set_input(self, slot, dx, dy, shoot):
        self.inputs.pop(slot, None)

    def mode_input(self, slot, message):
        if slot not in self.required_slots() or self.result is not None:
            return None
        if message['type'] == 'mode_action':
            if message['action'] != 'launch':
                return 'invalid_mode_action'
            if self.race.phase == 'racing':
                self.launches.add(slot)
        else:
            if 'aim' in message or 'aim8' in message or message['held'] & ~2:
                return 'invalid_mode_input'
            self.inputs[slot] = (message['x'], message['y'], message['held'])
        return None

    def action(self, slot, action, key=None):
        return 'unsupported_action'

    def remove_player(self, slot):
        # Departures are processed against the last completed authoritative step.
        self.race.depart((slot,))

    def step(self):
        self.race.step(self.inputs, self.launches)
        self.launches.clear()

    def snapshot(self):
        world = self.race.snapshot()
        world.update(kind='mode', schema=1, mode='tide_race', epoch=self.epoch,
                     content_id=world['track_id'], content_version=world['track_version'],
                     view_size=VIEW, phase=world['race_phase'])
        return dict(tick=self.race.tick, phase=self.phase, players=[], world=world)
