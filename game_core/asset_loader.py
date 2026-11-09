"""
图片素材加载工具。
运行时优先使用 assets/images 下的 PNG；缺失时返回 None，让旧的代码绘制兜底。
"""
import os
import pygame


ASSET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'assets', 'images')
PREFERRED_ASSET_DIR = None
_IMAGE_CACHE = {}
_SCALED_CACHE = {}


def scale_surface_cached(surf, size, smooth=True):
    """Cache repeated integer-size transforms used by animated entities."""
    size = (max(1, int(size[0])), max(1, int(size[1])))
    if surf.get_size() == size:
        return surf
    key = (surf, size, smooth)
    cached = _SCALED_CACHE.get(key)
    if cached is None:
        scaler = pygame.transform.smoothscale if smooth else pygame.transform.scale
        cached = scaler(surf, size)
        _SCALED_CACHE[key] = cached
    return cached


def image_asset(name, size=None):
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    source_key = (PREFERRED_ASSET_DIR, name, None)
    cache_key = (PREFERRED_ASSET_DIR, name, None if size is None else tuple(size))
    cached = _IMAGE_CACHE.get(cache_key)
    if cached is not None:
        return cached
    surf = _IMAGE_CACHE.get(source_key)
    if surf is None:
        for directory in (PREFERRED_ASSET_DIR, ASSET_DIR):
            if directory is None:
                continue
            path = os.path.join(directory, name)
            try:
                surf = pygame.image.load(path).convert_alpha()
            except (pygame.error, FileNotFoundError):
                continue
            _IMAGE_CACHE[source_key] = surf
            break
        if surf is None:
            return None
    if size and surf.get_size() != size:
        surf = scale_surface_cached(surf, size)
    _IMAGE_CACHE[cache_key] = surf
    return surf


def cover_image_asset(name, size):
    """Scale/crop a large source to a target view without retaining its full-size copy."""
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    path = os.path.join(ASSET_DIR, name)
    try:
        source = pygame.image.load(path).convert_alpha()
    except (pygame.error, FileNotFoundError):
        return None
    width, height = max(1, int(size[0])), max(1, int(size[1]))
    src_w, src_h = source.get_size()
    crop_w = min(src_w, max(1, round(src_h * width / height)))
    crop_h = min(src_h, max(1, round(src_w * height / width)))
    crop = source.subsurface(((src_w - crop_w) // 2, (src_h - crop_h) // 2, crop_w, crop_h))
    return pygame.transform.smoothscale(crop, (width, height))


def image_asset_supersampled(name, display_size, scale=1.5):
    """从高清 PNG 加载 display_size*scale 的超采样版本，供运行时缩小采样（避免放大模糊）。

    素材缺失时返回 None，调用方应回退到普通 surface 放大。"""
    if os.environ.get('TTGAMES_DISABLE_IMAGE_ASSETS') == '1':
        return None
    path = os.path.join(ASSET_DIR, name)
    if not os.path.exists(path):
        return None
    try:
        surf = image_asset(name)
    except (pygame.error, FileNotFoundError):
        return None
    if surf is None:
        return None
    target = (max(1, int(display_size[0] * scale)), max(1, int(display_size[1] * scale)))
    return scale_surface_cached(surf, target)
