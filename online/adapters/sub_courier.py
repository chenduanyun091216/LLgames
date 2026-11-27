"""Room lifecycle and input adaptation for the submarine."""
from game_core.modes.sub_courier import SIGNALS, SubCourier

ACTIONS = frozenset(('power_next', 'station_next', 'deliver', 'swap_request', *SIGNALS))


class SubCourierRoom(SubCourier):
    def __init__(self, *, mode_options, swapped=False, **options):
        super().__init__(mode_options['order'], swapped=swapped)

    def set_input(self, slot, dx, dy, shoot):
        self.inputs.pop(slot, None)

    def mode_input(self, slot, message):
        role = self.role_by_slot[slot]
        if message['type'] == 'mode_input':
            if not self.result:
                self.inputs[slot] = (message['x'] if role == 'helm' else 0,
                                     message['y'], message['held'] & (1 if role == 'helm' else 4))
            return
        action = message['action']
        if self.result:
            return 'result_pending'
        if action in ACTIONS and (role == 'engineer' or action in SIGNALS or action == 'swap_request'):
            self.actions.append((slot, action))
        else:
            return 'unsupported_action'

    def action(self, slot, action, key=None):
        return 'unsupported_action'

    def remove_player(self, slot):
        self.reset_input()
        self.finish('搭档离开，订单中止')

    def snapshot(self):
        players = [dict(slot=slot, role=role) for slot, role in self.role_by_slot.items()]
        return dict(tick=self.tick, phase=self.phase, players=players, world=self.world())
