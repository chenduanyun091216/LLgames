"""Display authoritative visual snapshots using the unchanged original pygame renderer."""
import pygame
from functools import lru_cache
from game_core import config, entities as E
from game_core import special_bosses as S, orochi as O
from game_core.background import make_background
from game_core.sounds import play_sound, start_music, advance_music
from game_core.game import Game, GameState
from game_core.asset_loader import scale_surface_cached
from game_core.boss_skills import BossSignature
from game_core.sprites import (make_player_surface, make_fire_player_surface,
    make_ice_player_surface, make_water_player_surface, make_radiation_player_surface)
from online.shared.world import WORLD_SIZES, configure_world
from .snapshot import SCHEMA, CLASSES, COLLECTIONS, GAME_FIELDS, DATA_KEYS, DEFINITION_KEYS

@lru_cache(maxsize=2)
def _orochi_fire_art(gold):
    # Rebuild the two original resource variants once, never once per frame.
    art = O._load_art('effects/orochi_fireball.png')
    if art is not None and gold:
        return O._gold_fireball(art)
    return art

class _View(Game):
    @property
    def players(self):
        players = getattr(self, 'all_players', (self.player,))
        return [p for p in players if getattr(p,'alive',True)] or list(players)
    def _players_to_draw(self):
        return [p for p in getattr(self, 'all_players', self.players)
                if getattr(p, 'alive', True) or p.character in config.CHARACTER_DEFS] or self.players
    def _player_downed_age(self, player, now):
        if getattr(player, 'alive', True):
            return None
        return 360 if player.animation_hit_at is None else now - player.animation_hit_at
    def _draw_hud(self): pass
    def _draw_player_label(self, player, label):
        super()._draw_player_label(player, 'P' + str(getattr(player,'slot',1)))
    def _draw_invincible_shield(self, player):
        before = self.player_invincible_until
        self.player_invincible_until = getattr(player,'invincible_until',before)
        super()._draw_invincible_shield(player)
        self.player_invincible_until = before

class Presentation:
    def __init__(self, surface):
        self.orientation = next((key for key, size in WORLD_SIZES.items()
                                 if size == surface.get_size()), None)
        if self.orientation is None:
            raise ValueError('Expected an authoritative room-sized logical surface')
        configure_world(self.orientation)
        config.SCR = surface
        self.surface = surface
        self.view = _View(scroll_campaign_backgrounds=True)
        self.view.mobile_controls.draw = lambda *args: None
        self.objects = {}
        self.time_ms = 0
        self.local_slot = 1
        self.match_id = None
        self._last_sound_id = -1
        self._music_boss = None
        self._background_level = None

    def _construct(self, record):
        name, f = record['type'], record['fields']
        if name not in CLASSES: raise ValueError('Unknown visual type')
        if name == 'Player': return E.Player()
        if name == 'Enemy': return E.Enemy(record['edef'])
        if name in ('Boss', 'NiuBoss', 'ZongBoss', 'OrochiBoss', 'MechaLizardBoss', 'AncientWhaleBoss'):
            boss = CLASSES[name](record['bdef'], self.view.difficulty)
            boss.intro_until = 0
            return boss
        if name == 'BossSignature':
            # Data-only signature has no fonts/surfaces; only allowlisted fields applied below.
            return BossSignature.__new__(BossSignature)
        if name == 'Bullet': return E.Bullet(0,0,config.WEAPON_DEFS[f['weapon_name']],f['weapon_name'])
        if name == 'Coin': return E.Coin(0,0,1)
        if name == 'GiftBox': return E.GiftBox(0)
        if name == 'Particle': return E.Particle(0,0,(255,255,255),0)
        if name == 'Explosion': return E.Explosion(0,0,count=0)
        if name in ('FireWall','IceFloor','MagneticStorm'): return CLASSES[name](0,0)
        if name == 'SkillProjectile': return E.SkillProjectile(0,0,0,0,f['ptype'])
        if name == 'Lightning': return E.Lightning(0,0,[],0)
        if name in ('RadiationLaser','SpinningDarts'): return CLASSES[name](self.view.player)
        if name == 'AbyssProjectile': return CLASSES[name].__new__(CLASSES[name])
        if name == 'BossProjectile': return E.BossProjectile(0,0,0,0)
        if name == 'DragonFireball': return E.DragonFireball(0,0,0)
        if name == 'ReturningAxe':
            # Reference to the restored boss is installed in the second pass.
            return S.ReturningAxe(self.view.boss or E.Boss(config.BOSS_DEFS[6], self.view.difficulty), 1, 0, False)
        if name == 'CrescentWave': return S.CrescentWave(0, 0)
        if name in ('ZongBomb', 'ZongFireball'): return CLASSES[name](0, 0, 0, 0)
        if name == 'ZongReflectBullet': return S.ZongReflectBullet(0, 0)
        if name == 'NiuShieldShard': return S.NiuShieldShard(0, 0, f['index'], f['width'])
        if name == 'NiuFanBullet': return S.NiuFanBullet(0, 0, 0, False)
        if name == 'OrochiFireball': return O.OrochiFireball(0, 0, f['color'], None)
        raise ValueError('Unsupported constructor')

    def apply(self, full_snapshot, local_slot=1):
        snap = full_snapshot.get('world',full_snapshot)
        orientation = full_snapshot.get('orientation', self.orientation)
        if orientation not in WORLD_SIZES:
            raise ValueError('Unknown room orientation')
        if tuple(full_snapshot.get('world_size', WORLD_SIZES[orientation])) != WORLD_SIZES[orientation]:
            raise ValueError('Room geometry does not match orientation')
        size = configure_world(orientation)
        if self.surface.get_size() != size:
            # The client may replace this with its SDL display surface before
            # apply; headless consumers still get a correctly sized renderer.
            self.surface = pygame.Surface(size)
            self.objects.clear()
            self._background_level = None
            self.view.bg_transition_prev = None
        self.orientation = orientation
        config.SCR = self.surface
        match_id = full_snapshot.get('match_id')
        if match_id != self.match_id:
            self.objects.clear()
            self._last_sound_id = -1
            self._music_boss = None
            self.match_id = match_id
            self._background_level = None
            self.view.bg_transition_prev = None
        difficulty = full_snapshot.get('difficulty','medium')
        self.view.difficulty = config.DIFFICULTY_PRESETS.get(difficulty,config.DIFFICULTY_PRESETS['medium'])
        if snap.get('version') != 1: raise ValueError('Unknown visual protocol')
        self.time_ms = snap['time_ms']
        config.campaign_time_ms = self.time_ms
        self.local_slot = local_slot
        records = snap['objects']
        if len(records) > 12000: raise ValueError('Too many visual records')
        live = {}
        for r in records:
            if r['type'] not in SCHEMA: raise ValueError('Unknown visual type')
            if any(k not in SCHEMA[r['type']] for k in r['fields']): raise ValueError('Unknown visual field')
            for attr in ('edef','bdef'):
                if any(k not in DEFINITION_KEYS for k in r.get(attr,{})): raise ValueError('Unknown definition field')
            old = self.objects.get(r['id'])
            same_definition = all(getattr(old, attr, None) == r[attr] for attr in ('edef','bdef') if attr in r)
            live[r['id']] = old if type(old) is CLASSES[r['type']] and same_definition else self._construct(r)
        def value(v):
            if isinstance(v,dict):
                if set(v)=={'ref'}: return live[v['ref']]
                if any(k not in DATA_KEYS for k in v): raise ValueError('Unknown data field')
                return {k:value(item) for k,item in v.items()}
            if isinstance(v,list): return [value(item) for item in v]
            if v is None or type(v) in (bool,str,int,float): return v
            raise ValueError('Non-JSON visual value')
        for r in records:
            obj = live[r['id']]
            old_character = getattr(obj,'character',None)
            # Full frames replace optional fields, rather than retaining a past
            # attack/clone phase when its authoritative attribute disappears.
            for k in SCHEMA[r['type']]:
                if k not in r['fields']:
                    try: delattr(obj, k)
                    except AttributeError: pass
            for attr in ('edef', 'bdef'):
                if attr in r: setattr(obj, attr, value(r[attr]))
            for k,v in r['fields'].items(): setattr(obj,k,value(v))
            if isinstance(obj,E.Boss) and 'intro_until' not in r['fields']:
                obj.intro_until=0
            if r['type']=='OrochiFireball':
                obj.art = _orochi_fire_art(tuple(obj.color) == O.OrochiBoss.FIRE_COLORS[1])
            if r['type']=='Enemy' and obj.is_zongzong:
                grow = obj.w / max(1, obj.base_w)
                size = tuple(max(1, round(v * obj.size_scale * grow)) for v in obj.base_surface_size)
                obj.surface = scale_surface_cached(obj.base_surface, size)
            if r['type']=='Player':
                asset = 'players/player1.png'
                if old_character != obj.character or obj.sprite_asset != asset:
                    factories = {'fire':make_fire_player_surface,'ice':make_ice_player_surface,
                                 'water':make_water_player_surface,'radiation':make_radiation_player_surface}
                    obj.surface = factories[obj.character]() if obj.character in factories else make_player_surface(asset)
                    obj.sprite_asset = asset
                    obj.breath_base = None
        previous_background = None
        if self._background_level is not None and snap['game'].get('current_level') != self._background_level:
            previous = self.view.scrolling_background(self.view.bg.get_size())
            previous_background = (previous if previous is not None else self.view.bg).copy()
        self.objects = live
        for k in COLLECTIONS: setattr(self.view,k,[live[i] for i in snap['collections'].get(k,[])])
        for k,v in snap['game'].items():
            if k not in GAME_FIELDS: raise ValueError('Unknown world field')
            converted = value(v)
            if k in ('water_heal_effects','muzzle_flashes'): converted = [tuple(row) for row in converted]
            setattr(self.view,k,converted)
        for p in snap['players']:
            live[p['id']].slot = p['slot']
            live[p['id']].alive = p['alive']
        self.view.all_players = tuple(live[p['id']] for p in snap['players'])
        if self.view.all_players: self.view.player = next((p for p in self.view.all_players if getattr(p,'slot',1)==local_slot),self.view.all_players[0])
        self.view.boss = live.get(snap.get('boss'))
        self.view.state = GameState.BOSS_FIGHT if self.view.boss else GameState.PLAYING
        level = self.view.current_level
        if level != self._background_level:
            self.view.bg = make_background(level)
            self.view.bg_transition_prev = previous_background if self.time_ms < self.view.bg_transition_until else None
            self._background_level = level
        music = (level, bool(self.view.boss))
        if music != self._music_boss:
            start_music(level,boss=music[1])
            self._music_boss = music
        allowed_sounds = {'shoot_pistol','shoot_rifle','shoot_shotgun','shoot_sniper','hit','boss_hit','niu_shield_hit','niu_axe_impact',
            'coin','buy','error','level_up','game_over','boss_appear','fire_cast','ice_cast','player_hit',
            'water_cast','grenade','lightning','orochi_thunder','storm','laser','laser_hit','dart_cast','dart_burst','kill'}
        for event in full_snapshot.get('events',[]):
            ident = event.get('id')
            if type(ident) is not int or ident <= self._last_sound_id:
                continue
            self._last_sound_id = ident
            if event.get('type') == 'sound' and event.get('key') in allowed_sounds:
                play_sound(event['key'])

    def draw(self):
        configure_world(self.orientation)
        config.SCR = self.surface
        config.campaign_time_ms = self.time_ms
        self.view.draw()
        advance_music()
