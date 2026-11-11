"""Package the Phaser client with assets and balance data from the original game."""
import hashlib
import json
import os
import random
import shutil
import sys
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT.parent
DIST = PROJECT / 'dist'
sys.path.insert(0, str(ROOT))
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = '1'

from game_core import config, sounds


def fields(value):
    return {key: getattr(value, key) for key in value.__slots__}


def campaign_data():
    tables = {key: value for key, value in vars(config).items()
              if key.startswith(('CAMPAIGN_', 'INFINITE_')) and isinstance(value, (dict, tuple))}
    return dict(tables, levels=config.LEVEL_CONFIGS, bosses=config.BOSS_DEFS,
                enemies={value['key']: value for value in config.ENEMY_DEFS},
                weapons={key: fields(value) for key, value in config.WEAPON_DEFS.items()},
                characters={key: dict(fields(value), skills=[fields(s) for s in value.skills])
                            for key, value in config.CHARACTER_DEFS.items()},
                difficulty=[fields(value) for value in config.DIFFICULTY_PRESETS.values()])


def image_asset(source):
    relative = source.relative_to(ROOT / 'assets' / 'images')
    key = relative.with_suffix('').as_posix()
    destination = DIST / 'art' / relative.with_suffix('.webp')
    destination.parent.mkdir(parents=True, exist_ok=True)
    folder = 'enemies' if relative.parts[:2] == ('animations', 'enemies') else relative.parts[0]
    with Image.open(source) as image:
        frame = None
        grids = {'boss_niu_actions': (2, 2), 'boss_niu_axe_sequence': (2, 2),
                 'anim_boss_orochi_idle': (6, 4), 'anim_boss_orochi_split': (4, 3),
                 'anim_boss_ancient_whale': (8, 6)}
        grid = grids.get(source.stem)
        if not grid and folder == 'animations' and image.width % image.height == 0:
            grid = (image.width // image.height, 1)
        if grid:
            cols, rows = grid
            fw, fh = image.width // cols, image.height // rows
            ratio = min(1, 256 / max(fw, fh))
            frame = [round(fw * ratio), round(fh * ratio)]
            image = image.convert('RGBA').resize((cols * frame[0], rows * frame[1]), Image.Resampling.LANCZOS)
        else:
            image = image.convert('RGB' if folder == 'backgrounds' else 'RGBA')
            limit = {'backgrounds': (1440, 2160), 'ui': (1024, 720), 'bosses': (800, 800),
                     'effects': (512, 512), 'enemies': (256, 256)}.get(folder, (384, 384))
            image.thumbnail(limit, Image.Resampling.LANCZOS)
        image.save(destination, 'WEBP', quality=87, method=4)
    return key, {'url': destination.relative_to(DIST).as_posix(), 'frame': frame}


def save_wav(name, pcm):
    path = DIST / 'audio' / (name + '.wav')
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, sounds.SAMPLE_RATE, 0, 'NONE', 'not compressed'))
        output.writeframes(pcm)


def music(level, boss=False):
    generator = sounds._music_pcm(level, boss, False, 0)
    try:
        while True:
            next(generator)
    except StopIteration as result:
        return result.value


def build():
    DIST.mkdir(exist_ok=True)
    for name in ('index.html', 'style.css', 'sw.js'):
        shutil.copy2(PROJECT / name, DIST / name)
    shutil.copytree(PROJECT / 'src', DIST / 'src', dirs_exist_ok=True)
    for name in ('phaser.min.js', 'LICENSE.md'):
        shutil.copy2(PROJECT / 'node_modules' / 'phaser' / (('dist/' if name.endswith('.js') else '') + name), DIST / name)
    images = sorted((ROOT / 'assets' / 'images').rglob('*.png'))
    with ThreadPoolExecutor(max_workers=4) as pool:
        manifest = dict(pool.map(image_asset, images))
    current_art = {DIST / asset['url'] for asset in manifest.values()}
    for path in (DIST / 'art').rglob('*.webp'):
        if path not in current_art:
            path.unlink()
    (DIST / 'assets.json').write_text(json.dumps(manifest), encoding='utf-8')
    (DIST / 'campaign.json').write_text(json.dumps(campaign_data(), ensure_ascii=False), encoding='utf-8')
    (DIST / 'audio').mkdir(exist_ok=True)
    random.seed(0)
    for name, fn in {'pistol': sounds._snd_shoot_pistol, 'rifle': sounds._snd_shoot_rifle,
                     'shotgun': sounds._snd_shoot_shotgun, 'sniper': sounds._snd_shoot_sniper,
                     'hit': sounds._snd_hit, 'hurt': sounds._snd_player_hit, 'coin': sounds._snd_coin,
                     'skill': sounds._snd_grenade, 'boss': sounds._snd_boss_appear,
                     'clear': sounds._snd_level_up}.items():
        save_wav(name, sounds._pack(fn()))
    for level in range(12):
        save_wav(f'music-{level}', music(level))
        if level:
            save_wav(f'music-{level}-boss', music(level, boss=True))
    digest = hashlib.sha256()
    files = sorted(path for path in DIST.rglob('*') if path.is_file() and path.name != 'offline.json')
    for path in files:
        digest.update(path.relative_to(DIST).as_posix().encode())
        digest.update(path.read_bytes())
    (DIST / 'offline.json').write_text(json.dumps({'version': digest.hexdigest()[:16],
        'files': ['./', *(p.relative_to(DIST).as_posix() for p in files)]}), encoding='utf-8')
    print(f'Phaser Web build: {len(files)} files, {sum(p.stat().st_size for p in files) / 1e6:.1f} MB')


if __name__ == '__main__':
    build()
