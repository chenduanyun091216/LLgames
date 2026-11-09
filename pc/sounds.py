"""
程序化生成音效——无需外部音频文件。
合成器工具包：带限波形 / 滤波噪声 / 音高扫频 / 包络 / 旋律 / 多轨混音。
"""
import math, random, struct
import pygame

_sound_cache = {}

SAMPLE_RATE = 22050


def ensure_audio():
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1)
        return pygame.mixer.get_init() is not None
    except (pygame.error, AttributeError):
        return False


# ── 合成器基础 ───────────────────────────────────────────────────────────────

def _clamp16(v):
    return int(max(-32767, min(32767, v)))

def _gen_tone(freq0, freq1, duration, wave='sine', vol=0.3, attack=0.003, decay=12.0,
              tremolo=0.0, trem_rate=8.0):
    """单音：音高从 freq0 指数扫到 freq1，起音+指数衰减包络。
    wave: sine / triangle / soft(带限方波，柔和) / saw(带限锯齿)"""
    n = int(SAMPLE_RATE * duration)
    out = []
    phase = 0.0
    ratio = (freq1 / freq0) if freq0 > 0 else 1.0
    for i in range(n):
        t = i / SAMPLE_RATE
        frac = i / max(1, n - 1)
        f = freq0 * (ratio ** frac)
        phase += 2 * math.pi * f / SAMPLE_RATE
        p = phase % (2 * math.pi)
        if wave == 'sine':
            v = math.sin(p)
        elif wave == 'triangle':
            v = math.asin(math.sin(p)) * (2 / math.pi)
        elif wave == 'soft':
            v = 0.7 * math.sin(p) + 0.2 * math.sin(3 * p) + 0.1 * math.sin(5 * p)
        else:  # saw
            v = 0.5 * math.sin(p) + 0.25 * math.sin(2 * p) + 0.12 * math.sin(3 * p)
        env = min(t / attack, 1.0) if attack > 0 else 1.0
        env *= math.exp(-t * decay)
        if tremolo > 0:
            env *= 1.0 - tremolo * (0.5 + 0.5 * math.sin(2 * math.pi * trem_rate * t))
        out.append(_clamp16(v * vol * env * 32767))
    return out

def _gen_fnoise(duration, vol=0.3, lp=0.3, attack=0.002, decay=10.0):
    """一阶低通滤波噪声：lp 越小越低沉柔和，越大越明亮。"""
    n = int(SAMPLE_RATE * duration)
    out = []
    prev = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        raw = random.uniform(-1, 1)
        prev = prev * (1 - lp) + raw * lp
        env = min(t / attack, 1.0) if attack > 0 else 1.0
        env *= math.exp(-t * decay)
        out.append(_clamp16(prev * vol * env * 32767))
    return out

def _melody(notes, wave='sine', vol=0.22, decay=8.0, attack=0.005):
    """notes: [(freq, dur), ...] 依次拼接成旋律。"""
    out = []
    for freq, dur in notes:
        out.extend(_gen_tone(freq, freq, dur, wave, vol, attack, decay))
    return out

def _mix_layers(layers):
    """layers: [(samples, offset_sec, gain), ...] 多轨混音并防削波。"""
    total = 0
    for samples, off, _g in layers:
        total = max(total, int(off * SAMPLE_RATE) + len(samples))
    out = [0] * total
    for samples, off, g in layers:
        base = int(off * SAMPLE_RATE)
        for i, s in enumerate(samples):
            out[base + i] += int(s * g)
    return [_clamp16(v) for v in out]

def _pack(samples):
    return struct.pack(f'<{len(samples)}h', *samples)


# ── 武器音效 ─────────────────────────────────────────────────────────────────

def _snd_shoot_pistol():
    """手枪：清脆短促的'啪'，快速下滑音 + 轻点击。"""
    return _mix_layers([
        (_gen_tone(950, 380, 0.065, 'soft', 0.42, attack=0.001, decay=32), 0.0, 1.0),
        (_gen_fnoise(0.02, 0.12, lp=0.5, decay=70), 0.0, 1.0),
    ])

def _snd_shoot_rifle():
    """步枪：有力的'砰'，中频冲击 + 低频体感 + 点击。"""
    return _mix_layers([
        (_gen_tone(520, 170, 0.085, 'soft', 0.32, attack=0.001, decay=24), 0.0, 1.0),
        (_gen_tone(150, 65, 0.08, 'sine', 0.26, attack=0.001, decay=22), 0.0, 1.0),
        (_gen_fnoise(0.03, 0.11, lp=0.45, decay=50), 0.0, 1.0),
    ])

def _snd_shoot_shotgun():
    """散弹枪：低沉宽厚的'轰'，深低频 + 宽噪声爆发。"""
    return _mix_layers([
        (_gen_tone(105, 42, 0.18, 'sine', 0.44, attack=0.001, decay=11), 0.0, 1.0),
        (_gen_tone(280, 110, 0.10, 'soft', 0.20, attack=0.001, decay=18), 0.0, 1.0),
        (_gen_fnoise(0.13, 0.24, lp=0.32, decay=16), 0.0, 1.0),
    ])

def _snd_shoot_sniper():
    """狙击枪：尖锐枪栓爆响 + 深沉尾音，有分量感。"""
    return _mix_layers([
        (_gen_fnoise(0.045, 0.22, lp=0.6, decay=32), 0.0, 1.0),
        (_gen_tone(130, 38, 0.30, 'sine', 0.42, attack=0.001, decay=8), 0.0, 1.0),
        (_gen_fnoise(0.22, 0.07, lp=0.18, decay=6), 0.02, 1.0),
    ])


# ── 战斗反馈 ─────────────────────────────────────────────────────────────────

def _snd_hit():
    """命中：短促有力的打击感——高频瞬态起音 + 中低频'砰'体感 + 噪声碎裂（播放频繁，音量克制）。"""
    return _mix_layers([
        (_gen_tone(920, 430, 0.035, 'soft', 0.27, attack=0.001, decay=42), 0.0, 1.0),
        (_gen_tone(250, 110, 0.055, 'triangle', 0.25, attack=0.001, decay=32), 0.0, 1.0),
        (_gen_fnoise(0.02, 0.07, lp=0.35, decay=60), 0.0, 1.0),
    ])

def _gen_kill_wav(duration=0.32, vol=0.34):
    """击败音效：低频下坠'砰'体感 + 柔和碎裂噪声 + 中频泛音尾韵。"""
    n_samples = int(SAMPLE_RATE * duration)
    samples = []
    prev_noise = 0.0
    for i in range(n_samples):
        t = i / SAMPLE_RATE
        f = 45 + 170 * math.exp(-t * 8.5)
        thump = math.sin(2 * math.pi * f * t) * math.exp(-t * 9.0)
        raw = random.uniform(-1, 1)
        prev_noise = prev_noise * 0.72 + raw * 0.28
        noise = prev_noise * math.exp(-t * 38.0) * 0.30
        crack = math.sin(2 * math.pi * (260 * math.exp(-t * 10.0) + 90) * t) * math.exp(-t * 16.0) * 0.22
        v = thump * 0.95 + noise + crack
        env = min(t * 250.0, 1.0) * min((duration - t) * 14.0, 1.0)
        s = int(max(-32767, min(32767, v * vol * env * 32767)))
        samples.append(s)
    return _pack(samples)


# ── 经济 / 界面 ─────────────────────────────────────────────────────────────

def _snd_coin():
    """金币：经典两音'叮-叮'，明亮愉悦。"""
    return _mix_layers([
        (_melody([(988, 0.055), (1319, 0.10)], 'sine', 0.26, decay=11), 0.0, 1.0),
        (_melody([(1976, 0.055), (2638, 0.10)], 'sine', 0.08, decay=11), 0.0, 1.0),
    ])

def _snd_buy():
    """购买：收银机'咔-叮'，轻快满足。"""
    return _mix_layers([
        (_gen_fnoise(0.03, 0.07, lp=0.7, decay=45), 0.0, 1.0),
        (_melody([(660, 0.06), (880, 0.12)], 'triangle', 0.24, decay=10), 0.02, 1.0),
    ])

def _snd_error():
    """错误：两声低柔的'嘟'，提示但不烦躁。"""
    return _melody([(155, 0.07), (115, 0.11)], 'triangle', 0.18, decay=13)


# ── 游戏流程 ─────────────────────────────────────────────────────────────────

def _snd_level_up():
    """过关：上行琶音 C-E-G-C，明亮庆祝感。"""
    return _mix_layers([
        (_melody([(523, 0.10), (659, 0.10), (784, 0.10), (1047, 0.22)], 'sine', 0.28, decay=7), 0.0, 1.0),
        (_melody([(1047, 0.10), (1319, 0.10), (1568, 0.10), (2093, 0.22)], 'sine', 0.08, decay=7), 0.0, 1.0),
    ])

def _snd_game_over():
    """失败：缓慢下行的忧伤旋律 A-F-D-A，余音渐弱。"""
    return _mix_layers([
        (_melody([(440, 0.28), (349, 0.28), (294, 0.28), (220, 0.45)], 'sine', 0.22, decay=3.5), 0.0, 1.0),
        (_melody([(220, 0.28), (175, 0.28), (147, 0.28), (110, 0.45)], 'sine', 0.09, decay=3.5), 0.0, 1.0),
    ])

def _snd_boss_appear():
    """Boss登场：深沉隆隆声渐强 + 黑暗上行 + 结尾重锤。"""
    return _mix_layers([
        (_gen_tone(46, 46, 0.95, 'sine', 0.36, attack=0.35, decay=2.2), 0.0, 1.0),
        (_gen_tone(58, 190, 0.75, 'saw', 0.14, attack=0.45, decay=2.5), 0.0, 1.0),
        (_gen_tone(90, 38, 0.22, 'sine', 0.40, attack=0.001, decay=13), 0.72, 1.0),
        (_gen_fnoise(0.10, 0.16, lp=0.3, decay=18), 0.72, 1.0),
    ])


# ── 技能音效 ─────────────────────────────────────────────────────────────────

def _snd_fire_cast():
    """火焰技能：温暖的呼啸上升 + 低频燃烧感。"""
    return _mix_layers([
        (_gen_fnoise(0.26, 0.26, lp=0.30, attack=0.07, decay=7), 0.0, 1.0),
        (_gen_tone(170, 430, 0.20, 'soft', 0.17, attack=0.02, decay=9), 0.0, 1.0),
        (_gen_tone(72, 60, 0.25, 'sine', 0.18, attack=0.01, decay=8), 0.0, 1.0),
    ])

def _snd_ice_cast():
    """冰霜技能：晶莹风铃音 + 寒冷 shimmer。"""
    return _mix_layers([
        (_melody([(1568, 0.07), (2093, 0.08), (1319, 0.13)], 'sine', 0.18, decay=10), 0.0, 1.0),
        (_gen_fnoise(0.16, 0.07, lp=0.7, decay=14), 0.0, 1.0),
        (_gen_fnoise(0.20, 0.12, lp=0.18, attack=0.03, decay=8), 0.0, 1.0),
    ])

def _snd_water_cast():
    """水系技能：上升的气泡音 + 轻柔水流。"""
    return _mix_layers([
        (_melody([(380, 0.06), (520, 0.06), (700, 0.10)], 'sine', 0.22, decay=18), 0.0, 1.0),
        (_gen_fnoise(0.22, 0.08, lp=0.22, attack=0.04, decay=9), 0.0, 1.0),
    ])

def _snd_grenade():
    """榴弹发射：沉闷的'嘭'抛出感。"""
    return _mix_layers([
        (_gen_tone(220, 85, 0.11, 'soft', 0.38, attack=0.001, decay=17), 0.0, 1.0),
        (_gen_fnoise(0.05, 0.12, lp=0.35, decay=30), 0.0, 1.0),
    ])

def _snd_lightning():
    """闪电链：电光'噼啪'，快速下滑啾声 + 电火花香。"""
    return _mix_layers([
        (_gen_tone(2600, 280, 0.11, 'soft', 0.22, attack=0.001, decay=19), 0.0, 1.0),
        (_gen_fnoise(0.09, 0.13, lp=0.55, decay=26), 0.0, 1.0),
        (_gen_tone(130, 60, 0.08, 'sine', 0.16, attack=0.001, decay=20), 0.0, 1.0),
    ])

def _snd_storm():
    """磁暴：低频电磁呼啸 + 脉冲震颤。"""
    return _mix_layers([
        (_gen_fnoise(0.55, 0.26, lp=0.22, attack=0.18, decay=3.5), 0.0, 1.0),
        (_gen_tone(68, 55, 0.55, 'sine', 0.26, attack=0.10, decay=3.5, tremolo=0.55, trem_rate=7), 0.0, 1.0),
    ])

def _snd_laser():
    """辐射激光：科幻光束'咻'，下行啁啾 + 能量嗡鸣。"""
    return _mix_layers([
        (_gen_tone(1500, 380, 0.20, 'saw', 0.22, attack=0.005, decay=6, tremolo=0.3, trem_rate=30), 0.0, 1.0),
        (_gen_tone(220, 220, 0.24, 'sine', 0.12, attack=0.005, decay=7), 0.0, 1.0),
        (_gen_fnoise(0.03, 0.12, lp=0.6, decay=40), 0.0, 1.0),
    ])

def _snd_laser_hit():
    """激光灼烧命中：短促的'嘶'电击声，适合高频重复播放。"""
    return _mix_layers([
        (_gen_fnoise(0.07, 0.13, lp=0.5, decay=30), 0.0, 1.0),
        (_gen_tone(1700, 420, 0.07, 'saw', 0.10, attack=0.001, decay=28), 0.0, 1.0),
        (_gen_tone(240, 120, 0.05, 'sine', 0.08, attack=0.001, decay=30), 0.0, 1.0),
    ])

def _snd_dart_cast():
    """飞镖释放：金属旋转呼啸，上行动机 + 高速颤音（旋转感）。"""
    return _mix_layers([
        (_gen_fnoise(0.28, 0.15, lp=0.45, attack=0.03, decay=9), 0.0, 1.0),
        (_gen_tone(700, 1500, 0.22, 'triangle', 0.13, attack=0.01, decay=8, tremolo=0.45, trem_rate=18), 0.0, 1.0),
        (_gen_tone(1400, 2800, 0.18, 'sine', 0.05, attack=0.01, decay=9, tremolo=0.45, trem_rate=18), 0.0, 1.0),
    ])

def _snd_dart_burst():
    """飞镖炸开：金属爆裂 + 低频冲击。"""
    return _mix_layers([
        (_gen_fnoise(0.22, 0.24, lp=0.42, decay=15), 0.0, 1.0),
        (_gen_tone(135, 45, 0.22, 'sine', 0.32, attack=0.001, decay=10), 0.0, 1.0),
        (_gen_tone(950, 260, 0.12, 'soft', 0.15, attack=0.001, decay=20), 0.0, 1.0),
    ])


_SOUND_BUILDERS = {
    'shoot_pistol': _snd_shoot_pistol,
    'shoot_rifle': _snd_shoot_rifle,
    'shoot_shotgun': _snd_shoot_shotgun,
    'shoot_sniper': _snd_shoot_sniper,
    'hit': _snd_hit,
    'coin': _snd_coin,
    'buy': _snd_buy,
    'error': _snd_error,
    'level_up': _snd_level_up,
    'game_over': _snd_game_over,
    'boss_appear': _snd_boss_appear,
    'fire_cast': _snd_fire_cast,
    'ice_cast': _snd_ice_cast,
    'water_cast': _snd_water_cast,
    'grenade': _snd_grenade,
    'lightning': _snd_lightning,
    'storm': _snd_storm,
    'laser': _snd_laser,
    'laser_hit': _snd_laser_hit,
    'dart_cast': _snd_dart_cast,
    'dart_burst': _snd_dart_burst,
}


def make_sound(key):
    if key in _sound_cache:
        return _sound_cache[key]
    if not ensure_audio():
        return None
    try:
        if key == 'kill':
            buf = _gen_kill_wav()
        elif key in _SOUND_BUILDERS:
            buf = _pack(_SOUND_BUILDERS[key]())
        else:
            buf = _pack(_gen_tone(400, 300, 0.1, 'soft', 0.2))
        snd = pygame.mixer.Sound(buffer=buf)
    except (pygame.error, AttributeError):
        return None
    _sound_cache[key] = snd
    return snd


def play_sound(key):
    snd = make_sound(key)
    if snd:
        snd.play()


# ── 背景音乐：程序化循环乐曲生成 ─────────────────────────────────────────────

_music_cache = {}

# Am - F - C - G 和弦进行（低音根音 + 和弦音）
_CHORDS = [
    (110.00, [220.00, 261.63, 329.63]),   # Am
    (87.31,  [174.61, 220.00, 261.63]),   # F
    (130.81, [261.63, 329.63, 392.00]),   # C
    (98.00,  [196.00, 246.94, 293.66]),   # G
]

def start_music(level=0, boss=False, infinite=False, variant=0):
    """生成并循环播放背景音乐。
    level=0 为主菜单（舒缓）；level>=1 为关卡战斗曲；boss=True 更急促低沉；
    infinite/variant 用于无限模式的变奏。"""
    if not ensure_audio():
        return
    if 'bg' in _music_cache:
        _music_cache['bg'].stop()
        del _music_cache['bg']
    try:
        menu = (level <= 0)
        rng = random.Random(level * 977 + variant * 131 + (7 if boss else 0))
        tempo = 0.26 if menu else (0.155 if boss else 0.19)
        if infinite:
            tempo *= 0.94
        bass_vol = 0.085 if menu else 0.09
        mel_vol = 0.065 if menu else 0.07
        mel_decay = 3.2 if menu else 4.5
        chords = _CHORDS if variant % 2 == 0 else [ _CHORDS[0], _CHORDS[3], _CHORDS[2], _CHORDS[1] ]
        samples = []
        bar_len = int(SAMPLE_RATE * tempo * 4)
        for bar in range(8):
            root, tones = chords[(bar // 2) % len(chords)]
            # 低音轨
            if boss:
                bass = list(_gen_tone(root, root, tempo, 'sine', bass_vol, attack=0.004, decay=3.5))
                bass += list(_gen_tone(root * 1.5, root * 1.5, tempo, 'sine', bass_vol * 0.8, attack=0.004, decay=3.5)) * 1
                bass += list(_gen_tone(root, root, tempo * 2, 'sine', bass_vol, attack=0.004, decay=3.0))
            else:
                bass = list(_gen_tone(root, root, tempo * 4, 'sine', bass_vol, attack=0.01, decay=1.6))
            if len(bass) < bar_len:
                bass += [0] * (bar_len - len(bass))
            # 旋律轨
            mel = []
            for _s in range(4):
                if menu and rng.random() < 0.3:
                    mel.extend([0] * int(SAMPLE_RATE * tempo))
                elif not menu and rng.random() < 0.15:
                    mel.extend([0] * int(SAMPLE_RATE * tempo))
                else:
                    f = rng.choice(tones + [root * 2])
                    mel.extend(_gen_tone(f, f, tempo, 'sine', mel_vol, attack=0.004, decay=mel_decay))
            if len(mel) < bar_len:
                mel += [0] * (bar_len - len(mel))
            mixed = [_clamp16(b + m) for b, m in zip(bass[:bar_len], mel[:bar_len])]
            samples.extend(mixed)
        buf = _pack(samples)
        snd = pygame.mixer.Sound(buffer=buf)
        snd.set_volume(0.55 if menu else 0.38)
        snd.play(loops=-1)
        _music_cache['bg'] = snd
    except (pygame.error, AttributeError):
        pass
