import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import pygame

from game_core import config
from game_core.entities import GiftBox
from game_core.game import Game
from online.adapters.core_adapter import OnlineGame


class FireSpeedTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        pygame.display.set_mode((960, 720))
        self.addCleanup(pygame.quit)
        self.addCleanup(setattr, config, 'campaign_time_ms', config.campaign_time_ms)
        config.campaign_time_ms = 10000

    def assert_shot_gap(self, player, now, gap):
        player.last_shot_time = now - gap + 1
        self.assertFalse(player.can_shoot(now))
        player.last_shot_time -= 1
        self.assertTrue(player.can_shoot(now))

    def test_campaign_buffs_stack_in_pc_and_web(self):
        for web in (False, True):
            with self.subTest(web=web):
                game = Game(desktop_controls=not web, web=web, mobile_web=web)
                game._start_game('hard')
                player = game.player
                player.owned_characters.append('water')
                self.assertTrue(game.try_switch_character('water'))
                player.character_upgrades['water'] = 1
                gift = GiftBox()
                gift.kind = 'haste'
                with patch('game_core.game.random.random', return_value=0):
                    game._handle_mobile_action('skill2')
                game._open_gift_box(gift, 10000)
                self.assert_shot_gap(player, 10000, 103)
                player.current_weapon = 'rifle'
                player.weapon_upgrades['rifle'] = 3
                self.assert_shot_gap(player, 10000, 57)
                player.current_weapon = 'pistol'
                game._activate_rage()
                self.assert_shot_gap(player, 10000, 44)
                self.assert_shot_gap(player, 12000, 66)
                self.assert_shot_gap(player, 16000, 86)
                self.assert_shot_gap(player, 20000, 172)
                self.assert_shot_gap(player, 30000, 400)

    def test_retry_restores_remaining_time_for_each_layer(self):
        game = Game(desktop_controls=True)
        game._start_game('hard')
        gift = GiftBox()
        gift.kind = 'haste'
        game._open_gift_box(gift, 10000)
        game._open_gift_box(gift, 11000)
        config.campaign_time_ms = 12000
        game._start_level(2)
        config.campaign_time_ms = 30000
        game._retry_level()
        self.assert_shot_gap(game.player, 37999, 100)
        self.assert_shot_gap(game.player, 38000, 200)
        self.assert_shot_gap(game.player, 39000, 400)

    def test_online_water_skills_from_both_players_stack_and_expire_separately(self):
        game = OnlineGame(mode='infinite')
        first, second = game.all_players
        for player in (first, second):
            player.current_weapon = 'pistol'
        self.assertIsNone(game.action(1, 'character', 'water'))
        first.character_upgrades['water'] = 1
        with patch('game_core.game.random.random', return_value=0):
            config.campaign_time_ms = 10000
            self.assertIsNone(game.action(1, 'skill1'))
            config.campaign_time_ms = 11000
            self.assertIsNone(game.action(1, 'character', 'ice'))
            self.assertIsNone(game.action(2, 'character', 'water'))
            self.assertIsNone(game.action(2, 'skill1'))
        for player in (first, second):
            self.assert_shot_gap(player, 11000, 85)
            self.assert_shot_gap(player, 12000, 128)
            self.assert_shot_gap(player, 13000, 191)
            self.assert_shot_gap(player, 15000, 286)
            self.assert_shot_gap(player, 16000, 429)
