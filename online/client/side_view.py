"""Local controls and rendering for the authoritative platform game."""
from time import monotonic
import pygame

from game_core import config
from game_core.run_gun import RunGun
from game_core.run_gun_art import draw_scene


class SideView:
    def __init__(self):
        self.actor=None
        self.context=None
        self.last_input=None
        self.sent=0

    def frame(self,lan,game,state,events,away,window):
        world=state['world']
        context=state['match_id'],world['epoch']
        if self.context!=context:
            self.actor=RunGun(world['stage'],touch=game.mobile_web)
            self.context=context
            self.last_input=None
        a=self.actor
        me=next(p for p in state['players'] if p['slot']==int(lan.transport.slot))
        a.x,a.y,a.hp=me['x'],me['y'],me['hp']
        a.facing,a.crouching=me['facing'],me['crouching']
        a.camera,a.tick=world['camera'],world['clock']
        a.bullets,a.crabs=world['bullets'],world['crabs']
        a.objectives,a.objective_ticks=world['objectives'],world['winch']
        a.player.character=me.get('character')
        a.player.current_weapon=me.get('weapon','pistol')
        a.player.animation_skill=me.get('skill')
        a.player.animation_skill_at=me.get('cast')
        a.player.last_shot_time=me.get('shot',-1000)
        a.vx=245 if me.get('moving') else 0
        a.cast_ready=me.get('cooldowns',{})
        a.aim=me.get('aim')
        a.effects=world.get('effects',[])
        if 'encounter' in world:
            for key in ('units','boss','shots','zones','clock'):
                setattr(a.encounter,key,world['encounter'][key])
        a.state='playing'
        def action(name):
            lan.transport.send(dict(type='mode_action',epoch=world['epoch'],action=name))
        bounds=a.surface.get_rect().fit(config.SCR.get_rect())
        bounds.center=config.SCR.get_rect().center
        for e in events:
            key=None
            if e.type==pygame.KEYDOWN:
                key=e.key
            elif e.type in (pygame.FINGERDOWN,pygame.MOUSEBUTTONDOWN):
                if e.type==pygame.MOUSEBUTTONDOWN and getattr(e,'touch',False):continue
                pos=(game.mobile_controls.event_position(e) if e.type==pygame.FINGERDOWN
                     else config.window_to_game(e.pos))
                pt=((pos[0]-bounds.x)*960/bounds.w,(pos[1]-bounds.y)*540/bounds.h)
                if state['phase']!='playing':key=pygame.K_ESCAPE
                elif world['choice']:key=pygame.K_RETURN if pt[0]<480 else pygame.K_ESCAPE
                else:
                    for name,r in a.buttons().items():
                        if r.collidepoint(pt):
                            a.touches[getattr(e,'finger_id','mouse')]=name
                            if name=='shoot' and e.type==pygame.FINGERDOWN:a.touch_aim[e.finger_id]=(e.x,e.y)
                            if name in ('hero','weapon','skill1','skill2'):action(name)
                            if name=='jump':key=pygame.K_k
                            elif name=='pause':key=pygame.K_p
                    a.auto=e.type==pygame.FINGERDOWN
            elif e.type==pygame.FINGERMOTION and e.finger_id in a.touch_aim:
                ox,oy=a.touch_aim[e.finger_id]
                if abs(e.x-ox)+abs(e.y-oy)>.015:a.manual_aim=a.octant((e.x-ox)*bounds.w,(e.y-oy)*bounds.h)
            elif e.type in (pygame.FINGERUP,pygame.MOUSEBUTTONUP):
                if a.touch_aim.pop(getattr(e,'finger_id','mouse'),None) is not None:a.manual_aim=None
                a.touches.pop(getattr(e,'finger_id','mouse'),None)
            commands={pygame.K_c:'hero',pygame.K_TAB:'weapon',pygame.K_u:'skill1',pygame.K_i:'skill2'}
            if key in commands and not state['paused'] and not getattr(e,'repeat',False):
                action(commands[key])
            if key==pygame.K_ESCAPE or (key==pygame.K_RETURN and state['phase']!='playing'):
                lan.leave()
                return
            if key==pygame.K_RETURN and world['choice']:action('continue_solo')
            if key==pygame.K_p:lan.send('unpause' if state['paused'] else 'pause')
            if key in (pygame.K_SPACE,pygame.K_k) and not state['paused'] and not getattr(e,'repeat',False):action('jump')
        keys=pygame.key.get_pressed()
        a.keys={k for k in (pygame.K_a,pygame.K_d,pygame.K_w,pygame.K_s,pygame.K_LEFT,pygame.K_RIGHT,
                            pygame.K_DOWN,pygame.K_UP,pygame.K_j,pygame.K_e,pygame.K_l,pygame.K_SPACE,pygame.K_k,pygame.K_KP2,pygame.K_KP4,pygame.K_KP6,pygame.K_KP8) if keys[k]}
        inputs=(int(a.pressed('right',pygame.K_d,pygame.K_RIGHT))-int(a.pressed('left',pygame.K_a,pygame.K_LEFT)),
                int(a.pressed('down',pygame.K_s,pygame.K_DOWN))-int(a.pressed('up',pygame.K_w,pygame.K_UP)),
                int(a.auto or a.pressed('shoot',pygame.K_j))+2*int(pygame.K_l in a.keys)+
                4*int(a.pressed('use',pygame.K_e))+8*int(a.pressed('jump',pygame.K_k,pygame.K_SPACE)))
        inputs=(*inputs,a.aim_direction())
        if state['paused'] or away:
            a.reset_input()
            self.last_input=None
        elif state['phase']=='playing' and (inputs!=self.last_input or monotonic()-self.sent>.05):
            lan.transport.send(dict(type='mode_input',epoch=world['epoch'],x=inputs[0],y=inputs[1],held=inputs[2],aim=list(inputs[3])))
            self.sent=monotonic()
            self.last_input=inputs
        notice=({'won':'撤离成功　回车返回','lost':'撤离失败　回车返回'}.get(state['phase']) or
                ('队友离开　回车或点左侧继续　Esc 或点右侧退出' if world['choice'] else
                 ('已暂停　P 继续' if state['paused'] else '')))
        target=window.subsurface((config.VIEW_OFFSET,config.VIEW_SIZE))
        draw_scene(a,target,teammates=[p for p in state['players'] if p['slot']!=me['slot']],notice=notice)
        lan.drawn_to_window=True
