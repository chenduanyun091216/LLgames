"""Authority for a two-seat side-scrolling evacuation."""
import math

import pygame

from game_core.run_gun import RunGun


class RunGunRoom:
    def __init__(self, *, start_level=1, **options):
        self.tick = 0
        self.epoch = 0
        self.departed = set()
        self.choice = False
        self.phase = 'playing'
        self.start_stage(0)

    def start_stage(self, stage):
        self.stage = stage
        previous = getattr(self, "actors", ())
        self.actors = [RunGun(stage, player=previous[i].player if previous else None) for i in range(2)]
        self.actors[1].crabs = self.actors[0].crabs
        self.actors[1].objectives = self.actors[0].objectives
        self.actors[1].encounter=self.actors[0].encounter
        for actor in self.actors:actor.party=tuple(self.actors)
        self.retries = 2
        self.rescue = [0,0]
        self.epoch += 1

    def set_input(self, slot, dx, dy, shoot):
        self.actors[slot-1].reset_input()

    def mode_input(self, slot, msg):
        actor = self.actors[slot-1]
        if msg['type']=='mode_action':
            action = msg['action']
            if self.choice and action in ('continue_solo','end_run'):
                self.choice = False
                if action=='end_run':
                    self.phase='lost'
            elif action=='jump' and actor.state=='playing':
                actor.jump_buffer=6
            elif action in ('skill1','skill2','weapon','hero') and actor.state=='playing':
                actor.command({'skill1':pygame.K_u,'skill2':pygame.K_i,'weapon':pygame.K_TAB,'hero':pygame.K_c}[action])
            return
        keys=set()
        for enabled,key in ((msg['x']<-.25,pygame.K_a),(msg['x']>.25,pygame.K_d),
                            (msg['y']<-.25,pygame.K_w),(msg['y']>.25,pygame.K_s),
                            (msg['held']&1,pygame.K_j),(msg['held']&2,pygame.K_l),
                            (msg['held']&4,pygame.K_e),(msg['held']&8,pygame.K_k)):
            if enabled:
                keys.add(key)
        actor.keys=keys
        actor.manual_aim=tuple(msg['aim']) if msg.get('aim') else None

    def action(self,slot,action,key=None):
        return 'unsupported_action'

    def remove_player(self,slot):
        self.departed.add(slot)
        party=tuple(a for i,a in enumerate(self.actors,1) if i not in self.departed)
        for actor in party:actor.party=party
        self.choice = self.phase=='playing'
        self.epoch+=1

    def step(self):
        if self.phase!='playing' or self.choice:
            return
        self.tick+=1
        actors=[a for i,a in enumerate(self.actors,1) if i not in self.departed]
        self.actors[0].encounter.advance(actors)
        marker=max(a.marker_index for a in actors)
        for a in actors:
            if a.state=='playing':
                a.step(cooperative=True)
        alive=[a for a in actors if a.state=='playing']
        if not alive:
            if not self.retries:
                self.phase='lost'
                return
            self.retries-=1
            self.epoch+=1
            for a in actors:
                a.x,a.y=a.checkpoint
                a.hp,a.state=3,'playing'
                a.vx=a.vy=0
                a.safe_until=a.tick+72
                a.bullets.clear()
                a.reset_input()
            return
        winch=max(a.objective_ticks for a in actors)
        leader=max(alive,key=lambda a:a.marker_index)
        for i,a in enumerate(self.actors):
            a.objective_ticks=winch
            if i+1 in self.departed or a.state!='down':
                continue
            near=any(pygame.K_e in other.keys and math.hypot(a.x-other.x,a.y-other.y)<75 for other in alive)
            self.rescue[i]=self.rescue[i]+1 if near else 0
            if self.rescue[i]>=72 or leader.marker_index>marker:
                a.x,a.y=leader.x,leader.y
                a.tick=leader.tick
                a.hp,a.state=1,'playing'
                a.safe_until=a.tick+72
                self.rescue[i]=0
        if len(alive)==2:
            rear,front=sorted(alive,key=lambda a:a.x)
            front.x=min(front.x,rear.x+720)
        self.camera=max(0,min(leader.length-960,(min(a.x for a in alive)+max(a.x for a in alive))/2-480))
        if all(getattr(a,'at_exit',False) and a.x>=a.EXIT for a in alive):
            if self.stage==2:
                self.phase='won'
            else:
                self.start_stage(self.stage+1)

    def snapshot(self):
        players=[dict(slot=i,x=a.x,y=a.y,hp=a.hp,alive=a.state=='playing',
                      character=a.player.character,weapon=a.player.current_weapon,moving=abs(a.vx)>5,
                      cooldowns=a.cast_ready,aim=getattr(a,"aim",None),skill=a.player.animation_skill,cast=a.player.animation_skill_at,shot=a.player.last_shot_time,
                      facing=a.facing,crouching=getattr(a,'crouching',False))
                 for i,a in enumerate(self.actors,1) if i not in self.departed]
        a=self.actors[0]
        return dict(tick=self.tick,phase=self.phase,players=players,world=dict(
            kind='run_gun',stage=self.stage,epoch=self.epoch,choice=self.choice,
            camera=getattr(self,'camera',0),clock=max(p.tick for p in self.actors),
            encounter=a.encounter.snapshot(getattr(self,'camera',0)),crabs=a.crabs,objectives=a.objectives,winch=a.objective_ticks,
            effects=[e for actor in self.actors for e in actor.effects],
            bullets=[b for actor in self.actors for b in actor.bullets]))
