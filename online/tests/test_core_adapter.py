import math
import unittest
from unittest.mock import patch
from game_core import config
from game_core.entities import Enemy, Bullet
from game_core.game import GameState
from online.adapters.core_adapter import OnlineGame, REVIVE_COSTS


class CoOpRulesTests(unittest.TestCase):
    def setUp(self):
        self.g = OnlineGame()
        self.p1, self.p2 = self.g.all_players

    def enemy(self):
        return Enemy(config.ENEMY_DEFS[0])

    def kill(self, p):
        self.g._damage_target = p
        p.invincible_until = 0
        self.g._damage_player(config.game_ticks(), 100, 'test')

    def test_initial_shared_resources_and_individual_health(self):
        self.assertEqual(self.g.lives, 5)
        self.assertEqual((self.p1.hp, self.p2.hp), (5, 5))
        self.p2.gold += 13
        self.assertEqual(self.p1.gold, 13)
        self.assertIs(self.p1.owned_weapons, self.p2.owned_weapons)
        self.assertIs(self.p1.owned_characters, self.p2.owned_characters)

    def test_two_inputs_move_independently_and_normalize_diagonal(self):
        a, b = self.p1.x, self.p2.x
        self.g.set_input(1, 1, 0, True)
        self.g.set_input(2, -1, -1, True)
        self.g.step()
        self.assertAlmostEqual(self.p1.x-a, 5.2)
        self.assertAlmostEqual(self.p2.x-b, -5.2 / math.sqrt(2))
        self.assertEqual(self.g.tick, 1)

    def test_invalid_input_cannot_inject_position_or_nan(self):
        self.g.set_input(1, float('nan'), 0, True)
        self.g.set_input(1, True, 0, True)
        self.g.set_input(999, 1, 0, True)
        self.assertEqual(self.g._inputs[1], (0, 0, False))

    def test_one_world_update_per_tick(self):
        enemy = self.enemy(); enemy.y = 150; enemy.speed = 1
        self.g.enemies = [enemy]
        self.g.step()
        self.assertEqual(enemy.y, 151.25)

    def test_either_shop_opener_requires_both_to_close(self):
        self.assertIsNone(self.g.action(2, 'shop_open'))
        self.assertTrue(all(p.shop_open for p in self.g.all_players))
        self.g.step(); self.assertEqual(self.g.tick, 0)
        self.g.action(2, 'shop_close'); self.g.step()
        self.assertTrue(self.g.paused); self.assertEqual(self.g.tick, 0)
        self.g.action(1, 'shop_close'); self.g.step()
        self.assertFalse(self.g.paused); self.assertEqual(self.g.tick, 1)

    def test_purchase_atomic_shared_ownership_and_exclusive_equipment(self):
        self.p1.gold = 100
        self.g.action(1, 'shop_open')
        self.assertIsNone(self.g.action(1, 'weapon', 'rifle'))
        gold = self.g.gold
        self.assertEqual(gold, 90)
        self.assertIn('rifle', self.p2.owned_weapons)
        self.assertIsNotNone(self.g.action(2, 'weapon', 'rifle'))
        self.assertEqual(self.g.gold, gold)
        self.p1.last_switch_at = -9999
        self.assertIsNone(self.g.action(1, 'weapon', 'pistol'))
        self.assertIsNone(self.g.action(2, 'weapon', 'rifle'))
        self.assertEqual(self.g.gold, gold)

    def test_character_exclusivity_and_fisher_can_be_shared(self):
        self.p1.gold = 100
        self.g.action(2, 'shop_open')
        self.assertIsNone(self.g.action(2, 'character', 'fire'))
        self.assertIsNotNone(self.g.action(1, 'character', 'fire'))
        self.assertIsNone(self.g.action(2, 'character', 'fisher'))
        self.assertIsNone(self.g.action(1, 'character', 'fire'))
        self.assertEqual(self.g.gold, 70)
        self.g.action(1, 'character', 'fisher')
        self.assertIsNone(self.p1.character); self.assertIsNone(self.p2.character)

    def test_cannot_buy_outside_shop_or_without_money(self):
        self.p1.gold = 100
        self.assertIsNotNone(self.g.action(1, 'weapon', 'rifle'))
        self.assertEqual(self.g.gold, 100)
        self.g.action(1, 'shop_open'); self.p1.gold = 0
        self.assertIsNotNone(self.g.action(1, 'character', 'ice'))
        self.assertNotIn('ice', self.p1.owned_characters)

    def test_death_is_individual_and_auto_revives_with_shared_lives(self):
        self.kill(self.p2)
        self.assertTrue(self.p1.alive); self.assertFalse(self.p2.alive)
        self.assertEqual(self.g.lives, 5)
        self.g.step()
        self.assertEqual(self.p2.x, self.g.world_size[0] // 2)
        self.assertEqual(self.p2.y, config.GAME_AREA_BOTTOM - 14)
        self.assertEqual(self.p2.invincible_until, config.game_ticks() + 1500)
        self.assertTrue(self.p2.alive); self.assertEqual(self.g.lives, 4)
        self.assertEqual(self.p2.hp, self.p2.max_hp)
        self.assertIsNotNone(self.g.action(2, 'revive'))
        self.assertEqual(self.g.lives, 4)

    def test_revive_uses_lives_before_gold(self):
        self.p1.gold = 100
        self.kill(self.p1); self.g.action(1, 'revive')
        self.assertEqual(self.g.gold, 100); self.assertEqual(self.g.lives, 4)
        self.assertEqual(self.g.revive_count, 0)

    def test_paid_revive_limit_is_shared_by_both_players(self):
        for difficulty, limit in (('easy', 5), ('medium', 4), ('hard', 3)):
            with self.subTest(difficulty=difficulty):
                game = OnlineGame(difficulty)
                p1, p2 = game.all_players
                game.lives = 0
                p1.gold = 1000
                for purchase in range(limit):
                    player = game.all_players[purchase % 2]
                    player.invincible_until = 0
                    game._damage_target = player
                    game._damage_player(0, 100, 'test')
                    self.assertIsNone(game.action(player.slot, 'revive'))
                gold = 1000 - limit * REVIVE_COSTS[difficulty]
                self.assertEqual(game.gold, gold)
                for player in (p1, p2):
                    player.invincible_until = 0
                    game._damage_target = player
                    game._damage_player(0, 100, 'test')
                    self.assertIsNotNone(game.action(player.slot, 'revive'))
                self.assertEqual(game.gold, gold)
                self.assertEqual(game.phase, 'lost')

    def test_paid_revive_prices_all_difficulties(self):
        for difficulty, price in REVIVE_COSTS.items():
            with self.subTest(difficulty=difficulty):
                game = OnlineGame(difficulty); p1, p2 = game.all_players
                game.lives = 0; p1.gold = price
                game._damage_target = p2; game._damage_player(0, 100, 'test')
                self.assertIsNone(game.action(2, 'revive'))
                self.assertEqual(game.gold, 0)
                self.assertTrue(p2.alive)

    def test_both_dead_wait_if_one_revive_is_affordable(self):
        self.g.lives = 0; self.p1.gold = 75
        self.kill(self.p1); self.kill(self.p2)
        self.assertEqual(self.g.phase, 'playing'); self.assertTrue(self.g.paused)
        self.g.action(2, 'revive')
        self.assertFalse(self.g.paused)
        self.assertEqual(self.g.gold, 0)
        self.assertIsNotNone(self.g.action(1, 'revive'))

    def test_both_dead_without_resources_ends(self):
        self.g.lives = 0; self.p1.gold = 74
        self.kill(self.p1)
        self.assertEqual(self.g.phase, 'playing')
        self.kill(self.p2)
        self.assertEqual(self.g.phase, 'lost')
        self.assertEqual(self.g.state, GameState.GAME_OVER)

    def test_every_leak_costs_each_living_player_one_hp_all_difficulties(self):
        for difficulty in REVIVE_COSTS:
            game = OnlineGame(difficulty)
            p1, p2 = game.all_players
            a,b = p1.hp,p2.hp
            p1.invincible_until = p2.invincible_until = 2000
            enemy = self.enemy(); game.enemies = [enemy]
            game._resolve_leak(enemy, 0)
            self.assertEqual((p1.hp,p2.hp), (a-1,b-1))
            self.assertEqual((p1.invincible_until,p2.invincible_until),(2000,2000))
            self.assertEqual(game.lives, 5)

    def test_leak_does_not_resurrect_or_charge_dead_player(self):
        self.kill(self.p2)
        enemy=self.enemy(); self.g.enemies=[enemy]
        self.g._resolve_leak(enemy,0)
        self.assertEqual(self.p2.hp,0); self.assertFalse(self.p2.alive)
        self.assertEqual(self.g.lives,5)

    def test_projectile_damage_hits_only_collision_target(self):
        self.p2.x=700
        self.assertIs(self.g._hit_player(self.p2.rect()),self.p2)
        self.g._damage_player(0,1,'test')
        self.assertEqual((self.p1.hp,self.p2.hp),(5,4))

    def test_overlapping_invincible_player_does_not_absorb_for_other(self):
        self.p1.x=self.p2.x
        self.p1.invincible_until=1000
        self.assertIs(self.g._hit_player(self.p1.rect()),self.p2)
        self.g._damage_player(0,1,'test')
        self.assertEqual((self.p1.hp,self.p2.hp),(5,4))

    def test_contact_damage_cooldown_per_player(self):
        enemy=self.enemy(); enemy.x=self.p1.x=self.p2.x; enemy.y=self.p1.y-20
        self.g.enemies=[enemy]
        with self.g._capture_sounds():
            self.g._damage_player_on_contacts(0)
            self.assertEqual((self.p1.hp,self.p2.hp),(4,4))
            self.p1.invincible_until=self.p2.invincible_until=0
            self.g._damage_player_on_contacts(800)
        self.assertEqual((self.p1.hp,self.p2.hp),(4,4))
        snapshot = self.g.snapshot()
        self.assertEqual(sum(event.get('key') == 'player_hit' for event in snapshot['events']), 2)
        self.assertEqual(len(snapshot['world']['collections']['explosions']), 2)

    def test_water_heal_uses_caster_not_player_one(self):
        self.p2.owned_characters.append('water')
        self.g.try_switch_character('water',self.p2)
        self.p2.hp=3; self.p1.hp=2
        self.g.action(2,'skill1')
        self.assertEqual((self.p1.hp,self.p2.hp),(2,4))
        self.assertGreater(self.p2.invincible_until,0)
        self.assertEqual(self.p1.invincible_until,0)

    def test_skill_owner_and_cooldown_are_independent(self):
        self.g.action(1,'skill1'); self.g.action(2,'skill1')
        self.assertEqual(len(self.g.skill_projectiles),2)
        self.assertIs(self.g.skill_projectiles[0].owner,self.p1)
        self.assertIs(self.g.skill_projectiles[1].owner,self.p2)
        self.g.action(2,'skill1')
        self.assertEqual(len(self.g.skill_projectiles),2)

    def test_boss_signature_can_damage_both_players(self):
        self.g._trigger_boss(); self.g.boss.y=60; self.g.boss.entered=True
        self.g._try_boss_signature(0,opening=True)
        sig=self.g.boss.signature
        self.p1.x=self.p2.x=sig.target_x-46
        x,y,r=sig._claws(500)[0]
        self.p1.y=self.p2.y=y
        self.g._update_boss_signature(500)
        self.assertLess(self.p1.hp,5); self.assertEqual(self.p1.hp,self.p2.hp)

    def test_enemy_kill_reward_once_and_first_level_boss(self):
        enemy=self.enemy(); self.g.enemies=[enemy]
        self.g.level_kills=self.g._campaign_value(config.CAMPAIGN_KILLS)-1
        self.g._kill_enemy(enemy); self.g._kill_enemy(enemy)
        self.assertEqual(self.g.kill_count,1)
        self.assertEqual(self.g.state,GameState.PLAYING)
        self.g.background_scroll_ticks = 40 * config.FPS - 1
        self.g.step()
        self.assertEqual(self.g.state,GameState.BOSS_FIGHT)
        self.assertEqual(self.g.boss.bdef['key'],'boss_lobster')
        snapshot = self.g.snapshot()
        self.assertEqual(snapshot['boss_remaining_ms'], 0)
        self.assertEqual(snapshot['world']['game']['background_scroll_ticks'], 40 * config.FPS)

    def test_campaign_transitions_and_final_victory_rewards_once(self):
        for level in range(1, len(config.LEVEL_CONFIGS) + 1):
            self.assertEqual(self.g.current_level, level)
            self.g.enemies.append(self.enemy())
            self.g._level_complete(); gold = self.g.gold
            self.g._level_complete()
            self.assertEqual(self.g.gold, gold)
            self.assertFalse(self.g.enemies)
            self.assertTrue(self.g.particles)
            if level < len(config.LEVEL_CONFIGS):
                self.assertEqual(self.g.state, GameState.LEVEL_TRANSITION)
                for _ in range(120):
                    self.g.step()
            else:
                for _ in range(25):
                    self.g.step()
                self.assertFalse(self.g.particles)
                self.assertEqual(self.g.phase, 'won')
                self.assertEqual(self.g.current_level, 11)
        self.assertRaises(ValueError, self.g._start_level, 12)

    def test_headless_visual_records_expire_without_rendering(self):
        self.g.muzzle_flashes = [(self.p1, 0, 'pistol'), (self.p2, 911, 'rifle')]
        self.g.water_heal_effects = [(self.p1, 0), (self.p2, 201)]
        self.g.laser_impacts = [(1, 2, 699), (2, 3, 700)]
        self.g.gift_messages = [('old', (1,2,3), 1000, 0), ('new', (1,2,3), 1001, 0)]
        self.g.skill_flash = (1, 2, 660, (1,2,3))
        self.g._expire_visuals(1000)
        self.assertEqual(len(self.g.muzzle_flashes), 1)
        self.assertEqual(len(self.g.water_heal_effects), 1)
        self.assertEqual(len(self.g.laser_impacts), 1)
        self.assertEqual(len(self.g.gift_messages), 1)
        self.assertIsNone(self.g.skill_flash)

    def test_sustained_fire_does_not_accumulate_visual_records(self):
        self.g.spawn_interval = 10**10
        for _ in range(3600):
            self.g.set_input(1, 0, 0, True)
            self.g.set_input(2, 0, 0, True)
            self.g.step()
            self.assertLessEqual(len(self.g.muzzle_flashes), 2)
        self.assertLessEqual(len(self.g._events), 48)
        self.assertTrue(all(config.game_ticks()-f[1] < 90 for f in self.g.muzzle_flashes))

    def test_dead_player_cannot_act_or_steal_reserved_equipment(self):
        self.p1.owned_weapons.append('rifle'); self.p2.current_weapon='rifle'
        self.kill(self.p2)
        self.assertIsNotNone(self.g.action(2,'skill1'))
        self.assertIsNotNone(self.g.action(1,'weapon','rifle'))


if __name__ == '__main__':
    unittest.main()
