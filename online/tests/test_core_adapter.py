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

    def test_death_waits_at_position_then_respawns(self):
        self.p1.x, self.p1.y = 123, 234
        self.kill(self.p1)
        self.assertFalse(self.p1.alive)
        self.assertEqual(self.g.continuing[1], 180)
        self.assertEqual((self.p1.x, self.p1.y), (123, 234))
        self.assertTrue(self.p2.alive)
        for _ in range(179):
            self.g._advance_continues()
        self.assertFalse(self.p1.alive)
        self.g._advance_continues()
        self.assertTrue(self.p1.alive)
        self.assertEqual((self.p1.x, self.p1.y),
                         (config.SCREEN_WIDTH // 2, config.GAME_AREA_BOTTOM - 14))

    def test_death_automatically_pays_or_ends_only_local_player(self):
        self.g.lives = 0
        self.p1.gold = REVIVE_COSTS['medium']
        self.kill(self.p1)
        self.assertEqual(self.p1.gold, 0)
        self.assertEqual(self.g.continuing[1], 180)
        self.kill(self.p2)
        self.assertNotIn(2, self.g.continuing)
        self.assertEqual(self.g.phase, 'playing')

    def test_initial_shared_resources_and_individual_health(self):
        self.assertEqual(self.g.lives, 5)
        self.assertEqual((self.p1.hp, self.p2.hp), (5, 5))
        self.p2.gold += 13
        self.assertEqual(self.p1.gold, 13)
        self.assertIs(self.p1.owned_weapons, self.p2.owned_weapons)
        self.assertIs(self.p1.owned_characters, self.p2.owned_characters)

    def test_weapon_upgrade_is_shared_and_used_by_teammate(self):
        for mode in ('campaign', 'infinite'):
            with self.subTest(mode=mode):
                game = OnlineGame(mode=mode)
                buyer, teammate = game.all_players
                if 'rifle' not in buyer.owned_weapons:
                    buyer.owned_weapons.append('rifle')
                buyer.gold = 1000
                cost = game._weapon_upgrade_cost('rifle')

                self.assertIsNone(game.action(1, 'shop_open'))
                self.assertEqual(game.action(1, 'upgrade', 'rifle'), '已加强至 Lv.1')
                self.assertEqual(teammate.gold, 1000 - cost)
                self.assertEqual(teammate.weapon_upgrades.get('rifle'), 1)
                self.assertEqual(game._weapon_upgrade_cost('rifle'), cost * 2)
                world = game.snapshot()['world']
                self.assertEqual([p['weapon_upgrades'].get('rifle') for p in world['players']], [1, 1])

                self.assertIsNone(game.action(2, 'weapon', 'rifle'))
                game.action(1, 'shop_close')
                with patch('game_core.game.random.random', return_value=.99):
                    self.assertTrue(game._shoot(config.game_ticks(), teammate))
                base = config.CAMPAIGN_BULLET_DAMAGE['rifle']
                self.assertAlmostEqual(game.bullets[-1].damage, base * 1.1)

    def test_infinite_departure_releases_radiation_equipment_for_teammate(self):
        for leaving in (1, 2):
            with self.subTest(leaving=leaving):
                game = OnlineGame(mode='infinite')
                remaining = 3 - leaving
                self.assertIsNone(game.action(leaving, 'character', 'radiation'))
                self.assertIsNone(game.action(leaving, 'weapon', 'rifle'))
                self.assertIsNotNone(game.action(remaining, 'character', 'radiation'))
                self.assertIsNotNone(game.action(remaining, 'weapon', 'rifle'))
                game.remove_player(leaving)
                self.assertIsNone(game.action(remaining, 'character', 'radiation'))
                self.assertIsNone(game.action(remaining, 'weapon', 'rifle'))
                self.assertIsNone(game.action(remaining, 'laser'))
                self.assertEqual(game.radiation_lasers[0].owner.slot, remaining)

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
        self.assertAlmostEqual(enemy.y, 150 + config.CAMPAIGN_MOVE_MULT[1])

    def test_opener_closes_both_shops_and_resumes_battle(self):
        for opener in (1, 2):
            with self.subTest(opener=opener):
                game = OnlineGame()
                self.assertIsNone(game.action(opener, 'shop_open'))
                self.assertTrue(all(p.shop_open for p in game.all_players))
                game.step()
                self.assertEqual(game.tick, 0)
                self.assertIsNone(game.action(opener, 'shop_close'))
                self.assertFalse(any(p.shop_open for p in game.all_players))
                game.step()
                self.assertEqual(game.tick, 1)

    def test_guest_can_close_own_shop_and_opener_departure_releases_pause(self):
        self.g.action(1, 'shop_open')
        self.g.action(2, 'shop_close')
        self.assertTrue(self.p1.shop_open)
        self.assertFalse(self.p2.shop_open)
        self.assertTrue(self.g.paused)
        self.g.action(1, 'shop_close')
        self.g.action(1, 'shop_open')
        self.g.remove_player(1)
        self.assertFalse(self.p2.shop_open)
        self.assertFalse(self.g.paused)

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
        self.assertEqual(self.g.lives, 4)
        for _ in range(180):
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
                    for _ in range(180):
                        game._advance_continues()
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
                for _ in range(180):
                    game._advance_continues()
                self.assertEqual(game.gold, 0)
                self.assertTrue(p2.alive)

    def test_both_dead_wait_if_one_revive_is_affordable(self):
        self.g.lives = 0; self.p1.gold = 75
        self.kill(self.p1); self.kill(self.p2)
        self.assertEqual(self.g.phase, 'playing'); self.assertTrue(self.g.paused)
        for _ in range(180):
            self.g.step()
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
        self.assertEqual(self.g.lives,4)

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

    def test_water_skills_support_both_living_players_in_each_mode(self):
        for mode, caster_slot in (('campaign', 2), ('infinite', 1)):
            with self.subTest(mode=mode, caster=caster_slot):
                game = OnlineGame(mode=mode)
                p1, p2 = game.all_players
                caster = game.all_players[caster_slot - 1]
                if 'water' not in caster.owned_characters:
                    caster.owned_characters.append('water')
                game.action(caster_slot, 'character', 'water')
                p1.hp = p1.max_hp - 2
                self.assertIsNone(game.action(caster_slot, 'skill1'))
                self.assertEqual((p1.hp, p2.hp), (p1.max_hp - 1, p2.max_hp + 1))
                self.assertEqual((p1.temp_hp_until, p2.temp_hp_until),
                                 (0, 15000 if mode == 'infinite' else 8000))
                self.assertEqual([p for p, _ in game.water_heal_effects], [p1, p2])
                for p in (p1, p2):
                    self.assertEqual(p.invincible_until, 2000 if mode == 'infinite' else 800)
                    self.assertEqual(p.water_haste_until, 5000 if mode == 'infinite' else 0)
                self.assertIsNone(game.action(caster_slot, 'skill1'))
                self.assertEqual(len(game.water_heal_effects), 2)
                self.assertIsNone(game.action(caster_slot, 'skill2'))
                for p in (p1, p2):
                    self.assertEqual(p.water_boost_until, 10000 if mode == 'infinite' else 6000)
                    self.assertGreater(game._player_speed(p, 500), game._player_speed(p, 10000))
                    p.last_shot_time = 0
                    self.assertTrue(p.can_shoot(350))
                    p.last_shot_time = 10000
                    self.assertFalse(p.can_shoot(10350))
                game._expire_water_temp_hp(p2.temp_hp_until)
                self.assertEqual(p2.hp, p2.max_hp)

    def test_water_skills_do_not_revive_or_buff_fallen_teammates(self):
        self.p1.owned_characters.append('water')
        self.g.action(1, 'character', 'water')
        self.p2.alive, self.p2.hp = False, 0
        self.g.action(1, 'skill1')
        self.g.action(1, 'skill2')
        self.assertEqual(self.p2.hp, 0)
        self.assertEqual(self.p2.water_boost_until, 0)
        self.assertEqual([p for p, _ in self.g.water_heal_effects], [self.p1])

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
                snapshot = self.g.snapshot()
                self.assertEqual(snapshot['transition_reward'], config.CAMPAIGN_REWARDS[level - 1])
                self.assertEqual(snapshot['next_level_title'], config.LEVEL_CONFIGS[level]['title'])
                for _ in range(120):
                    self.g.step()
            else:
                for _ in range(25):
                    self.g.step()
                self.assertFalse(self.g.particles)
                self.assertEqual(self.g.phase, 'won')
                self.assertEqual(self.g.current_level, 12)
        self.assertRaises(ValueError, self.g._start_level, 13)

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
