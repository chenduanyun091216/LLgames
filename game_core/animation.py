"""Small sprite-sheet helper for character and boss animations."""
from .asset_loader import image_asset

_FRAMES = {}


def frame(name, index):
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
        index = 1 if laser_active else min(1, max(0, (now - warning) // 250))
        name = boss.bdef['key']
        sprite = frame(name + '_laser', index) or frame(name + '_attack', index)
        if sprite is not None:
            return sprite
    index = action_frame(getattr(boss, 'animation_attack_at', None), now)
    if index is None:
        return None
    name = boss.bdef['key']
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
