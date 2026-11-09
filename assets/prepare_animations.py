"""Prepare aligned runtime sheets from the generated animation drafts."""
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
SIZE = 160


def prepare(path):
    image = Image.open(path).convert('RGBA')
    alpha = image.getchannel('A').point(lambda value: 0 if value < 25 else value)
    image.putalpha(alpha)
    cuts = [0]
    if not path.stem.endswith('_back'):
        counts = [sum(v > 48 for v in alpha.crop((x, 0, x + 1, image.height)).getdata()) for x in range(image.width)]
        for index in range(1, 4):
            center, radius = image.width * index // 4, image.width // 16
            cuts.append(min(range(center - radius, center + radius),
                            key=lambda x: (sum(counts[x-2:x+3]), abs(x-center))))
    cuts.append(image.width)
    frames = []
    for left, right in zip(cuts, cuts[1:]):
        part = image.crop((left, 0, right, image.height))
        box = part.getchannel('A').point(lambda a: 255 if a > 48 else 0).getbbox()
        if not box:
            raise ValueError(f'Empty frame: {path}')
        frames.append(part.crop(box))
    scale = min((SIZE-8) / max(f.width for f in frames), (SIZE-8) / max(f.height for f in frames))
    sheet = Image.new('RGBA', (SIZE * len(frames), SIZE))
    for index, frame in enumerate(frames):
        frame = frame.resize((max(1, round(frame.width * scale)), max(1, round(frame.height * scale))), Image.Resampling.LANCZOS)
        sheet.alpha_composite(frame, (index * SIZE + (SIZE-frame.width)//2, SIZE-4-frame.height))
    name = path.stem.replace('zongzong_attack', 'boss_zongzong_attack').replace('boss_niu_vortex_v2', 'boss_niu_vortex').replace('boss_zongzong_wave_v2', 'boss_zongzong_wave').replace('boss_zongzong_bomb_v2', 'boss_zongzong_bomb').replace('boss_niu_laser_v2', 'boss_niu_laser')
    sheet.save(ROOT / 'images' / ('anim_' + name + '.png'), optimize=True)


if __name__ == '__main__':
    for draft in sorted((ROOT / 'animation_drafts').glob('*.png')):
        prepare(draft)
