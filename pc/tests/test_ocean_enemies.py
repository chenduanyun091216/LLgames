import os
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
import pygame

from game_core import config
from game_core.asset_loader import image_asset
from game_core.entities import Enemy
from game_core.game import TEMPLE_WORM


OCEAN_KEYS = {
    'puffer', 'scallop', 'mantis_shrimp', 'nudibranch',
    'flounder', 'anglerfish', 'sea_cucumber', 'cuttlefish',
}
ORIGINAL_ACTION_KEYS = {
    'lobster', 'crab', 'goldfish', 'crab_red', 'jellyfish', 'octopus_pink',
    'seahorse', 'starfish', 'turtle', 'octopus', 'shark',
}
CAMPAIGN_ACTION_KEYS = set(config.FACTORY_ENEMY_KEYS + config.TEMPLE_ENEMY_KEYS + ['ancient_worm'])


class OceanEnemiesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    def test_all_eight_share_the_first_eight_level_pools(self):
        for level in config.LEVEL_CONFIGS:
            with self.subTest(level=level['level']):
                enemies = config.get_level_enemy_defs(level)
                keys = {enemy['key'] for enemy in enemies if not enemy['is_large']}
                self.assertEqual(keys & OCEAN_KEYS, OCEAN_KEYS if level['level'] <= 8 else set())

    def test_each_enemy_draws_its_action_pose_without_changing_hitbox(self):
        canvas = pygame.Surface((config.SCREEN_WIDTH, 240), pygame.SRCALPHA)
        for definition in [*config.ENEMY_DEFS, TEMPLE_WORM]:
            if definition['key'] not in OCEAN_KEYS | ORIGINAL_ACTION_KEYS | CAMPAIGN_ACTION_KEYS:
                continue
            with self.subTest(enemy=definition['key']):
                enemy = Enemy(definition)
                enemy.y = 90
                rect = enemy.rect()
                action_asset = f'enemies/enemy_{definition["key"]}_action.png'
                for age, asset in ((1000, enemy.sprite_asset), (3200, action_asset)):
                    self.assertIsNotNone(image_asset(asset))
                    with patch.object(config, 'game_ticks', return_value=enemy.breath_start_time + age), \
                         patch('game_core.entities.blit_lit_sprite') as blit:
                        enemy.draw(canvas)
                    self.assertEqual(blit.call_args.kwargs['source'], asset)
                    self.assertEqual(enemy.rect(), rect)

    def test_zongzong_keeps_its_existing_sprite_during_the_action_window(self):
        definition = next(enemy for enemy in config.ENEMY_DEFS if enemy['key'] == 'zongzong')
        enemy = Enemy(definition)
        enemy.y = 90
        canvas = pygame.Surface((config.SCREEN_WIDTH, 240), pygame.SRCALPHA)
        with patch.object(config, 'game_ticks', return_value=enemy.breath_start_time + 3200), \
             patch('game_core.entities.blit_lit_sprite') as blit:
            enemy.draw(canvas)
        self.assertEqual(blit.call_args.kwargs['source'], 'bosses/zongzong.png')
