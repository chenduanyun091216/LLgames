"""
图片素材加载工具。
运行时优先使用 assets/images 下的 PNG；缺失时返回 None，让旧的代码绘制兜底。
"""
import os
from collections import OrderedDict
from functools import lru_cache

import pygame

ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'images')
web_hd_assets = False
_IMAGE_CACHE = {}
SCALE_CACHE_LIMIT = 48 * 1024 ** 2
_SCALED_CACHE = OrderedDict()
_scaled_cache_bytes = 0


@lru_cache(maxsize=256)
def _image_path(directory, name, hd):
    if hd:
        alternate = os.path.join(os.path.dirname(directory), 'images-hd', name)
        if os.path.isfile(alternate):
            return alternate
    return os.path.join(directory, name)


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


def image_asset(name, size=None):
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    path = _image_path(ASSET_DIR, name, web_hd_assets)
    surf = _IMAGE_CACHE.get(path)
    if surf is None:
        try:
            surf = pygame.image.load(path).convert_alpha()
        except (pygame.error, FileNotFoundError):
            return None
        _IMAGE_CACHE[path] = surf
    return scale_surface_cached(surf, size) if size else surf


def cover_image_asset(name, size, *, panorama=False):
    """Scale/crop a large source to a target view without retaining its full-size copy."""
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    path = _image_path(ASSET_DIR, name, web_hd_assets)
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
        crop_w = min(src_w, max(1, round(width / scale)))
        crop = source.subsurface(((src_w - crop_w) // 2, 0, crop_w, src_h))
        image = pygame.transform.smoothscale(crop, (width, round(src_h * scale)))
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
