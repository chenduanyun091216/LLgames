"""Both renderer seats use the host-selected logical geometry, never device pixels."""
import json
import unittest
import pygame
from game_core import config
from online.adapters.core_adapter import OnlineGame
from online.adapters.presentation import Presentation
from online.shared.world import WORLD_SIZES


class WorldGeometryTests(unittest.TestCase):
    def test_both_clients_use_identical_room_world_on_all_new_stages(self):
        for orientation, size in WORLD_SIZES.items():
            for level in (9, 10, 11):
                with self.subTest(orientation=orientation, level=level):
                    game = OnlineGame(orientation=orientation)
                    game._start_level(level)
                    if not game.boss:
                        game._trigger_boss()
                    self.assertEqual((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), size)
                    for player in game.all_players:
                        self.assertGreaterEqual(player.rect().left, 0)
                        self.assertLessEqual(player.rect().right, size[0])
                    snapshot = json.loads(json.dumps(game.snapshot()))
                    self.assertEqual(snapshot['world_size'], list(size))
                    for slot in (1, 2):
                        view = Presentation(pygame.Surface((960, 720)))
                        view.apply(snapshot, slot)
                        view.draw()
                        self.assertEqual(view.surface.get_size(), size)
                        self.assertEqual(config.GAME_AREA_RIGHT, 720 if orientation == 'landscape' else 480)
                        self.assertEqual(config.GAME_AREA_BOTTOM, 591)
                        self.assertEqual(view.view.boss.x, game.boss.x)
                        self.assertEqual(view.view.player.slot, slot)
                    game.step()
                    self.assertEqual((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), size)

    def test_orientation_changes_geometry_not_damage_speed_or_hp(self):
        landscape = OnlineGame('hard', orientation='landscape')
        portrait = OnlineGame('hard', orientation='portrait')
        for game in (landscape, portrait):
            before = game.player.x
            game.set_input(1, 1, 0, False)
            game.step()
            self.assertAlmostEqual(game.player.x - before, 5.2)
            game._damage_target = game.player
            game._damage_player(100, 2, 'fixture')
            self.assertEqual(game.player.hp, 2)
            self.assertEqual(game.player.invincible_until, 650)
        self.assertRaises(ValueError, OnlineGame, orientation='upside_down')

    def test_revive_spawns_inside_portrait_world(self):
        game = OnlineGame(orientation='portrait')
        p = game.all_players[1]
        p.alive, p.hp = False, 0
        self.assertIsNone(game.action(2, 'revive'))
        self.assertLess(p.rect().right, 480)
        self.assertGreater(p.rect().left, 0)

    def test_reject_inconsistent_geometry_from_snapshot(self):
        game = OnlineGame()
        snapshot = game.snapshot()
        snapshot['world_size'] = [999, 999]
        view = Presentation(pygame.Surface((960, 720)))
        self.assertRaises(ValueError, view.apply, snapshot)


if __name__ == '__main__':
    unittest.main()
