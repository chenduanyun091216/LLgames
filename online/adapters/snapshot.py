"""Explicit JSON visual schema. Resource objects and executable data never leave the server."""
import math
import weakref
import pygame
from game_core import config, entities as E
from game_core.boss_skills import BossSignature
from game_core import abyss_bosses as A
from game_core import special_bosses as S, orochi as O

# Reviewed static allowlist, not runtime introspection or object-dictionary export.
SCHEMA = {
    'Player': 'animation_move_at animation_moving animation_skill animation_skill_at breath_start_time campaign character current_weapon gift_speed_until gold last_shot_time niu_freeze_until niu_slow_until owned_characters owned_weapons rage_until skill_active_cd skill_active_until skill_cooldowns skill_display_duration snow_slow_until sprite_asset water_boost_until water_haste_until weapon_ammo x y slot hp max_hp alive invincible_until shop_open'.split(),
    'Enemy': 'hits attack_interval attack_interval_max attack_interval_min base_h base_w breath_start_time burn_damage burn_duration burn_hits burn_start burning chase_color chase_partner chase_side damage_taken frozen frozen_until gold_value h health_mult immune_text_until infected infected_weapon is_large is_zongzong last_attack_time last_burn_tick last_contact_damage_time max_hp size_scale slow_mult slowed_until snowflake_until speed sprite_asset unscaled_base_h unscaled_base_w w water_mark_until x y zong_expression zong_expression_at zong_expression_from zong_hits'.split(),
    'Bullet': 'angle character color damage gift_kind max_lifetime radius spawn_time speed weapon_name x y'.split(),
    'Coin': 'radius speed value x y'.split(),
    'GiftBox': 'breath_start_time kind radius speed x y'.split(),
    'Particle': 'particles'.split(),
    'Explosion': 'age color element heavy life sparks x y'.split(),
    'FireWall': 'h last_damage_time lifetime spawn_time speed w x y'.split(),
    'IceFloor': 'alive freeze_radius gaps h hits_left speed w x y'.split(),
    'SkillProjectile': 'alive angle damage lifetime owner piercing ptype r skill_type spawn_time speed x y'.split(),
    'Lightning': 'damage gift lifetime spawn_time start_x start_y targets'.split(),
    'MagneticStorm': 'explode_time exploded last_damage_time lifetime pull_duration pull_speed radius spawn_time x y'.split(),
    'RadiationLaser': 'duration last_whip_time owner spawn_time swing_power swing_speed'.split(),
    'SpinningDarts': '_fly_discs duration owner release_time released skill_type spawn_time'.split(),
    'BossProjectile': 'alive angle big_fireball bomb damage explode_radius homing homing_duration max_lifetime prev_x prev_y r spawn_time speed tint x y lightning_previous'.split(),
    'DragonFireball': 'alive angle big_fireball blast_reason bomb damage explode_radius homing homing_duration lightning_previous max_lifetime prev_x prev_y r spawn_time speed tint x y'.split(),
    'Boss': 'animation_attack_at last_pattern attack_phase fusion_mode fusion_started_at axe_slam_start axe_slam_duration absorb_count absorb_target attack_interval base_h base_w breath_start_time entered fight_start_time h homing_chance hp laser_active_until laser_chance laser_warning_ms laser_warning_start last_attack_time last_laser_hit_until max_hp movement_timer name next_absorb_time next_death_laser_time next_signature_time projectile_count signature signature_opening_pending size_scale slow_mult slowed_until speed sprite_asset w x y intro_until'.split(),
    'BossSignature': 'bottom bubble_crabs bubble_released bubble_spacing bubble_x campaign chasing color damage end_at impact_at key last_hit launch_y left name next_fireball_at origin right second_target_x target_x target_y trident_lanes'.split(),
}
# Explicit inherited field groups keep the wire vocabulary reviewable. Surfaces,
# fonts, cached animation frames and simulation-only sets are never transmitted.
SCHEMA['NiuBoss'] = SCHEMA['Boss'] + 'opening_skill_pending lightning_xs lightning_warning_until lightning_until shield_until shield_damage shield_break_at running_left'.split()
SCHEMA['ZongBoss'] = SCHEMA['Boss'] + 'body_hp easy_campaign next_fusion_time fusion_until fusion_end_volley snow_until opening_snow_done expression_hit_at pending_projectiles crescent_projectiles crescent_started_at crescent_count crescent_target crescent_origin next_revive_check campaign_revived fusion_warning_mode'.split()
SCHEMA['OrochiBoss'] = SCHEMA['Boss'] + 'skill skill_at next_skill opening_pending spawned_at emitted shots impacts head_hp final_storm invincible_until death_at death_particles hit_flashes split_hp split_xy split_dive split_next_dive split_charged split_charge_until split_velocity split_last_update split_regroup_at split_target'.split()
SCHEMA['ReturningAxe'] = SCHEMA['BossProjectile'] + 'boss origin side red target_x impact_x impact_pending blast_reason'.split()
SCHEMA['CrescentWave'] = SCHEMA['BossProjectile'] + ['unblockable']
SCHEMA['ZongBomb'] = SCHEMA['BossProjectile'] + 'color proximity_detonated'.split()
SCHEMA['ZongFireball'] = list(SCHEMA['BossProjectile'])
SCHEMA['ZongReflectBullet'] = list(SCHEMA['BossProjectile'])
SCHEMA['NiuFanBullet'] = SCHEMA['BossProjectile'] + ['red']
SCHEMA['OrochiFireball'] = SCHEMA['BossProjectile'] + ['color']
SCHEMA['MechaLizardBoss'] = SCHEMA['Boss'] + 'skill_index current_skill skill_started_at self_telegraphed'.split()
SCHEMA['AncientWhaleBoss'] = SCHEMA['MechaLizardBoss'] + ['moon_cast_at', 'swim_direction', 'swim_turn_at']
SCHEMA['AbyssProjectile'] = SCHEMA['BossProjectile'] + list(A.ABYSS_PROJECTILE_FIELDS)
SCHEMA['Enemy'] += ['factory_kind', 'factory_link_until', 'temple_kind']
CLASSES = {name: getattr(E, name) for name in (
    'Player Enemy Bullet Coin GiftBox Particle Explosion FireWall IceFloor SkillProjectile '
    'Lightning MagneticStorm RadiationLaser SpinningDarts BossProjectile DragonFireball Boss').split()}
CLASSES.update({name: getattr(S, name) for name in (
    'NiuBoss ZongBoss ReturningAxe CrescentWave ZongBomb ZongFireball ZongReflectBullet NiuFanBullet').split()})
CLASSES.update({name: getattr(A, name) for name in ('MechaLizardBoss', 'AncientWhaleBoss', 'AbyssProjectile')})
CLASSES.update(BossSignature=BossSignature, OrochiBoss=O.OrochiBoss, OrochiFireball=O.OrochiFireball)
COLLECTIONS = 'enemies bullets coins gift_boxes particles explosions fire_walls ice_floors skill_projectiles magnetic_storms radiation_lasers lightnings dart_shields boss_projectiles warned_boss_shots enemy_projectiles'.split()
GAME_FIELDS = 'bg_transition_until current_level chapter infinite_mode infinite_background_level player_invincible_until level_title_until rage_banner_until gift_lightning_icon_until gift_lightning_remaining gift_fire_until gift_ice_until player_hp max_player_hp score kill_count level_kills leak_count lives warned_boss_shots_at laser_impacts water_heal_effects muzzle_flashes skill_flash gift_messages'.split()
DATA_KEYS = set('x y vx vy life max_life color size start text until at kind key name is_large zongzong gold base_speed health_mult sprite_asset sprite_key enemy_key base_hp fixed_hp speed attack_interval projectile_count homing_chance laser_chance campaign_tier campaign_level warning duration h w radius released burst_at target_x target_y'.split()) | set(config.WEAPON_DEFS) | set(config.CHARACTER_DEFS) | set('fisher_grenade ice_balls water_heal lightning skill1 skill2 radiation_laser dart_shield fireball fire_wall ice_ball ice_floor magnetic_storm lightning_chain water_boost water_haste'.split())
DEFINITION_KEYS = 'campaign_hp key name is_large zongzong gold base_speed health_mult sprite_asset sprite_key enemy_key base_hp fixed_hp speed attack_interval projectile_count homing_chance laser_chance campaign_tier campaign_level size damage_cap final_boss easy_campaign laser_offsets shield_thresholds laser_interval_mult'.split()

DATA_KEYS.update(DEFINITION_KEYS)

def encode_world(game):
    """Capture a full frame with monotonic world IDs, never memory addresses."""
    if not hasattr(game, '_visual_ids'):
        game._visual_ids = weakref.WeakKeyDictionary()
        game._visual_next_id = 1
    # Server-only subclass retains the exact original axe renderer. Import here
    # so the browser presentation never loads the authoritative game adapter.
    from .core_adapter import SharedReturningAxe
    records, seen = [], set()
    def entity(obj):
        name = ('ReturningAxe' if type(obj) is SharedReturningAxe else
                'Player' if isinstance(obj, E.Player) else type(obj).__name__)
        if name not in CLASSES or (name != 'Player' and type(obj) is not CLASSES[name] and type(obj) is not SharedReturningAxe):
            raise ValueError('Unsupported visual entity: ' + name)
        if obj not in game._visual_ids:
            game._visual_ids[obj] = game._visual_next_id
            game._visual_next_id += 1
        ident = game._visual_ids[obj]
        if ident not in seen:
            seen.add(ident)
            record = {'id': ident, 'type': name, 'fields': {}}
            records.append(record)
            record['fields'] = {k: value(getattr(obj, k)) for k in SCHEMA[name] if hasattr(obj, k)}
            for attr in ('edef', 'bdef'):
                if hasattr(obj, attr):
                    record[attr] = {k: value(v) for k,v in getattr(obj, attr).items() if k in DEFINITION_KEYS}
        return ident
    def value(v):
        if v is None or type(v) in (bool, str, int): return v
        if type(v) is float:
            if not math.isfinite(v): raise ValueError('Nonfinite visual value')
            return v
        if isinstance(v, E.Player) or type(v) is SharedReturningAxe or type(v).__name__ in CLASSES: return {'ref': entity(v)}
        if isinstance(v, pygame.Color): return list(v)
        if isinstance(v, (list, tuple)): return [value(item) for item in v]
        if isinstance(v, dict): return {k:value(item) for k,item in v.items() if k in DATA_KEYS}
        raise TypeError('Non-JSON visual value: ' + type(v).__name__)
    players = []
    for slot, player in enumerate(getattr(game, 'all_players', game.players), 1):
        players.append({'slot': slot, 'id': entity(player), 'alive': getattr(player, 'alive', True),
                        **{k:value(getattr(player,k)) for k in SCHEMA['Player'] if hasattr(player,k)}})
    fields = {k:value(getattr(game,k)) for k in GAME_FIELDS if hasattr(game,k)}
    return {'version':1, 'time_ms':config.game_ticks(), 'game':fields, 'players':players,
            'boss':entity(game.boss) if game.boss else None,
            'collections':{k:[entity(o) for o in getattr(game,k,())] for k in COLLECTIONS}, 'objects':records}
