"""
程序化生成音效——无需外部音频文件。
合成器工具包：带限波形 / 滤波噪声 / 音高扫频 / 包络 / 旋律 / 多轨混音。
"""
import math, random, struct
from time import perf_counter
import pygame

_sound_cache = {}

SAMPLE_RATE = 22050
_MUSIC_CHANNEL = 0


def ensure_audio():
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=1)
        if pygame.mixer.get_init() is None:
            return False
        pygame.mixer.set_reserved(_MUSIC_CHANNEL + 1)
        return True
    except (pygame.error, AttributeError):
        return False


# ── 合成器基础 ───────────────────────────────────────────────────────────────

def _clamp16(v):
    return int(max(-32767, min(32767, v)))

def _gen_tone(freq0, freq1, duration, wave='sine', vol=0.3, attack=0.003, decay=12.0,
              tremolo=0.0, trem_rate=8.0):
    generator = _tone_steps(freq0, freq1, duration, wave, vol, attack, decay, tremolo, trem_rate)
    try:
        while True:
            next(generator)
    except StopIteration as finished:
        return finished.value


def _tone_steps(freq0, freq1, duration, wave='sine', vol=0.3, attack=0.003, decay=12.0,
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
        if (i + 1) % 1024 == 0:
            yield
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
        (_gen_tone(235, 85, 0.074, 'triangle', 0.29, attack=0.001, decay=30), 0.0, 1.0),
        (_gen_fnoise(0.02, 0.07, lp=0.35, decay=60), 0.0, 1.0),
    ])

def _snd_niu_shield_hit():
    return _mix_layers([
        (_gen_fnoise(0.025, 0.13, lp=0.45, decay=65), 0.0, 1.0),
        (_gen_tone(1240, 1170, 0.105, 'triangle', 0.21, attack=0.001, decay=26), 0.0, 1.0),
        (_gen_tone(710, 670, 0.13, 'sine', 0.15, attack=0.001, decay=21), 0.0, 1.0),
    ])

def _snd_niu_axe_impact():
    return _mix_layers([
        (_gen_tone(145, 38, 0.28, 'sine', 0.54, attack=0.001, decay=11), 0.0, 1.0),
        (_gen_fnoise(0.19, 0.32, lp=0.40, decay=18), 0.0, 1.0),
        (_gen_tone(680, 160, 0.08, 'triangle', 0.24, attack=0.001, decay=35), 0.0, 1.0),
    ])

def _snd_player_hit():
    return _mix_layers([
        (_gen_fnoise(0.09, 0.38, lp=0.55, decay=32), 0.0, 1.0),
        (_gen_tone(185, 58, 0.24, 'triangle', 0.58, attack=0.001, decay=15), 0.0, 1.0),
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

def _snd_orochi_thunder():
    """Sharp lightning followed by a low rolling thunderclap."""
    return _mix_layers([
        (_snd_lightning(), 0.0, 0.8),
        (_gen_fnoise(0.52, 0.45, lp=0.12, attack=0.025, decay=4.5), 0.03, 1.0),
        (_gen_tone(92, 39, 0.46, 'sine', 0.32, attack=0.02, decay=5), 0.06, 1.0),
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
    'niu_shield_hit': _snd_niu_shield_hit,
    'niu_axe_impact': _snd_niu_axe_impact,
    'player_hit': _snd_player_hit,
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
    'orochi_thunder': _snd_orochi_thunder,
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

# Seconds per eighth note, bass roots (MIDI), lead timbre and an eight-step motif.
# Motif pitches are semitones above the current bass root; None leaves space.
_MUSIC_THEMES = (
    (0.282, (45, 41, 48, 43), 'sine', (24, None, 31, None, 36, 31, None, 27)),   # 菜单
    (0.240, (48, 45, 41, 43), 'triangle', (24, 28, 31, None, 33, 31, 28, None)), # 温柔浅滩
    (0.226, (45, 48, 41, 43), 'sine', (31, None, 27, 24, None, 34, None, 31)),   # 迷失城堡
    (0.177, (50, 50, 46, 48), 'soft', (24, 24, None, 31, 27, None, 34, 31)),    # 海底激战
    (0.202, (43, 47, 48, 45), 'triangle', (None, 31, 36, 40, None, 36, 33, 31)), # 珊瑚礁岛
    (0.255, (43, 39, 46, 41), 'triangle', (31, None, None, 34, 27, None, 26, None)), # 沉船迷航
    (0.268, (40, 41, 36, 35), 'sine', (24, None, 25, None, 31, None, None, 27)), # 黑暗森林
    (0.152, (40, 40, 43, 41), 'saw', (24, 24, 31, None, 30, 27, 24, None)),      # 死亡火山
    (0.189, (49, 45, 52, 47), 'soft', (36, None, 31, 38, 33, None, 40, 31)),     # 粽子星球
)

_pending_music = None
_requested_music = None


def start_music(level=0, boss=False, infinite=False, variant=0):
    """Queue a track without synthesizing it inside a gameplay update."""
    global _pending_music, _requested_music
    track = (level, boss, infinite, variant)
    if track != _requested_music:
        _requested_music = track
        _pending_music = _music_pcm(*track)


def advance_music(budget=0.004):
    """Give synthesis a small frame budget and keep playing the previous track."""
    global _pending_music, _requested_music
    if _pending_music is None:
        return
    try:
        deadline = perf_counter() + budget
        while perf_counter() < deadline:
            next(_pending_music)
    except StopIteration as finished:
        _pending_music = None
        if not ensure_audio():
            _requested_music = None
            return
        try:
            snd = pygame.mixer.Sound(buffer=finished.value)
            snd.set_volume(0.55 if _requested_music[0] <= 0 else 0.38)
            # Replacing a sound on the same channel keeps the handoff exclusive.
            pygame.mixer.Channel(_MUSIC_CHANNEL).play(snd, loops=-1, fade_ms=30)
        except (pygame.error, AttributeError):
            _requested_music = None


def _music_note(cache, midi, seconds, wave, volume, attack, decay):
    key = (midi, seconds, wave, volume, attack, decay)
    if key in cache:
        return cache[key]
    freq = 440 * 2 ** ((midi - 69) / 12)
    samples = yield from _tone_steps(freq, freq, seconds, wave, volume, attack=attack, decay=decay)
    release = min(len(samples), SAMPLE_RATE // 160)
    for i in range(release):
        samples[-1 - i] = int(samples[-1 - i] * i / release)
    cache[key] = samples
    return samples


def _music_pcm(level, boss, infinite, variant):
    tempo, roots, wave, motif = _MUSIC_THEMES[max(0, level) % len(_MUSIC_THEMES)]
    if boss:
        tempo *= 0.82
    if infinite:
        tempo *= 0.94
    if variant % 2:
        roots = (roots[0], roots[3], roots[2], roots[1])
    steps = len(motif)
    step_len = int(SAMPLE_RATE * tempo)
    note_cache = {}
    pcm = bytearray()
    for bar in range(8):
        root = roots[bar % len(roots)]
        bass = []
        for step in (0, 2, 4, 6) if boss else (0, 4):
            pitch = root + (7 if step == 6 else 0)
            note = yield from _music_note(note_cache, pitch, tempo * (2 if boss else 4),
                                          'soft' if boss else 'sine', 0.105, 0.006, 4 if boss else 2.2)
            bass.extend(note[:step_len * (2 if boss else 4)])
        for step, interval in enumerate(motif):
            if interval is None:
                lead = [0] * step_len
            else:
                pitch = root + interval + (12 if bar >= 4 and step in (2, 5) else 0)
                lead = yield from _music_note(note_cache, pitch, tempo, wave, 0.105, 0.008, 4.5)
            offset = step * step_len
            for start in range(0, step_len, 1024):
                end = min(start + 1024, step_len)
                pcm.extend(_pack([_clamp16(b + m) for b, m in
                                  zip(bass[offset + start:offset + end], lead[start:end])]))
                yield
    # Integer subdivision can trim a sample from the last bass note.
    pcm[-2:] = b'\0\0'
    return bytes(pcm)
