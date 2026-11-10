"""Input-only opening-level bots through advancement to level two, not a device test."""
import json
import random
import time
from online.adapters.core_adapter import OnlineGame


def run(difficulty):
    random.seed(76)
    game = OnlineGame(difficulty)
    started = time.perf_counter()
    sizes, steps = [], []
    for frame in range(60 * 240):
        if game.phase != 'playing' or game.current_level > 1:
            break
        targets = sorted(game.enemies, key=lambda e: e.y, reverse=True)
        if game.boss:
            targets.append(game.boss)
        for player in game.all_players:
            if not player.alive:
                game.action(player.slot, 'revive')
                continue
            target = targets[min(player.slot - 1, len(targets) - 1)] if targets else None
            target_x = target.x if target else 390 + (player.slot - 1) * 180
            dx = max(-1, min(1, (target_x - player.x) / 5.2))
            game.set_input(player.slot, dx, 0, True)
            if target:
                game.action(player.slot, 'skill1')
        tick_start = time.perf_counter()
        game.step()
        steps.append(time.perf_counter() - tick_start)
        if frame % 3 == 0:
            sizes.append(len(json.dumps(game.snapshot(), ensure_ascii=False, separators=(',', ':')).encode()))
    report = {'difficulty': difficulty, 'phase': game.phase, 'current_level': game.current_level, 'ticks': game.tick,
              'simulation_seconds': round(game.tick / 60, 2),
              'wall_seconds': round(time.perf_counter() - started, 3),
              'kills': game.level_kills, 'lives': game.lives, 'gold': game.gold,
              'mean_snapshot_bytes': round(sum(sizes) / len(sizes)),
              'max_snapshot_bytes': max(sizes),
              'p95_step_ms': round(sorted(steps)[int(len(steps) * .95)] * 1000, 3)}
    if game.current_level < 2:
        raise AssertionError(report)
    return report


if __name__ == '__main__':
    print(json.dumps([run(d) for d in ('easy', 'medium', 'hard')], indent=2))
