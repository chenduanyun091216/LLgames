import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import json
import unittest
from unittest.mock import patch
import pygame
from game_core import config, entities as E
from game_core.game import Game
from game_core.boss_skills import BossSignature
from game_core import special_bosses as S, orochi as O
from online.adapters.snapshot import encode_world
from online.adapters.presentation import Presentation
from online.shared.world import configure_world

class SnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((960,720))
    def world(self):
        config.campaign_time_ms=100
        g=Game()
        g.player.slot=1
        g.player.alive=True
        other=E.Player();other.slot=2;other.alive=True
        g.all_players=(g.player,other)
        g.difficulty=config.DIFFICULTY_PRESETS['medium']
        g.enemies=[E.Enemy(d) for d in config.ENEMY_DEFS]
        for i,e in enumerate(g.enemies): e.x=80+i*60; e.y=150
        g.bullets=[E.Bullet(200,300,w,k) for k,w in config.WEAPON_DEFS.items()]
        g.coins=[E.Coin(400,400,1)]
        g.gift_boxes=[E.GiftBox(450)]
        g.particles=[E.Particle(400,300,(255,100,20))]
        g.explosions=[E.Explosion(500,300,element=k) for k in ('water','fire','ice','radiation')]
        g.fire_walls=[E.FireWall(100,200)]
        g.ice_floors=[E.IceFloor(250,300)]
        g.skill_projectiles=[E.SkillProjectile(320,350,0,2,k,owner=g.player) for k in ('fireball','fire_rocket','grenade','ice_ball')]
        g.magnetic_storms=[E.MagneticStorm(600,300)]
        g.radiation_lasers=[E.RadiationLaser(other)]
        g.radiation_lasers[0].muzzle_effect=3
        g.dart_shields=[E.SpinningDarts(g.player)]
        g.lightnings=[E.Lightning(100,500,g.enemies[:2],1)]
        g.boss_projectiles=[E.BossProjectile(700,200,10,2),E.DragonFireball(750,200,1)]
        g.boss_projectiles[1].lightning_previous=g.boss_projectiles[0]
        g.boss=E.Boss(config.BOSS_DEFS[0],g.difficulty)
        g.boss.y=80
        g.boss.signature=BossSignature(g.boss,g.player,100,100,campaign=True)
        g.warned_boss_shots=[E.BossProjectile(700,250,20,2)]
        g.muzzle_flashes=[(g.player,100,'pistol')]
        g.water_heal_effects=[(other,100)]
        g.skill_flash=(250,300,100,(120,240,255))
        return g
    def test_full_variety_original_draw_and_refs(self):
        g=self.world(); snap=encode_world(g)
        raw=json.dumps(snap,allow_nan=False)
        p=Presentation(pygame.Surface((960,720)))
        p.apply({'world':json.loads(raw)},2);p.draw()
        self.assertIs(p.view.radiation_lasers[0].owner,p.view.all_players[1])
        self.assertEqual(p.view.radiation_lasers[0].muzzle_effect,3)
        self.assertIs(p.view.lightnings[0].targets[0],p.view.enemies[0])
        self.assertIs(p.view.boss_projectiles[1].lightning_previous,p.view.boss_projectiles[0])
        self.assertEqual(len(p.view.bullets),len(config.WEAPON_DEFS))
        self.assertEqual(snap['players'][0]['id'],encode_world(g)['players'][0]['id'])
        self.assertNotIn('surface',raw)
        # View never changes the authoritative world or advances entity physics.
        x=g.bullets[0].x;p.draw();self.assertEqual(g.bullets[0].x,x)
    def test_death_slots_and_character_resources(self):
        g=self.world();p=Presentation(pygame.Surface((960,720)))
        for character in [None,*config.CHARACTER_DEFS]:
            g.player.character=character
            g.player.alive=False
            p.apply(encode_world(g),2);p.draw()
            self.assertEqual(p.view.players[0].slot,2)
        g.all_players[1].alive=False
        p.apply(encode_world(g),1);p.draw()
        self.assertEqual([v.slot for v in p.view.players],[1,2])
    def test_reject_arbitrary_attribute_and_class(self):
        g=self.world();s=encode_world(g);p=Presentation(pygame.Surface((960,720)))
        s['objects'][0]['fields']['__class__']='evil'
        with self.assertRaises(ValueError):p.apply(s)
        s=encode_world(g);s['objects'][0]['type']='eval'
        with self.assertRaises(ValueError):p.apply(s)
    def test_monotonic_ids_and_retained_resources(self):
        g=self.world();s=encode_world(g);p=Presentation(pygame.Surface((960,720)));p.apply(s)
        player=p.view.player;surface=player.surface
        p.apply(encode_world(g));self.assertIs(p.view.player,player);self.assertIs(player.surface,surface)
        previous=max(o['id'] for o in s['objects']);g.coins.append(E.Coin(20,20,1))
        self.assertGreater(encode_world(g)['collections']['coins'][-1],previous)

    def test_match_reset_difficulty_and_audio_dedup(self):
        g=self.world(); p=Presentation(pygame.Surface((960,720)))
        frame={'world':encode_world(g),'match_id':'one','difficulty':'hard',
               'events':[{'id':1,'type':'sound','key':'player_hit'}]}
        with patch('online.adapters.presentation.play_sound') as sound, patch('online.adapters.presentation.start_music') as music, patch('online.adapters.presentation.advance_music') as advance:
            p.apply(frame); player=p.view.player; p.draw();p.apply(frame)
            sound.assert_called_once_with('player_hit')
            music.assert_called_once_with(1,boss=True)
            advance.assert_called_once_with()
            self.assertIs(p.view.difficulty,config.DIFFICULTY_PRESETS['hard'])
            self.assertEqual(p.view.all_players[1].sprite_asset,'players/player1.png')
            frame['match_id']='two';p.apply(frame)
            self.assertIsNot(p.view.player,player)
            self.assertEqual(sound.call_count,2)

    def test_boss_attack_pose_and_late_skill_effects(self):
        g=self.world();p=Presentation(pygame.Surface((960,720)))
        g.boss.signature=None
        g.boss.animation_attack_at=100
        g.ice_floors[0].gaps=[(240,34),(300,20)]
        g.dart_shields[0].release(100)
        for _ in range(4): g.dart_shields[0].update()
        for now in (100,175,250,325,400,475,550,625):
            config.campaign_time_ms=now
            expected=g.boss._body_frame(now)
            self.assertIsNotNone(expected)
            snap=encode_world(g)
            p.apply(snap)
            self.assertEqual(p.view.boss.animation_attack_at,100)
            restored=p.view.boss._body_frame(now)
            self.assertEqual(pygame.image.tostring(expected,'RGBA'),pygame.image.tostring(restored,'RGBA'))
            self.assertEqual(p.view.dart_shields[0]._fly_discs,g.dart_shields[0]._fly_discs)
            self.assertTrue(p.view.dart_shields[0].released)
            self.assertEqual(p.view.ice_floors[0].gaps,[[240,34],[300,20]])
            p.draw()
        # Expired flashes clean up locally without a client-side physics step.
        config.campaign_time_ms=5900
        p.apply(encode_world(g));p.draw()
        self.assertEqual(p.view.muzzle_flashes,[])
        self.assertEqual(p.view.water_heal_effects,[])
        self.assertIsNone(p.view.skill_flash)
        self.assertEqual(len(g.muzzle_flashes),1)

    def campaign_boss(self, level, tier='hard'):
        g=self.world()
        g.current_level=level
        g.difficulty=config.DIFFICULTY_PRESETS[tier]
        g.boss=None
        g._trigger_boss()
        g.boss.entered=True
        g.boss.y=60
        g.boss.intro_until=0
        return g

    def assert_boss_pixels(self, g, p):
        # Original authoritative class vs restored class, same time and pixels.
        import random
        rng=random.getstate()
        left=pygame.Surface((960,720),pygame.SRCALPHA)
        right=pygame.Surface((960,720),pygame.SRCALPHA)
        g.boss.draw(left)
        g.boss._draw_hit_flashes(left, config.game_ticks())
        random.setstate(rng)
        p.view.boss.draw(right)
        p.view.boss._draw_hit_flashes(right, config.game_ticks())
        self.assertEqual(pygame.image.tostring(left,'RGBA'),pygame.image.tostring(right,'RGBA'))
        p.draw()

    def test_all_campaign_bosses_signatures_and_lasers(self):
        p=Presentation(pygame.Surface((960,720)))
        for level in range(1,len(config.LEVEL_CONFIGS)+1):
            g=self.campaign_boss(level)
            for now in (100,450,1300):
                config.campaign_time_ms=now
                g.boss.animation_attack_at=100
                p.apply(json.loads(json.dumps(encode_world(g))))
                self.assertIs(type(p.view.boss),type(g.boss))
                self.assertEqual(p.view.current_level,level)
                self.assert_boss_pixels(g,p)
            if level<=6:
                g.boss.signature=BossSignature(g.boss,g.player,100,300,campaign=True)
                for now in (200,450,800,1300,2200,3500):
                    config.campaign_time_ms=now
                    g.boss.signature.move(g.boss,now,g.player)
                    p.apply(json.loads(json.dumps(encode_world(g))))
                    self.assert_boss_pixels(g,p)
                g.boss.signature=None
                for now in (100,700,1600,2300):
                    config.campaign_time_ms=now
                    g.boss.laser_warning_start=100 if now<1600 else 0
                    g.boss.laser_active_until=3100 if now>=1600 else 0
                    p.apply(encode_world(g));self.assert_boss_pixels(g,p)

    def test_niu_phases_and_special_projectile_refs(self):
        configure_world('landscape')
        g=self.campaign_boss(7);p=Presentation(pygame.Surface((960,720)))
        boss=g.boss
        shots=[S.ReturningAxe(boss,-1,320,True),S.ReturningAxe(boss,1,640,False),
               S.NiuFanBullet(200,300,25,True),S.NiuFanBullet(260,300,-25,False),
               S.CrescentWave(350,300),S.ZongBomb(400,300,0,2),
               S.ZongFireball(500,300,20,2),S.ZongReflectBullet(550,300),
               S.NiuShieldShard(350,400,2,420)]
        shots[5].color='red'
        shots[6].lightning_previous=shots[5]
        g.boss_projectiles=shots
        g.warned_boss_shots=shots[:2]+[shots[4]]
        for fields in ({'running_left':True,'movement_timer':24},
                       {'shield_until':9000}, {'shield_until':0,'shield_break_at':100},
                       {'axe_slam_start':100},
                       {'axe_slam_start':None,'lightning_xs':(200,480,760),
                        'lightning_warning_until':1000,'lightning_until':2400}):
            for k,v in fields.items():setattr(boss,k,v)
            for now in (200,600,1000,1450,2300):
                config.campaign_time_ms=now
                p.apply(json.loads(json.dumps(encode_world(g))))
                self.assertIs(p.view.boss_projectiles[0].boss,p.view.boss)
                self.assertIs(p.view.boss_projectiles[6].lightning_previous,p.view.boss_projectiles[5])
                self.assert_boss_pixels(g,p)
                for source,restored in zip(shots,p.view.boss_projectiles):
                    a=pygame.Surface((960,720),pygame.SRCALPHA);b=a.copy()
                    source.draw(a);restored.draw(b)
                    self.assertEqual(pygame.image.tostring(a,'RGBA'),pygame.image.tostring(b,'RGBA'))

    def test_zong_fusions_dead_clone_revive_and_snow(self):
        g=self.campaign_boss(8);p=Presentation(pygame.Surface((960,720)))
        boss=g.boss
        for mode in (None,'shield','rage'):
            boss.fusion_mode=mode;boss.fusion_started_at=100
            for now in (200,700,1800):
                config.campaign_time_ms=now
                boss.pending_projectiles=boss._fireball_fan()
                boss.crescent_started_at=100 if mode is None else None
                p.apply(json.loads(json.dumps(encode_world(g))))
                self.assert_boss_pixels(g,p)
        boss.fusion_mode=None;boss.crescent_started_at=None
        for hp,revived in ((0,False),(boss.max_hp*.12,True)):
            boss.body_hp[0]=hp;boss.campaign_revived=revived
            boss.next_revive_check=2500;boss.expression_hit_at=1800
            g.player.snow_slow_until=5000
            boss.fusion_warning_mode='shield'
            p.apply(encode_world(g));self.assert_boss_pixels(g,p)
            self.assertEqual(p.view.boss.body_hp[0],hp)

    def test_orochi_every_skill_clone_head_regrowth_and_death(self):
        g=self.campaign_boss(11);p=Presentation(pygame.Surface((960,720)))
        boss=g.boss
        for skill in (*boss.SKILLS,'storm'):
            boss._start_skill(skill,100)
            for now in (200,950,1500,2500,4100):
                config.campaign_time_ms=now
                if skill=='split':
                    boss.split_xy[2]=[420,370];boss.split_hp[0]=0
                    boss.split_charge_until[2]=3000;boss.split_charged[2]=True
                if skill=='storm':
                    if boss.head_hp[0] > 0:
                        boss.hit_by('sniper', boss.head_hp[0], hit_rect=boss.head_rect(0))
                    boss.update(350, 420)
                boss.hit_flashes=[(480,180,now-50)]
                g.boss_projectiles=[O.OrochiFireball(250,350,boss.FIRE_COLORS[0],boss.fire_art),
                                    O.OrochiFireball(400,350,boss.FIRE_COLORS[1],boss.gold_fire_art)]
                p.apply(json.loads(json.dumps(encode_world(g))))
                self.assert_boss_pixels(g,p)
                for source,restored in zip(g.boss_projectiles,p.view.boss_projectiles):
                    self.assertEqual(pygame.image.tostring(source.art,'RGBA'),pygame.image.tostring(restored.art,'RGBA'))
            if skill=='split':
                boss.split_regroup_at=4000
                p.apply(encode_world(g));self.assert_boss_pixels(g,p)
        boss.skill=None;boss.invincible_until=7000
        p.apply(encode_world(g));self.assert_boss_pixels(g,p)
        boss._start_death(4100)
        for now in (4200,4700,5500):
            config.campaign_time_ms=now
            p.apply(encode_world(g));self.assert_boss_pixels(g,p)

    def test_optional_fields_disappear_and_background_music_follow_level(self):
        g=self.campaign_boss(1);p=Presentation(pygame.Surface((960,720)))
        g.boss.animation_attack_at=100
        p.apply(encode_world(g))
        del g.boss.animation_attack_at
        p.apply(encode_world(g))
        self.assertFalse(hasattr(p.view.boss,'animation_attack_at'))
        previous=p.view.bg
        g.current_level=2;g.bg_transition_until=1500
        with patch('online.adapters.presentation.start_music') as music:
            p.apply(encode_world(g));p.draw()
            music.assert_called_once_with(2,boss=True)
            self.assertIsNot(p.view.bg,previous)
            self.assertIsNotNone(p.view.bg_transition_prev)
            p.apply(encode_world(g));self.assertEqual(music.call_count,1)
        config.campaign_time_ms=1600
        p.apply(encode_world(g));p.draw()
        self.assertIsNone(p.view.bg_transition_prev)
        self.assertEqual(p.surface.get_size(),(960,720))

    def test_shared_axe_is_visual_only_and_draw_never_simulates(self):
        from online.adapters.core_adapter import SharedReturningAxe
        g=self.campaign_boss(7)
        axe=SharedReturningAxe(g.boss,-1,350,True)
        axe._online_game=g;axe._player_hits={1:100}
        g.boss_projectiles=[axe]
        p=Presentation(pygame.Surface((960,720)))
        snapshot=encode_world(g)
        raw=json.dumps(snapshot)
        self.assertNotIn('_online_game',raw)
        self.assertNotIn('_player_hits',raw)
        with patch.object(Game,'update',side_effect=AssertionError('client physics')), \
             patch.object(S.NiuBoss,'update',side_effect=AssertionError('client AI')), \
             patch.object(S.ReturningAxe,'update',side_effect=AssertionError('client projectile')):
            p.apply(json.loads(raw));p.draw();p.draw()
        self.assertIs(type(p.view.boss_projectiles[0]),S.ReturningAxe)
        self.assertIs(p.view.boss_projectiles[0].boss,p.view.boss)
        self.assertEqual(json.dumps(snapshot),raw)

if __name__=='__main__': unittest.main()
