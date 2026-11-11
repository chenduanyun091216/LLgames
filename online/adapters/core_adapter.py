"""Eleven-level two-player campaign adaptation of the original authoritative Game loop.

The battle loop, enemy spawning, shots, character skills and all boss AI remain
in game_core.Game. Overrides here are confined to multiplayer seams. This class
is deliberately single-room: game_core uses process-global geometry and time.
"""
from contextlib import contextmanager
from collections import deque
import math
import os

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

import pygame
from game_core import config
from game_core import game as core_game
from game_core import orochi as core_orochi
from game_core import special_bosses as core_special_bosses
from game_core.game import Game, GameState, CONTACT_DAMAGE_COOLDOWN
from game_core.entities import Player
from game_core.boss_skills import BossSignature
from game_core.sprites import make_player_surface
from online.shared.world import configure_world

REVIVE_COSTS = {'easy': 50, 'medium': 75, 'hard': 100}


def fixed_world(orientation='landscape'):
    """Only the room's fixed orientation can select logical geometry."""
    return configure_world(orientation)


class SharedPlayer(Player):
    def __init__(self, wallet):
        self._wallet = wallet
        super().__init__()

    @property
    def gold(self):
        return self._wallet['gold']

    @gold.setter
    def gold(self, value):
        self._wallet['gold'] = value


class SharedReturningAxe(core_game.ReturningAxe):
    """Original persistent axe, with its direct-hit cooldown split by victim."""
    @property
    def last_player_hit(self):
        target = self._online_game._damage_target
        return self._player_hits.get(target.slot, -9999) if target else -9999

    @last_player_hit.setter
    def last_player_hit(self, now):
        target = self._online_game._damage_target
        if target:
            self._player_hits[target.slot] = now


class OnlineGame(Game):
    def __init__(self, difficulty='medium', orientation='landscape'):
        if difficulty not in REVIVE_COSTS:
            raise ValueError('Unsupported difficulty')
        pygame.font.init()
        if not pygame.display.get_init():
            pygame.display.init()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1, 1))
        self.orientation = orientation
        self.world_size = fixed_world(orientation)
        config.SCR = pygame.Surface(self.world_size)
        config.campaign_time_ms = 0
        self.tick = 0
        self.phase = 'playing'
        self.difficulty_key = difficulty
        self._all_players = ()
        self._focus = None
        self._damage_target = None
        self._contact_hits = {}
        self._signature_hits = {}
        self._signature_object = None
        self._area_hits = {}
        self._suppress_damage = False
        self._events = deque(maxlen=48)
        self._event_id = 0
        with self._capture_sounds():
            super().__init__(desktop_controls=False, scroll_campaign_backgrounds=True)
        wallet = {'gold': 0}
        self.player = SharedPlayer(wallet)
        second = SharedPlayer(wallet)
        self._all_players = (self.player, second)
        with self._capture_sounds():
            self._start_game(difficulty)
        self.lives = 5
        self.mobile_controls.auto_fire = False
        self._inputs = {1: (0., 0., False), 2: (0., 0., False)}
        weapons, characters = self.player.owned_weapons, self.player.owned_characters
        hp = (6, 5, 4)[self._campaign_tier()]
        for slot, player in enumerate(self._all_players, 1):
            player.slot = slot
            player.hp = player.max_hp = hp
            player.alive = True
            player.invincible_until = 0
            player.temp_hp_until = 0
            player.shop_open = False
            player.last_switch_at = -9999
            player.campaign = True
            player.hazard_slow = (0.85, 0.80, 0.75)[self._campaign_tier()]
            player.owned_weapons, player.owned_characters = weapons, characters
            player.x, player.y = self.world_size[0] / 2 + (slot - 1.5) * 180, config.GAME_AREA_BOTTOM - 14
        self._legacy_sync()

    @contextmanager
    def _capture_sounds(self):
        # Online runs a single synchronous world in its own process. Capture the
        # original core's sound calls as events, restore the binding before any
        # await, and let each browser play each event once. No core file changes.
        original = core_game.play_sound, core_orochi.play_sound, core_special_bosses.play_sound
        def capture(key):
            self._event_id += 1
            self._events.append({'id': self._event_id, 'type': 'sound', 'key': key})
        core_game.play_sound = core_orochi.play_sound = core_special_bosses.play_sound = capture
        try:
            yield
        finally:
            core_game.play_sound, core_orochi.play_sound, core_special_bosses.play_sound = original

    @property
    def all_players(self):
        return self._all_players

    @property
    def players(self):
        if not self._all_players:
            return (self.player,)
        return tuple(p for p in self._all_players if getattr(p, 'alive', True))

    @property
    def gold(self):
        return self.player.gold

    @property
    def paused(self):
        return any(p.shop_open for p in self.all_players) or not self.players

    @property
    def pause_reason(self):
        if any(p.shop_open for p in self.all_players):
            return 'shop'
        return 'revive' if not self.players and self.phase == 'playing' else ''

    def _legacy_sync(self):
        p = self._focus or self.player
        self.player_hp, self.max_player_hp = p.hp, p.max_hp
        self.player_invincible_until = p.invincible_until
        self.water_temp_hp_until = p.temp_hp_until

    @contextmanager
    def _for_player(self, player, *, focus=True):
        previous, previous_focus = self.player, self._focus
        self.player, self._focus = player, player if focus else previous_focus
        self._legacy_sync()
        try:
            yield
        finally:
            player.invincible_until = max(player.invincible_until, self.player_invincible_until)
            self.player, self._focus = previous, previous_focus
            self._legacy_sync()

    def set_input(self, slot, dx, dy, shoot):
        if slot not in (1, 2) or not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in (dx, dy)):
            return
        dx, dy = max(-1, min(1, dx)), max(-1, min(1, dy))
        length = max(1, math.hypot(dx, dy))
        self._inputs[slot] = (dx / length, dy / length, shoot is True)

    def clear_inputs(self):
        for slot in self._inputs:
            self._inputs[slot] = (0., 0., False)

    def step(self):
        finishing = self.phase == 'won' and round(self.tick * 1000 / 60) < self.victory_end
        if not finishing and (self.phase != 'playing' or self.paused):
            self.clear_inputs()
            return
        fixed_world(self.orientation)
        self.tick += 1
        config.campaign_time_ms = round(self.tick * 1000 / 60)
        now = config.game_ticks()
        if finishing:
            self._update_combat_effects()
            self._expire_visuals(now)
            return
        accepting_input = self.state != GameState.LEVEL_TRANSITION and not self._whale_is_swallowing()
        for p in self.players if accepting_input else ():
            dx, dy, shooting = self._inputs[p.slot]
            if now >= max(p.niu_freeze_until, p.geyser_lift_until):
                speed = self._player_speed(p, now)
                p.move(dx * speed, dy * speed)
            if shooting and p.can_shoot(now, self._player_fire_interval_multiplier(now)):
                with self._capture_sounds():
                    self._shoot(now, p)
        self._damage_target = None
        with self._capture_sounds():
            with self._for_player(self.players[0], focus=False):
                super().update()  # Exactly one world update per tick.
            for player in self.all_players:
                if not player.alive and self.lives > 0:
                    self._action(player.slot, 'revive')
        self._expire_visuals(now)
        self._legacy_sync()

    def _expire_visuals(self, now):
        # In single-player these short-lived records are removed while drawing.
        # The headless host must apply the same TTLs without rendering a frame.
        self.muzzle_flashes[:] = [v for v in self.muzzle_flashes if now - v[1] < 90]
        self.water_heal_effects[:] = [v for v in self.water_heal_effects if now - v[1] < 800]
        self.laser_impacts[:] = [v for v in self.laser_impacts if now - v[2] <= 300]
        self.gift_messages[:] = [v for v in self.gift_messages if now < v[2]]
        if self.skill_flash and now - self.skill_flash[2] >= 340:
            self.skill_flash = None

    # Original Game polls local input. Online input is injected only in step().
    def _move_player_from_controls(self, player, keys, now):
        pass

    def _mobile_fire_active(self):
        return False

    def _key_pressed(self, keys, action):
        return False

    def _start_level(self, n, *, checkpoint=True):
        if not 1 <= n <= len(core_game.LEVEL_CONFIGS):
            raise ValueError('Only the configured ordinary campaign levels are supported')
        self._area_hits.clear()
        self._contact_hits.clear()
        # Single-player retry checkpoints are not used by confirmed co-op revival.
        return super()._start_level(n, checkpoint=False)

    def _level_complete(self):
        if self.phase != 'playing' or self.state == GameState.LEVEL_TRANSITION:
            return
        super()._level_complete()
        self.clear_inputs()
        if self.state == GameState.VICTORY:
            self.phase = 'won'

    def _hit_player(self, rect):
        hits = [p for p in self.players if rect.colliderect(p.rect())]
        # An invincible teammate must not shield a vulnerable overlapping player.
        p = next((p for p in hits if config.game_ticks() >= p.invincible_until), hits[0] if hits else None)
        self._damage_target = p
        return p

    def _hit_by_projectile(self, projectile):
        # Geometry and telegraph timing belong to the shared projectile; this
        # seam only chooses a living multiplayer victim and records that target.
        hits_rect = getattr(projectile, 'hits_rect', None)
        if hits_rect is None:
            return self._hit_player(projectile.rect())
        hit_players = getattr(projectile, '_hit_players', ())
        hits = [p for p in self.players if p not in hit_players and hits_rect(p.rect())]
        p = next((p for p in hits if config.game_ticks() >= p.invincible_until), hits[0] if hits else None)
        self._damage_target = p
        return p

    def _player_is_invincible(self, now):
        if self._suppress_damage:
            return True
        p = self._damage_target or self._focus or self.player
        return not p.alive or now < p.invincible_until

    def _damage_player(self, now, amount, reason, *, hit_feedback=False):
        # The shared loop can request local-only sound and screen feedback.
        if self._suppress_damage:
            return False
        p = self._damage_target or self._focus or self.player
        if not p.alive or now < p.invincible_until:
            return False
        p.hp = max(0, p.hp - amount)
        if amount > 0:
            p.animation_hit_at = now
        p.invincible_until = now + (850, 650, 550)[self._campaign_tier()]
        if p.hp <= 0:
            p.alive = False
            self._inputs[p.slot] = (0., 0., False)
            self.game_over_reason = reason
            if not self.players:
                if self.lives <= 0 and not self._can_buy_revive():
                    self.phase = 'lost'
                    self.state = GameState.GAME_OVER
                return True
        self._legacy_sync()
        return False

    def _defeat_players_by_suction(self, now):
        for player in tuple(self.players):
            with self._for_player(player):
                player.invincible_until = min(player.invincible_until, now)
                self._damage_player(now, player.hp, '被远古巨鲸吸入！')

    def _resolve_leak(self, enemy, now):
        self.enemies.remove(enemy)
        self.leak_count += 1
        # Every leak costs each living teammate exactly one HP on every difficulty.
        # Beach damage is not dodged by a recent projectile/revival shield.
        for player in tuple(self.players):
            self._damage_target = player
            shield_until = player.invincible_until
            player.invincible_until = min(player.invincible_until, now)
            self._damage_player(now, 1, f'{enemy.edef["name"]} 入侵成功！')
            player.invincible_until = max(shield_until, player.invincible_until)
        self._damage_target = None
        return not self.players

    def _damage_player_on_contacts(self, now):
        active = set(self.enemies)
        if self.boss:
            active.add(self.boss)
        self._contact_hits = {pair: time for pair, time in self._contact_hits.items() if pair[0] in active}
        boss_contact = (self.boss and not (self.boss.signature and self.boss.signature.origin is not None)
                        and not (isinstance(self.boss, core_game.OrochiBoss)
                                 and self.boss.skill in ('split', 'storm', 'laser')))
        for entity in tuple(self.enemies) + ((self.boss,) if boss_contact else ()):
            if entity is not self.boss and entity.temple_kind == 'rift':
                continue
            for p in self.players:
                key = (entity, p.slot)
                last_contact = self._contact_hits.get(key, getattr(entity, 'last_contact_damage_time', -9999))
                if now < p.invincible_until or (entity is not self.boss and now - last_contact < CONTACT_DAMAGE_COOLDOWN):
                    continue
                hitboxes = entity.hitboxes() if entity is self.boss else (entity.rect(),)
                contact = next((r for r in hitboxes if r.colliderect(p.rect())), None)
                if contact is None:
                    continue
                self._contact_hits[key] = now
                self._damage_target = p
                if not self._player_is_invincible(now):
                    self._play_contact_impact(p, contact, heavy=entity is self.boss or entity.is_large)
                if entity is self.boss:
                    p.move(0, contact.bottom - p.rect().top + 2)
                amount = 2 if entity is self.boss else self._enemy_contact_damage(entity)
                self._damage_player(now, amount, '被敌人撞击击败！')
        self._damage_target = None
        # This core hook runs immediately before the legacy singleton laser block.
        # Resolve the same geometry per player, then mark that block consumed.
        boss = self.boss
        if boss:
            for p in tuple(self.players):
                hit = any(r.colliderect(p.rect()) for r in boss.death_laser_rects(now))
                if hit:
                    self._area_damage(p, ('laser', boss.laser_active_until), now, 1,
                                      f'被{boss.name}毁灭激光击败！')
            boss.last_laser_hit_until = boss.laser_active_until
        return not self.players

    def _area_damage(self, player, token, now, amount, reason):
        # Keep only the latest strike per hazard/player, bounded over long fights.
        key = (token[0], player.slot)
        if now < player.invincible_until or self._area_hits.get(key) == token:
            return
        self._area_hits[key] = token
        self._damage_target = player
        self._damage_player(now, amount, reason)
        self._damage_target = None

    @contextmanager
    def _world_effects_only(self):
        previous = self._suppress_damage
        self._suppress_damage = True
        try:
            yield
        finally:
            self._suppress_damage = previous
            self._damage_target = None

    def _try_boss_signature(self, now, *, opening=False):
        if not self.boss or not self.players:
            return False
        target = self._nearest_player(self.boss.x, self.boss.y)
        with self._for_player(target):
            created = super()._try_boss_signature(now, opening=opening)
        if created:
            self._signature_hits.clear()
            self._signature_object = self.boss.signature
        return created

    def _update_boss_signature(self, now):
        if not self.boss.signature or not self.players:
            return not self.players
        target = self._nearest_player(self.boss.x, self.boss.y)
        # Original movement, bubbles, dragon projectiles and end/reset happen once.
        with self._for_player(target), self._world_effects_only():
            super()._update_boss_signature(now)
        signature = self.boss.signature
        if signature is None or now < signature.impact_at:
            return False
        for p in tuple(self.players):
            if now < p.invincible_until:
                continue
            last_hit, tridents = self._signature_hits.get(p.slot, (-1, set()))
            signature.last_hit, signature.trident_hits = last_hit, tridents
            hit = signature.hit(self.boss, p.rect(), now)
            self._signature_hits[p.slot] = (signature.last_hit, signature.trident_hits)
            if hit:
                self._damage_target = p
                damage = p.hp if signature.key == 'boss' else min(signature.damage, self.boss.bdef.get('damage_cap', 2))
                core_game.play_sound('hit')
                self._damage_player(now, damage, f'被{signature.name}击败！')
        self._damage_target = None
        return not self.players

    def _add_boss_projectiles(self, projectiles):
        adapted = []
        for projectile in projectiles:
            if type(projectile) is core_game.ReturningAxe:
                axe = SharedReturningAxe.__new__(SharedReturningAxe)
                axe.__dict__.update(projectile.__dict__)
                axe._online_game = self
                axe._player_hits = {}
                projectile = axe
            adapted.append(projectile)
        return super()._add_boss_projectiles(adapted)

    def _explode_enemy_bomb(self, projectile, now):
        # Preserve original explosion effects once; fan its damage/frost out by body.
        with self._world_effects_only():
            super()._explode_enemy_bomb(projectile, now)
        radius = getattr(projectile, 'explode_radius', 72)
        for player in tuple(self.players):
            rect = player.rect()
            x = max(rect.left, min(projectile.x, rect.right))
            y = max(rect.top, min(projectile.y, rect.bottom))
            if math.hypot(projectile.x - x, projectile.y - y) > radius or now < player.invincible_until:
                continue
            self._damage_target = player
            self._apply_niu_ice_axe_effect(projectile, player, now)
            core_game.play_sound('hit')
            self._damage_player(now, getattr(projectile, 'damage', 1),
                                getattr(projectile, 'blast_reason', '被小粽粽炸弹击败！'))
        self._damage_target = None
        return not self.players

    def _update_special_boss_hazards(self, now):
        boss = self.boss
        lightning_due = (isinstance(boss, core_game.NiuBoss)
                         and now >= boss.lightning_warning_until and now >= boss.lightning_next_tick
                         and bool(boss.lightning_rects(now)))
        # Preserve Orochi shot/impact effects and the Niu lightning world clock once.
        with self._world_effects_only():
            super()._update_special_boss_hazards(now)
        for player in tuple(self.players):
            if isinstance(boss, core_game.OrochiBoss) and boss.skill in ('slam', 'split', 'laser', 'storm'):
                age = boss.age(now)
                strike = boss.hazard_strike(age)
                if boss.hazard_hits(player.rect(), age):
                    self._area_damage(player, ('orochi', now - age, boss.skill, strike), now, 2,
                                      f'被{boss.name}击败！')
            elif isinstance(boss, core_game.NiuBoss):
                slam = boss.axe_slam_rect(now)
                if slam is not None and slam.colliderect(player.rect()):
                    strike = (now - boss.axe_slam_start) // boss.AXE_SLAM_CYCLE_MS
                    self._area_damage(player, ('axe', boss.axe_slam_start, strike), now, 1,
                                      '被牛魔王的巨斧击败！')
                if lightning_due and any(r.colliderect(player.rect()) for r in boss.lightning_rects(now)):
                    self._area_damage(player, ('lightning', boss.lightning_next_tick), now,
                                      min(2, boss.bdef.get('damage_cap', 2)), '被牛魔王的雷电击败！')
        return not self.players

    def _hazard_warning_ms(self, zones, now, minimum=None):
        # A warning must give every living teammate the original escape allowance.
        warnings = []
        for player in self.players:
            with self._for_player(player):
                warnings.append(super()._hazard_warning_ms(zones, now, minimum))
        return None if not warnings or None in warnings else max(warnings)

    def _kill_boss(self):
        self._boss_reward_heal = True
        try:
            return super()._kill_boss()
        finally:
            self._boss_reward_heal = False

    def _heal_player(self, amount, increase_max=False, temporary_ms=0):
        # A water skill heals its owner; passive/gift heals prefer the living water
        # character, otherwise the most wounded living teammate. Never resurrect.
        if not self._all_players or not hasattr(self.player, 'hp'):
            return super()._heal_player(amount, increase_max, temporary_ms)
        candidates = self.players
        if getattr(self, '_boss_reward_heal', False):
            for player in candidates:
                player.hp = min(player.max_hp, player.hp + amount)
            self._legacy_sync()
            return
        if not candidates:
            return
        p = self._focus or next((p for p in candidates if p.character == 'water'), min(candidates, key=lambda p: p.hp / p.max_hp))
        if not p.alive:
            return
        if increase_max:
            p.max_hp = min(5, p.max_hp + amount)
        p.hp = min(p.max_hp + (amount if temporary_ms else 0), p.hp + amount)
        if temporary_ms:
            p.temp_hp_until = max(p.temp_hp_until, config.game_ticks() + temporary_ms)
        self._legacy_sync()

    def _expire_water_temp_hp(self, now):
        for p in self.all_players:
            if p.temp_hp_until and now >= p.temp_hp_until:
                p.hp = min(p.hp, p.max_hp)
                p.temp_hp_until = 0
        self._legacy_sync()

    def _equipped_by_other(self, player, attr, key):
        if (attr == 'current_weapon' and key == 'pistol') or (attr == 'character' and key is None):
            return False
        return any(other is not player and getattr(other, attr) == key for other in self.all_players)

    def try_switch_weapon(self, key, player=None):
        p = player or self.player
        now = config.game_ticks()
        if now - getattr(p, 'last_switch_at', -9999) < config.WEAPON_SWITCH_COOLDOWN:
            return False
        if key in p.owned_weapons and not self._equipped_by_other(p, 'current_weapon', key):
            p.current_weapon, p.last_switch_at = key, now
            return True
        return False

    def try_switch_character(self, key, player=None):
        p = player or self.player
        if key is None:
            if any(l.owner is p and not l.is_expired(config.game_ticks()) for l in self.radiation_lasers):
                return False
            p.character, p.surface = None, make_player_surface()
            return True
        return super().try_switch_character(key, p)

    def action(self, slot, action, key=None):
        with self._capture_sounds():
            return self._action(slot, action, key)

    def _action(self, slot, action, key=None):
        if slot not in (1, 2):
            return '无效玩家'
        if self.phase != 'playing':
            return '对局已经结束'
        if self._whale_is_swallowing():
            return '等待巨鲸吞入动画结束'
        p = self.all_players[slot - 1]
        if action == 'shop_open':
            for other in self.all_players:
                other.shop_open = True
            self.clear_inputs()
            return None
        if action == 'shop_close':
            p.shop_open = False
            self.clear_inputs()
            return None
        if action == 'revive':
            if p.alive:
                return '当前玩家无需复活'
            if self.lives > 0:
                self.lives -= 1
            elif self._can_buy_revive():
                self.player.gold -= REVIVE_COSTS[self.difficulty_key]
                self.revive_count += 1
            elif not self._paid_revives_remaining():
                return '共享金币复活次数已用完'
            else:
                return '复活资源不足，请等待队友收集金币'
            p.alive, p.hp = True, p.max_hp
            self._place_revived_player(p)
            p.invincible_until = config.game_ticks() + core_game.REVIVE_INVINCIBILITY_MS
            p.temp_hp_until = 0
            self._inputs[slot] = (0., 0., False)
            return None
        if not p.alive:
            return '阵亡玩家需要确认复活'
        if action in ('weapon', 'character'):
            if action == 'weapon':
                definitions, owned = config.WEAPON_DEFS, p.owned_weapons
                if key not in definitions:
                    return '无效武器'
                price, attr = self._weapon_cost(key), 'current_weapon'
                switch = self.try_switch_weapon
            else:
                if key in ('fisher', 'fisherman', None):
                    return None if self.try_switch_character(None, p) else '技能持续中，暂不能切换'
                definitions, owned = config.CHARACTER_DEFS, p.owned_characters
                if key not in definitions:
                    return '无效角色'
                price, attr = self._character_cost(definitions[key]), 'character'
                switch = self.try_switch_character
            if self._equipped_by_other(p, attr, key):
                return '队友正在使用，不能重复装备'
            if key not in owned:
                if not p.shop_open:
                    return '请先打开商店购买'
                if self.gold < price:
                    return '共享金币不足'
                # Validate active laser before deducting or granting ownership.
                if action == 'character' and any(l.owner is p and not l.is_expired(config.game_ticks()) for l in self.radiation_lasers):
                    return '技能持续中，暂不能切换'
                self.player.gold -= price
                owned.append(key)
                # Purchase is atomic; equip is not delayed by prior weapon key.
                p.last_switch_at = -9999
            return None if switch(key, p) else '切换冷却中或技能仍在持续'
        if self.state == GameState.LEVEL_TRANSITION:
            return '等待进入下一关'
        if self.paused:
            return '等待双方关闭商店后继续'
        if action in ('skill1', 'skill2', 'laser', 'dart'):
            with self._for_player(p):
                if action == 'laser':
                    self._activate_radiation_laser(p)
                elif action == 'dart':
                    self._activate_dart_shield(p)
                else:
                    self._handle_skill_key(p, pygame.K_k if action == 'skill1' else pygame.K_l, pygame.K_k, pygame.K_l)
            return None
        return '未知操作'

    def snapshot(self):
        from .snapshot import encode_world
        players = []
        for p in self.all_players:
            players.append({'slot': p.slot, 'alive': p.alive, 'hp': p.hp, 'max_hp': p.max_hp,
                            'shop_open': p.shop_open, 'weapon': p.current_weapon,
                            'character': p.character or 'fisher', 'x': p.x, 'y': p.y,
                            'cooldowns': dict(p.skill_cooldowns),
                            'active_until': dict(p.skill_active_until)})
        weapons = [{'key': k, 'name': d.name, 'price': self._weapon_cost(k), 'owned': k in self.player.owned_weapons} for k, d in config.WEAPON_DEFS.items()]
        characters = [{'key': 'fisher', 'name': '渔夫', 'price': 0, 'owned': True}]
        characters += [{'key': k, 'name': d.name, 'price': self._character_cost(d), 'owned': k in self.player.owned_characters} for k, d in config.CHARACTER_DEFS.items()]
        stage = {GameState.LEVEL_TRANSITION: 'transition', GameState.BOSS_FIGHT: 'boss'}.get(self.state, self.phase)
        return {'tick': self.tick, 'phase': self.phase, 'paused': self.paused,
                'orientation': self.orientation, 'world_size': list(self.world_size),
                'current_level': self.current_level, 'total_levels': len(core_game.LEVEL_CONFIGS), 'stage': stage,
                'level_title': core_game.LEVEL_CONFIGS[self.current_level - 1]['title'],
                'transition_remaining_ms': max(0, self.level_transition_end - config.game_ticks()) if stage == 'transition' else 0,
                'pause_reason': self.pause_reason, 'players': players, 'gold': self.gold,
                'lives': self.lives, 'difficulty': self.difficulty_key,
                'revive_cost': REVIVE_COSTS[self.difficulty_key], 'kills': self.level_kills,
                'paid_revives_remaining': self._paid_revives_remaining(),
                'boss_remaining_ms': (max(0, core_game.BACKGROUND_SCROLL_TICKS - self.background_scroll_ticks)
                                      * 1000 // config.FPS if self.state == GameState.PLAYING else 0),
                'catalog': {'weapons': weapons, 'characters': characters},
                'events': list(self._events), 'world': encode_world(self)}
