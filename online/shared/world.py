"""Canonical room viewports using the exact single-player mobile layout rules."""
from functools import lru_cache
from game_core import config

WORLD_SIZES = {'landscape': (960, 720), 'portrait': (480, 720)}
_LAYOUT_FIELDS = ('SCREEN_WIDTH', 'SCREEN_HEIGHT', 'GAME_AREA_LEFT', 'GAME_AREA_RIGHT',
                  'GAME_AREA_BOTTOM', 'MOBILE_LANDSCAPE_VIEW', 'VIEW_SCALE',
                  'VIEW_OFFSET', 'VIEW_SIZE')


@lru_cache(maxsize=2)
def _canonical_layout(orientation):
    # Run the real single-player layout function, not a parallel arithmetic
    # implementation. Cache only geometry: do not allocate a new Surface/tick.
    previous_surface = config.SCR
    config.update_mobile_view(WORLD_SIZES[orientation])
    layout = tuple(getattr(config, field) for field in _LAYOUT_FIELDS)
    config.SCR = previous_surface
    return layout


def configure_world(orientation='landscape'):
    if orientation not in WORLD_SIZES:
        raise ValueError('Unsupported room orientation')
    for field, value in zip(_LAYOUT_FIELDS, _canonical_layout(orientation)):
        setattr(config, field, value)
    return WORLD_SIZES[orientation]
