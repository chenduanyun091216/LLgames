"""Small sprite-sheet helper for character and boss animations."""
from functools import lru_cache

import pygame

from .asset_loader import image_asset
from .boss_skills import BITE_REPEAT_MS, CHASE_MS, CLAW_DELAY_MS, LASH_MS, TRIDENT_INTERVAL_MS

_FRAMES = {}
DOWNWARD_LASER_POSES = {
    'boss_crab': (0, .50, .57),
    'boss_octopus': (1, .50, .64),
    'boss_shark': (1, .70, .74),
    'boss_dragon': (1, .62, .32),
    'boss': (1, .68, .77),
}

# Left and right edge travel as a fraction of sprite height. Keep the
# central body still and let the claws, tentacles or fins carry the motion.
IDLE_BODY_TRAVEL = {
    'boss_lobster': (-.075, .075),
    'boss_crab': (-.065, .065),
    'boss_octopus': (-.085, .080),
    'boss_shark': (-.11, .025),
    'boss_dragon': (-.075, -.065),
    'boss': (-.095, .035),
}
_IDLE_SWING = (0, .55, 1, .45, -.45, -1)
_ATTACK_POSES = ((2, 1), (2, .65), (2, .25), (3, .60),
                 (3, .35), (3, -.20), (0, -.15), (0, 0))


@lru_cache(maxsize=128)
def _body_pose(sprite, name, swing):
    if not swing:
        return sprite
    width, height = sprite.get_size()
    left, right = IDLE_BODY_TRAVEL[name]
    result = pygame.Surface((width, height), pygame.SRCALPHA)
    # The canvas and body center stay fixed so the pose cannot move the hitbox.
    for x in range(width):
        edge = (2 * x - width + 1) / width
        travel = left if edge < 0 else right
        shift = round(height * travel * swing * edge ** 2)
        result.blit(sprite, (x, shift), (x, 0, 1, height))
    return result


def boss_idle_frame(name, sprite, elapsed):
    if name not in IDLE_BODY_TRAVEL:
        return sprite
    if name == 'boss_dragon':
        sprite = frame('boss_dragon_attack', 0) or sprite
    return _body_pose(sprite, name, _IDLE_SWING[elapsed // 135 % len(_IDLE_SWING)])


def _signature_pose(signature, now):
    age = now - signature.impact_at
    if age < 0:
        return 1, -.75
    if signature.key == 'boss':
        if age >= BITE_REPEAT_MS:
            age -= BITE_REPEAT_MS
        return (2, 1) if age < CHASE_MS else (3, .35)
    if signature.key == 'boss_octopus':
        phase = age % LASH_MS / LASH_MS
        return (1, -.75) if phase < .23 else (2, 1) if phase < .72 else (3, .35)
    if signature.key == 'boss_lobster':
        if age < CLAW_DELAY_MS:
            return (2, 1) if age < 135 else (1, -.65)
        age -= CLAW_DELAY_MS
    if signature.key == 'boss_shark' and age < 3 * TRIDENT_INTERVAL_MS:
        age %= TRIDENT_INTERVAL_MS
    return _ATTACK_POSES[min(7, age // 75)]


def frame(name, index):
    if name in ('boss_dragon_attack', 'boss_dragon_laser') and index % 4 == 2:
        fire_breath = image_asset('animations/boss_dragon_fire_breath.png')
        if fire_breath is not None:
            return fire_breath
        index = 1
    sheet = image_asset('animations/anim_' + name + '.png')
    if sheet is None:
        return None
    size = sheet.get_height()
    count = sheet.get_width() // size
    if not count:
        return None
    key = (sheet, index % count)
    if key not in _FRAMES:
        _FRAMES[key] = sheet.subsurface(((index % count) * size, 0, size, size))
    return _FRAMES[key]


@lru_cache(maxsize=128)
def _visible_height_ratio(sprite):
    return sprite.get_bounding_rect(min_alpha=33).height / sprite.get_height()


def boss_action_size(sprite, idle, size):
    """Compensate for frame padding while limiting changes from pose to pose."""
    visible = _visible_height_ratio(sprite)
    idle_visible = _visible_height_ratio(idle)
    if not visible or not idle_visible:
        return size
    scale = max(.85, min(1.30, idle_visible / visible))
    return tuple(max(1, round(value * scale)) for value in size)


def action_frame(start, now):
    if start is None:
        return None
    elapsed = now - start
    return min(3, elapsed // 150) if 0 <= elapsed < 600 else None


def boss_frame(boss, now):
    mode = getattr(boss, 'fusion_mode', None)
    if boss.bdef['key'] == 'boss_zongzong' and mode:
        index = action_frame(getattr(boss, 'fusion_started_at', None), now)
        if index is not None:
            sprite = frame('boss_zongzong_' + ('rage' if mode == 'rage' else 'fusion'), index)
            if sprite is not None:
                return sprite
    warning = getattr(boss, 'laser_warning_start', 0)
    laser_active = now < getattr(boss, 'laser_active_until', 0)
    if warning or laser_active:
        if boss.bdef['key'] == 'boss_niu':
            elapsed = now - (boss.laser_active_until - 2000 if laser_active else warning)
            sprite = frame('boss_niu_laser', max(0, elapsed // (75 if laser_active else 50)) % 8)
            if sprite is not None:
                return sprite
        pose = DOWNWARD_LASER_POSES.get(boss.bdef['key'])
        if laser_active and pose and 1 <= boss.bdef.get('campaign_level', 0) <= 6:
            sprite = frame(boss.bdef['key'] + '_laser', pose[0])
            if sprite is not None:
                return sprite
        index = 1 if laser_active else min(1, max(0, (now - warning) // 250))
        name = boss.bdef['key']
        sprite = frame(name + '_laser', index) or frame(name + '_attack', index)
        if sprite is not None:
            return sprite
    start = getattr(boss, 'animation_attack_at', None)
    name = boss.bdef['key']
    if name in IDLE_BODY_TRAVEL:
        signature = getattr(boss, 'signature', None)
        if signature and name != 'boss_dragon' and now < signature.end_at:
            index, swing = _signature_pose(signature, now)
        elif start is not None and 0 <= now - start < 600:
            index, swing = _ATTACK_POSES[(now - start) // 75]
            # Dragon fireballs already set the animation clock back by 300 ms.
            if name == 'boss_dragon' and signature and 300 <= now - start < 450:
                index = 2
        else:
            return None
        sprite = frame(name + '_attack', index)
        return _body_pose(sprite, name, swing) if sprite is not None else None
    index = action_frame(start, now)
    if index is None:
        return None
    if name == 'boss_niu':
        index = min(7, (now - boss.animation_attack_at) // 75)
    pattern = getattr(boss, 'last_pattern', '')
    if name == 'boss_zongzong':
        action = 'bomb' if getattr(boss, 'attack_phase', 1) % 2 else 'wave'
        result = frame(name + '_' + action, index)
        if result is not None:
            return result
    if name == 'boss_niu' and pattern in ('vortex', 'lightning'):
        result = frame(name + '_' + pattern, index)
        if result is not None:
            return result
    return frame(name + '_attack', index)
