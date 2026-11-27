"""
图片素材加载工具。
按画质读取对应的图片目录，缺图时回退到 assets/images。
"""
import os
from collections import OrderedDict
from functools import lru_cache

import pygame

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'images')
web_hd_assets = False
pc_4k_assets = False
_IMAGE_CACHE = {}
_PC_4K_IMAGE_CACHE = OrderedDict()
_pc_4k_cache_bytes = 0
PC_4K_IMAGE_CACHE_LIMIT = 512 * 1024 ** 2
SCALE_CACHE_LIMIT = 48 * 1024 ** 2
_SCALED_CACHE = OrderedDict()
_scaled_cache_bytes = 0
_PC_4K_SHARED_ART = frozenset({
    # These redraws have a visible matte around the light effects.
    'effects/lightning_reactor.png',
    'effects/mecha_emp_ring.png',
})


def image_variant():
    if pc_4k_assets:
        return 'images_lg'
    return 'images-hd' if web_hd_assets else ''


@lru_cache(maxsize=256)
def _image_path(directory, name, variant):
    if variant and (variant != 'images_lg' or name not in _PC_4K_SHARED_ART):
        alternate = os.path.join(os.path.dirname(directory), variant, name)
        if os.path.isfile(alternate):
            return alternate
    original = os.path.join(directory, name)
    return original if os.path.isfile(original) else None


def scale_surface_cached(surf, size, smooth=True):
    """Cache repeated integer-size transforms used by animated entities."""
    global _scaled_cache_bytes
    size = (max(1, int(size[0])), max(1, int(size[1])))
    if surf.get_size() == size:
        return surf
    key = (surf, size, smooth)
    cached = _SCALED_CACHE.get(key)
    if cached is not None:
        _SCALED_CACHE.move_to_end(key)
        return cached
    scaler = pygame.transform.smoothscale if smooth else pygame.transform.scale
    cached = scaler(surf, size)
    cost = cached.get_pitch() * cached.get_height()
    if cost <= SCALE_CACHE_LIMIT:
        while _scaled_cache_bytes + cost > SCALE_CACHE_LIMIT:
            _, old = _SCALED_CACHE.popitem(last=False)
            _scaled_cache_bytes -= old.get_pitch() * old.get_height()
        _SCALED_CACHE[key] = cached
        _scaled_cache_bytes += cost
    return cached


def _load_image(path):
    try:
        return pygame.image.load(path).convert_alpha()
    except (pygame.error, FileNotFoundError):
        return None


def _remember_image(path, surf, use_4k):
    global _pc_4k_cache_bytes
    if use_4k:
        if path in _PC_4K_IMAGE_CACHE:
            return _PC_4K_IMAGE_CACHE[path]
        cost = surf.get_pitch() * surf.get_height()
        if cost <= PC_4K_IMAGE_CACHE_LIMIT:
            while _pc_4k_cache_bytes + cost > PC_4K_IMAGE_CACHE_LIMIT:
                _, old = _PC_4K_IMAGE_CACHE.popitem(last=False)
                _pc_4k_cache_bytes -= old.get_pitch() * old.get_height()
            _PC_4K_IMAGE_CACHE[path] = surf
            _pc_4k_cache_bytes += cost
        return surf
    return _IMAGE_CACHE.setdefault(path, surf)


def prepare_images(names, variant):
    """Decode uncached art on a worker without changing the drawing caches."""
    prepared = {}
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return prepared
    for name in names:
        path = _image_path(ASSET_DIR, name, variant)
        if path is None or path in prepared:
            continue
        use_4k = variant == 'images_lg' and path != os.path.join(ASSET_DIR, name)
        cache = _PC_4K_IMAGE_CACHE if use_4k else _IMAGE_CACHE
        if path not in cache:
            surf = _load_image(path)
            if surf is not None:
                prepared[path] = surf, use_4k
    return prepared


def remember_prepared_images(prepared):
    for path, (surf, use_4k) in prepared.items():
        _remember_image(path, surf, use_4k)


def image_asset(name, size=None):
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    path = _image_path(ASSET_DIR, name, image_variant())
    if path is None:
        return None
    use_4k = pc_4k_assets and path != os.path.join(ASSET_DIR, name)
    cache = _PC_4K_IMAGE_CACHE if use_4k else _IMAGE_CACHE
    surf = cache.get(path)
    if surf is None:
        surf = _load_image(path)
        if surf is None:
            return None
        surf = _remember_image(path, surf, use_4k)
    elif use_4k:
        cache.move_to_end(path)
    return scale_surface_cached(surf, size) if size else surf


def cover_image_asset(name, size, *, panorama=False, variant=None):
    """Scale/crop a large source to a target view without retaining its full-size copy."""
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    path = _image_path(ASSET_DIR, name, image_variant() if variant is None else variant)
    if path is None:
        return None
    try:
        source = pygame.image.load(path)
    except (pygame.error, FileNotFoundError):
        return None
    opaque = path.endswith('.jpg')
    source = source.convert() if opaque else source.convert_alpha()
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    src_w, src_h = source.get_size()
    if panorama:
        # Keep at least half a screen of travel in tall phone layouts.
        scale = max(width / src_w, 1.5 * height / src_h)
        target_size = (width, round(src_h * scale))
        crop_w = min(src_w, max(1, round(width / scale)))
        if opaque and crop_w == src_w and source.get_size() == target_size:
            return source
        crop = source.subsurface(((src_w - crop_w) // 2, 0, crop_w, src_h))
        image = pygame.transform.smoothscale(crop, target_size)
        return image if opaque else image.convert(32)
    crop_w = min(src_w, max(1, round(src_h * width / height)))
    crop_h = min(src_h, max(1, round(src_w * height / width)))
    crop = source.subsurface(((src_w - crop_w) // 2, (src_h - crop_h) // 2, crop_w, crop_h))
    return pygame.transform.smoothscale(crop, (width, height))


def image_asset_supersampled(name, display_size, scale=1.5):
    """从高清 PNG 加载 display_size*scale 的超采样版本，供运行时缩小采样（避免放大模糊）。

    素材缺失时返回 None，调用方应回退到普通 surface 放大。"""
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    surf = image_asset(name)
    if surf is None:
        return None
    target = (max(1, int(display_size[0] * scale)), max(1, int(display_size[1] * scale)))
    return scale_surface_cached(surf, target)
