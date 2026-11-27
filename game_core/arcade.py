"""Input and menus shared by independent arcade modes."""
import pygame

from . import config


def viewport(surface):
    target=surface.get_rect().fit(config.SCR.get_rect())
    target.center=config.SCR.get_rect().center
    return target


def pointer(event,surface,*,motion=False):
    if event.type==pygame.FINGERDOWN or (motion and event.type==pygame.FINGERMOTION):
        w,h=pygame.display.get_surface().get_size()
        point=config.window_to_game((w*event.x,h*event.y))
    elif event.type==pygame.MOUSEBUTTONDOWN and not getattr(event,'touch',False):
        point=config.window_to_game(event.pos)
    else:
        return None
    r=viewport(surface)
    return ((point[0]-r.x)*surface.get_width()/r.w,(point[1]-r.y)*surface.get_height()/r.h)


def present(surface):
    r=viewport(surface)
    config.SCR.fill((7,22,32))
    config.SCR.blit(pygame.transform.scale(surface,r.size),r)


class ArcadeMenu:
    def __init__(self, title, options):
        self.title=title
        self.options=options
        self.index=0
        self.surface=pygame.Surface((800,540))

    def frame(self,events,elapsed,suspended,font):
        canvas=self.surface
        canvas.fill((13,37,53))
        canvas.blit(font.render(self.title,True,(226,239,227)),(75,36))
        rects=[pygame.Rect(75,90+i*54,650,46) for i in range(len(self.options))]
        for i,((label,callback),r) in enumerate(zip(self.options,rects)):
            pygame.draw.rect(canvas,(44,107,117) if i==self.index else (29,65,82),r,border_radius=5)
            canvas.blit(font.render(label,True,(232,245,237)),(r.x+16,r.y+10))
        present(canvas)
        for e in events:
            pos=pointer(e,canvas)
            if pos is not None:
                picked=next((i for i,r in enumerate(rects) if r.collidepoint(pos)),None)
                if picked is not None:
                    self.index = picked
                    self.options[picked][1]()
                    break
            elif e.type==pygame.KEYDOWN:
                if e.key==pygame.K_ESCAPE:return False
                if e.key in (pygame.K_UP,pygame.K_w):self.index=(self.index-1)%len(rects)
                if e.key in (pygame.K_DOWN,pygame.K_s):self.index=(self.index+1)%len(rects)
                if e.key in (pygame.K_RETURN,pygame.K_KP_ENTER):
                    self.options[self.index][1]()
                    break
        return True


class SoloMode:
    def __init__(self,size=(800,540)):
        self.surface=pygame.Surface(size)
        self.keys=set()
        self.fingers={}
        self.paused=False
        self.ended=False
        self.accumulator=0

    def held(self,*keys):
        return any(k in self.keys or k in self.fingers.values() for k in keys)

    def controls(self):
        controls=[('左',pygame.K_a),('右',pygame.K_d),('上',pygame.K_w),('下',pygame.K_s),*self.actions,('暂停',pygame.K_p)]
        width=self.surface.get_width()//len(controls)
        return [(label,key,pygame.Rect(i*width,490,width-3,46)) for i,(label,key) in enumerate(controls)]

    def frame(self,events,elapsed,suspended,font):
        for e in events:
            key=None
            if e.type==pygame.WINDOWFOCUSLOST:
                self.paused=True
                self.keys.clear()
                self.fingers.clear()
            elif e.type==pygame.KEYDOWN:
                if e.key not in self.keys:key=e.key
                self.keys.add(e.key)
            elif e.type==pygame.KEYUP:self.keys.discard(e.key)
            elif e.type in (pygame.FINGERUP,pygame.MOUSEBUTTONUP):
                self.fingers.pop(getattr(e,'finger_id','mouse'),None)
            else:
                pos=pointer(e,self.surface)
                if pos:
                    if self.ended:return False
                    if self.paused:
                        if pos[0]>self.surface.get_width()/2:return False
                        key=pygame.K_p
                    else:
                        key=next((k for _,k,r in self.controls() if r.collidepoint(pos)),None)
                        if key:self.fingers[getattr(e,'finger_id','mouse')]=key
            if key==pygame.K_ESCAPE or self.ended and key==pygame.K_RETURN:
                return False
            if key==pygame.K_p:
                self.paused=not self.paused
                self.fingers.clear()
            elif key and not self.ended and not self.paused:self.action(key)
        if suspended or self.paused or self.ended:
            self.accumulator=0
            if suspended:
                self.keys.clear()
                self.fingers.clear()
        else:
            self.accumulator+=min(elapsed,4/60)
            while self.accumulator+1e-10>=1/60 and not self.ended:
                self.accumulator-=1/60
                self.step()
        self.draw(font)
        for label,key,r in self.controls():
            pygame.draw.rect(self.surface,(28,60,76),r,border_radius=6)
            self.surface.blit(font.render(label,True,(234,242,222)),(r.x+8,r.y+10))
        if self.paused or self.ended:
            msg=self.result+'　回车或点屏幕返回' if self.ended else '已暂停　左侧继续　右侧退出'
            self.surface.blit(font.render(msg,True,'white',(20,43,59)),(40,195))
        present(self.surface)
        return True


class ModeHub:
    def __init__(self,game):
        self.game=game
        self.closed=False
        self.tide_best = {}
        self.tide_intro = False
        self.home()

    def home(self):
        self.menu=ArcadeMenu('玩法大厅',[
            ('横版突围　·　单人或双人合作',self.run_gun),
            ('深潜寻宝　·　单人探索',self.deep_dive),
            ('今天我当 Boss　·　双人换边对决',self.boss_duel),
            ('双人潜艇快递　·　双人合作',self.sub_courier),
            ('潮汐竞速　·　单人计时或双人竞速',self.tide_race),
            ('返回首页',self.exit)])
        self.active=self.menu

    def restore_home(self):
        self.active = self.menu

    def exit(self):
        self.closed=True

    def run_gun(self):
        from .run_gun import RunGun
        def solo():
            self.active=RunGun(player=self.game.player,touch=self.game.mobile_web)
            self.active.choose_stage()
        self.choose_party('横版突围','run_gun',solo)

    def tide_race(self):
        self.choose_party('潮汐竞速', 'tide_race', self.tide_tracks)

    def tide_tracks(self):
        from .modes.tide_race import content
        from .modes.tide_race_ui import TideRaceMode

        def select(track):
            self.active = TideRaceMode(track, self.game, self.tide_tracks,
                                       show_tip=track == 'lighthouse' and not self.tide_intro,
                                       session=self.tide_best)
            if track == 'lighthouse':
                self.tide_intro = True

        tracks = content()['tracks']
        self.active = ArcadeMenu('潮汐竞速 · 选择赛道', [
            *[(item['name'], lambda track=track: select(track)) for track, item in tracks.items()],
            ('返回玩法大厅', self.restore_home)])

    def sub_courier(self):
        self.choose_party('双人潜艇快递', 'sub_courier')

    def deep_dive(self):
        from .modes.deep_dive_ui import DeepDiveMode
        self.active = DeepDiveMode(self.game.player, touch=self.game.mobile_web)

    def choose_party(self,title,mode,solo=None):
        lan=getattr(self.game,'arcade_lan',None)
        choices=[('单人出发',solo)] if solo else []
        if lan:
            def create():
                lan.requested_mode=mode
                lan.start_room('create')
                self.closed=True
            def join():
                lan.join_form()
                self.closed=True
            choices.extend([('创建双人房间',create),('加入房间',join)])
        choices.append(('返回玩法大厅',self.restore_home))
        self.active=ArcadeMenu(title,choices)

    def boss_duel(self):
        self.choose_party('今天我当 Boss', 'boss_duel')

    def frame(self,events,elapsed,suspended,font,target=None):
        current=self.active
        from .run_gun import RunGun
        from .modes.deep_dive_ui import DeepDiveMode
        from .modes.tide_race_ui import TideRaceMode
        self.direct = isinstance(current, (RunGun, DeepDiveMode, TideRaceMode)) and target is not None
        args = (target,) if self.direct else ()
        if not current.frame(events,elapsed,suspended,font,*args):
            if current is self.menu:return False
            self.restore_home()
        return not self.closed
