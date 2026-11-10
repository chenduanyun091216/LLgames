"""Nine-boss server/snapshot/render stress with explicit survival fixtures.

This deliberately sets high test HP/lives and enters each boss directly. It tests
AI, transport serialization and original rendering together, NOT a normal
campaign completion, balance, real browser, or mobile performance.
"""
import json
import random
import time
import pygame
from game_core import config
from online.adapters.core_adapter import OnlineGame
from online.adapters.presentation import Presentation


def run():
    random.seed(91)
    reports = []
    for level in range(1, 10):
        game = OnlineGame('medium')
        game._start_level(level)
        if not game.boss:
            game._trigger_boss()
        boss = game.boss
        boss.entered, boss.y, boss.fight_start_time = True, 60, 0
        game.lives = 99
        for player in game.all_players:
            player.hp = player.max_hp = 10000
        view = Presentation(pygame.Surface((960, 720)))
        largest, frames, samples = 0, 0, 0
        started = time.perf_counter()
        for frame in range(1800):
            for player in game.all_players:
                if not player.alive:
                    assert game.action(player.slot, 'revive') is None
            game.step()
            assert game.phase == 'playing', (level, game.phase)
            assert game.current_level == level, (level, game.current_level)
            if level == 7 and frame == 400:
                boss.hit_by('pistol', boss.max_hp * .4)
            if level == 9 and frame in (0, 360, 720, 1080, 1440):
                boss._start_skill(('volley', 'slam', 'split', 'laser', 'storm')[frame // 360], config.game_ticks())
            if frame % 30 == 0:
                snapshot = game.snapshot()
                snapshot['match_id'] = 'stress-level-' + str(level)
                raw = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
                largest = max(largest, len(raw.encode()))
                view.apply(json.loads(raw), 2)
                view.draw()
                samples += 1
            frames += 1
        reports.append({'level': level, 'boss': boss.bdef['key'], 'ticks': frames,
                        'rendered_snapshots': samples, 'max_snapshot_bytes': largest,
                        'wall_seconds': round(time.perf_counter() - started, 3)})
    return reports


if __name__ == '__main__':
    print(json.dumps({'scope': 'Controlled setup-state AI/snapshot/render stress, not normal playthrough',
                      'results': run()}, indent=2))
