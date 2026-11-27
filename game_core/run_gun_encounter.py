"""Stage landmarks and shared hostile simulation for the side-scrolling campaign."""
import math
import pygame

BOSSES = (
    ('铁钳船长','boss_crab',24),
    ('熔炉守卫','boss_mecha_lizard',32),
    ('深渊巨鲸','boss_ancient_whale',40),
)

def stage_layout(stage,length):
    # Routes are authored as linked silhouettes: cargo stacks, lift shafts, tunnel galleries.
    platforms = [(0,400,475,45),(580,345,285,32),(970,400,420,35),(1510,365,340,35),
                 (1950,400,555,45),(400,485,2120,55),(1800,440,130,18)]
    props = [('crate',356,400,65,58),('ladder',710,485,38,140),
             ('crane',140,400,190,170),('ladder',1750,485,38,120)]
    if stage==1:
        platforms[1]=(565,326,285,28)
        props[0]=('lift',385,400,82,125)
        props[2]=('crane',55,400,230,210)
    elif stage==2:
        platforms[1]=(578,346,315,24)
        props[0]=('tunnel',310,400,250,145)
        props[2]=('tunnel',40,400,245,155)
    templates = (
        (((0,404,310),(330,351,235),(575,308,190),(760,361,235),(991,395,290)),
         ((0,394,245),(260,337,210),(500,286,255),(770,330,210),(996,390,285))),
        (((0,386,242),(282,322,245),(564,266,196),(795,333,185),(1005,390,280)),
         ((0,389,260),(304,338,198),(550,304,210),(785,285,170),(985,360,300))),
        (((0,392,225),(255,333,205),(490,276,245),(762,308,214),(992,363,295)),
         ((0,383,290),(335,320,215),(575,277,170),(775,335,210),(1010,395,278))),
    )
    for section,x in enumerate(range(2470,length-1150,1280)):
        route=templates[stage][section%2]
        platforms.extend((x+dx,y,w,26) for dx,y,w in route)
        platforms.append((x,474,1282,43))
        kind=('crane','lift','tunnel')[stage]
        props.extend([(kind,x+80,route[0][1],220,155),('ladder',x+route[2][0]+65,474,38,474-route[2][1])])
        if stage==0:
            props.append(('crate',x+55,route[0][1],74,52))
    last=platforms[-1][0] if len(platforms)>7 else 2000
    platforms.extend([(last,474,length-last+5,46),(length-1200,400,1210,45)])
    props.extend([('ladder',length-1065,474,38,74),('lift',length-160,400,120,155)])
    for kind,x,y,w,h in props:
        if kind=='crate':
            platforms.append((x,y-h,w,9))
    return [pygame.Rect(*r) for r in platforms],props


class Encounter:
    def __init__(self,game):
        self.units=[]
        self.shots=[]
        self.zones=[]
        self.cover=[pygame.Rect(x,y-h,w,h) for kind,x,y,w,h in game.props if kind=="crate"]
        self.clock=0
        self.stage=game.stage
        self.exit=game.EXIT
        for i,x in enumerate([465,765,1310,1980,*range(2650,game.length-1200,590)]):
            kind=('turret','jelly','sentry')[i%3]
            ground=next((p.top for p in game.platforms if p.left<=x<p.right),400)
            hp={'turret':4,'jelly':2,'sentry':3}[kind]
            high_mount=kind=='turret' and game.stage==2 and i%2==0
            y=ground-(124 if high_mount else 26 if kind!='jelly' else 108)
            self.add(kind,x,y,hp)
            if high_mount:
                game.platforms.append(pygame.Rect(x-39,y+24,78,14))
        self.boss=self.add('boss',game.EXIT-30,360,BOSSES[game.stage][2])

    def add(self,kind,x,y,hp):
        unit=dict(kind=kind,x=x,y=y,home_y=y,hp=hp,max_hp=hp,next=0,fire=0,
                  dx=-1.,dy=0.,attack=0,facing=-1)
        self.units.append(unit)
        return unit

    @staticmethod
    def box(u):
        w,h={'turret':(54,47),'jelly':(48,49),'sentry':(46,52),'boss':(143,145)}[u['kind']]
        return pygame.Rect(u['x']-w/2,u['y']-h/2,w,h)

    def advance(self,actors):
        self.clock+=1
        alive=[a for a in actors if a.state=='playing']
        if not alive:return
        for i,u in enumerate(self.units):
            if u['hp']<=0:continue
            target=min(alive,key=lambda a:abs(a.x-u['x']))
            if abs(target.x-u['x'])>780:continue
            if u['kind']=='jelly':
                u['y']=u['home_y']+math.sin(self.clock/48+i)*38
            u['facing']=1 if target.x>u['x'] else -1
            if u['fire']:
                if self.clock>=u['fire']:
                    self.fire(u)
                    u['fire']=0
            elif self.clock>=u['next'] and abs(target.x-u['x'])<570:
                dx,dy=target.x-u['x'],target.y-26-u['y']
                length=max(1,math.hypot(dx,dy))
                u['dx'],u['dy']=dx/length,dy/length
                u['attack']+=1
                if u['kind']=='boss' and u['attack']%2==0:
                    kind=('shockwave','drill','geyser')[self.stage]
                    anchors=(target.x,) if kind!='geyser' else (target.x-86,target.x+86)
                    for x in anchors:
                        self.zones.append([kind,u['x'] if kind=='shockwave' else x,0,
                                           self.clock+66,self.clock+(190 if kind=='shockwave' else 103)])
                u['fire']=self.clock+(55 if u['kind']=='boss' else 42)
                u['next']=self.clock+(156 if u['kind']=='boss' else 225+i%3*20)
        for z in self.zones[:]:
            if self.clock>=z[4]:
                self.zones.remove(z)
            elif z[0]=='shockwave' and self.clock>=z[3]:
                z[1]-=5
        for b in self.shots[:]:
            b[0]+=b[2]
            b[1]+=b[3]
            if self.clock>=b[4] or any(r.collidepoint(b[:2]) for r in self.cover if abs(r.x-b[0])<120) or not -30<b[1]<575 or all(abs(a.x-b[0])>1040 for a in alive):
                self.shots.remove(b)

    def fire(self,u):
        boss=u['kind']=='boss'
        fans=([(-18,0,18),(-10,10)][u['attack']%2] if boss else [0])
        if u['kind']=='turret' and self.stage==1:fans=(-8,8)
        if u['kind']=='turret' and self.stage==2:fans=(-12,0,12)
        if boss and self.stage==1:fans=(-27,-9,9,27)
        if boss and self.stage==2:fans=(-35,-18,0,18,35)
        speed=3.6 if boss else 2.6
        bearing=math.atan2(u['dy'],u['dx'])
        for angle in fans:
            dx=math.cos(bearing+math.radians(angle))
            dy=math.sin(bearing+math.radians(angle))
            self.shots.append([u['x']+dx*22,u['y']+dy*16,dx*speed,dy*speed,self.clock+240,int(boss)])

    def hit(self,start,end,damage):
        for u in self.units:
            if u['hp']>0 and abs(u['x']-end[0])<96 and self.box(u).clipline(start,end):
                u['hp']=max(0,u['hp']-damage)
                return True
        return False

    def strikes(self,body):
        for b in self.shots[:]:
            if body.inflate(7,7).collidepoint(b[:2]):
                self.shots.remove(b)
                return True
        for kind,x,_,start,end in self.zones:
            if self.clock<start:continue
            area=pygame.Rect(x-21,378 if kind=='shockwave' else 155,42,115 if kind=='shockwave' else 335)
            if area.colliderect(body):return True
        return any(u['hp']>0 and abs(u['x']-body.centerx)<95 and self.box(u).colliderect(body) for u in self.units)

    def snapshot(self,camera):
        return {'units':[u for u in self.units if abs(u['x']-camera-480)<740],
                'boss':self.boss,'zones':self.zones,'shots':self.shots,'clock':self.clock}
