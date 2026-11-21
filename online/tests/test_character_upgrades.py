import json
import unittest
from unittest.mock import patch

import pygame

from game_core import config
from online.adapters.core_adapter import OnlineGame
from online.adapters.presentation import Presentation


class OnlineCharacterUpgradesTests(unittest.TestCase):
    def test_ice_countdown_follows_the_casting_slot_in_the_snapshot(self):
        self.addCleanup(setattr, config, 'campaign_time_ms', config.campaign_time_ms)
        game = OnlineGame(mode='infinite', orientation='portrait')
        game.all_players[1].character_upgrades['ice'] = 3
        game.action(2, 'character', 'ice')
        game.step()
        with patch('game_core.game.random.random', return_value=0):
            game.action(2, 'skill1')
        data = json.loads(json.dumps(game.snapshot()))
        self.assertEqual(data['world']['game']['ice_field_slot'], 2)
        deadline = data['world']['time_ms'] + 2000
        self.assertEqual(data['world']['game']['enemy_freeze_until'], deadline)

        presentation = Presentation(pygame.Surface(game.world_size), integrated=True)
        with patch('online.adapters.presentation.play_sound'):
            presentation.apply(data, local_slot=1)
        with patch('game_core.game.draw_player_fields') as draw:
            presentation.draw()
        self.assertEqual([(args[1].slot, kwargs['ice_until']) for args, kwargs in draw.call_args_list],
                         [(1, 0), (2, deadline)])

    def test_shared_shop_and_independent_shields_survive_snapshot_and_draw(self):
        game = OnlineGame(mode='infinite', orientation='portrait')
        first, second = game.all_players
        price = game._character_cost(config.CHARACTER_DEFS['fire'])
        first.gold = price * 3
        self.assertIsNotNone(game.action(1, 'upgrade', 'fire'))
        self.assertEqual(first.gold, price * 3)
        self.assertIsNone(game.action(1, 'shop_open'))
        for slot, level in ((1, 1), (2, 2), (1, 3)):
            self.assertEqual(game.action(slot, 'upgrade', 'fire'), f'已加强至 Lv.{level}')
            self.assertEqual(second.gold, price * (3 - level))
        self.assertEqual(game.action(2, 'upgrade', 'fire'), '角色已满级')
        self.assertIsNone(game.action(2, 'character', 'fire'))
        game.action(1, 'shop_close')
        with patch('game_core.game.random.random', return_value=.249) as roll:
            game.action(2, 'skill2')
            roll.assert_called_once_with()

        game._damage_target = first
        game._damage_player(config.game_ticks(), 100, 'test')
        self.assertEqual((first.hp, second.hp), (5, 5))
        data = json.loads(json.dumps(game.snapshot()))
        self.assertEqual([p['character_upgrades']['fire'] for p in data['world']['players']], [3, 3])
        self.assertEqual([p['fire_shield_hits'] for p in data['world']['players']], [2, 3])
        surface = pygame.Surface(game.world_size)
        presentation = Presentation(surface, integrated=True)
        with patch('online.adapters.presentation.play_sound'):
            presentation.apply(data, local_slot=2)
        presentation.draw()
        self.assertEqual(presentation.view.player.fire_shield_hits, 3)
        self.assertEqual(presentation.view.player.character_upgrades, {'fire': 3})

    def test_water_and_radiation_reach_living_teammates(self):
        game = OnlineGame(mode='infinite')
        first, second = game.all_players
        first.character_upgrades.update(water=1, radiation=3)
        game.action(1, 'character', 'water')
        game.action(2, 'character', 'radiation')
        game.step()
        now = config.game_ticks()
        with patch('game_core.game.random.random', return_value=0):
            game.action(1, 'skill1')
            game.action(2, 'dart')
        self.assertEqual([p.swift_field_until for p in (first, second)], [now + 2000] * 2)
        self.assertEqual([p.damage_multiplier(now) for p in (first, second)], [2, 2])
        game.remove_player(2)
        game.action(1, 'character', 'radiation')
        game.tick = 60 * 7
        game.step()
        with patch('game_core.game.random.random', return_value=0):
            game.action(1, 'dart')
        self.assertGreater(first.radiation_field_until, second.radiation_field_until)
