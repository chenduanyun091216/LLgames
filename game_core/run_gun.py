"""Side-view harbor evacuation. Positions use feet-center world coordinates."""
import math

import pygame

from . import config
from .entities import Player
from .run_gun_art import draw_scene
from .run_gun_encounter import Encounter, stage_layout


class RunGun:
    WIDTH, HEIGHT = 960, 540
    STAGES = (
        ('港口货轮', 12000, (3000, 7800), (55, 95, 65), (28, 68, 85)),
        ('钻井平台', 14400, (4000, 9600), (80, 115, 55), (66, 72, 80)),
        ('海底隧道', 16800, (4800, 11200), (35, 90, 70), (24, 59, 72)),
    )

    def __init__(self, stage=0, *, practice=False, player=None, touch=False):
        self.surface = pygame.Surface((self.WIDTH, self.HEIGHT))
        self.player = Player()
        if player is not None:
            self.player.current_weapon = player.current_weapon
            self.player.character = player.character
            self.player.weapon_upgrades = player.weapon_upgrades.copy()
        self.player.last_shot_time = -1000
        self.cast_ready = {}
        self.effects = []
        self.party=(self,)
        self.frozen = {}
        self.stage = stage
        self.practice = practice
        self.title, self.length, self.markers, gaps, self.sky = self.STAGES[stage]
        self.EXIT = self.length - 110
        self.platforms,self.props=stage_layout(stage,self.length)
        self.ramps=[(945,452,1175,400),(1510,465,1780,365)]
        for x in range(2470,self.length-1900,2560):
            self.ramps.append((x+520,474,x+805,373))
        self.on_ramp=False
        self.encounter=Encounter(self)
        self.manual_aim=None
        self.touch_aim={}
        self.x, self.y = 85., 400.
        self.vx = self.vy = self.camera = self.accumulator = 0.
        self.tick = self.next_shot = self.safe_until = 0
        self.hp, self.facing = 3, 1
        self.grounded = True
        self.support = 0
        self.coyote = self.jump_buffer = 0
        self.floor_at = {}
        self.keys = set()
        self.touches = {}
        self.bullets = []
        self.crabs = [[x, 2] for x in (330, 1150, 1660, 2160)]
        self.crabs.extend([x,2] for x in range(2650,self.length-550,770))
        self.state = 'playing'
        self.checkpoint = (85., 400.)
        self.auto = touch
        self.ignore_platform = None
        self.retries = 2
        self.marker_index = 0
        self.objectives = [0,0]
        self.objective_ticks = 0
        self.total_ticks = 0

    def cargo(self):
        if self.stage==1:
            return pygame.Rect(874,333+round(62*math.sin(self.tick/60)),92,22)
        return pygame.Rect(845 + round(50 * math.sin(self.tick / 55)), 320, 90, 20)

    def reset_input(self):
        self.keys.clear()
        self.touches.clear()
        self.jump_buffer = 0
        self.manual_aim=None
        self.touch_aim.clear()

    def buttons(self):
        return {name: pygame.Rect(x, 478, 68, 55) for name, x in
                [('left', 8), ('right', 80), ('down', 152), ('up', 224),
                 ('skill1',296), ('skill2',368), ('weapon',440), ('hero',512), ('use', 668), ('shoot', 740), ('jump', 812), ('pause', 884)]}

    def frame(self, events, elapsed, suspended, font, target=None):
        canvas = config.SCR
        bounds = self.surface.get_rect().fit(canvas.get_rect())
        bounds.center = canvas.get_rect().center
        for event in events:
            if event.type == pygame.WINDOWFOCUSLOST:
                self.reset_input()
                if self.state == 'playing':
                    self.state = 'paused'
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if self.state in ('playing', 'select') and not getattr(event, 'repeat', False):
                    self.command(event.key)
                if self.state == 'select':
                    if event.key in (pygame.K_UP, pygame.K_w, pygame.K_DOWN, pygame.K_s):
                        delta = -1 if event.key in (pygame.K_UP,pygame.K_w) else 1
                        self.selection = (self.selection+delta)%3
                    elif event.key in (pygame.K_LEFT,pygame.K_RIGHT):
                        self.practice = not self.practice
                    elif event.key in (pygame.K_RETURN,pygame.K_KP_ENTER):
                        self.__init__(self.selection,practice=self.practice,player=self.player,touch=self.auto)
                    continue
                if event.key in (pygame.K_p, pygame.K_RETURN):
                    if self.state in ('lost', 'won'):
                        self.choose_stage()
                        continue
                    self.state = 'playing' if self.state == 'paused' else 'paused'
                    self.reset_input()
                if event.key in (pygame.K_SPACE, pygame.K_k) and event.key not in self.keys:
                    self.jump_buffer = 6
                self.keys.add(event.key)
            elif event.type == pygame.KEYUP:
                self.keys.discard(event.key)
            elif event.type in (pygame.FINGERDOWN, pygame.MOUSEBUTTONDOWN):
                if event.type == pygame.MOUSEBUTTONDOWN and getattr(event, 'touch', False):
                    continue
                if event.type == pygame.FINGERDOWN:
                    size = pygame.display.get_surface().get_size()
                    pos = config.window_to_game((event.x * size[0], event.y * size[1]))
                    pointer = event.finger_id
                    self.auto = True
                else:
                    pos = config.window_to_game(event.pos)
                    pointer = 'mouse'
                point = ((pos[0]-bounds.x)*960/bounds.w, (pos[1]-bounds.y)*540/bounds.h)
                if self.state == 'select':
                    for i in range(3):
                        if pygame.Rect(230,155+65*i,500,52).collidepoint(point):
                            self.__init__(i,practice=self.practice,player=self.player,touch=self.auto)
                            break
                    else:
                        if 360<=point[1]<=415:
                            self.practice = not self.practice
                        elif point[1]>420:
                            return False
                    continue
                if self.state in ('lost', 'won'):
                    self.choose_stage()
                    continue
                if self.state == 'paused':
                    if point[0] > 480:
                        return False
                    self.state = 'playing'
                    continue
                for action, rect in self.buttons().items():
                    if rect.collidepoint(point):
                        self.touches[pointer] = action
                        if action=='shoot' and event.type==pygame.FINGERDOWN:
                            self.touch_aim[pointer]=(event.x,event.y)
                        self.command({'skill1': pygame.K_u, 'skill2': pygame.K_i, 'weapon': pygame.K_TAB, 'hero': pygame.K_c}.get(action))
                        if action == 'jump':
                            self.jump_buffer = 6
                        if action == 'pause':
                            self.state = 'paused'
                            self.reset_input()
                        break
            elif event.type == pygame.FINGERMOTION and event.finger_id in self.touch_aim:
                ox,oy=self.touch_aim[event.finger_id]
                v=pygame.Vector2((event.x-ox)*bounds.w,(event.y-oy)*bounds.h)
                if v.length()>8:
                    self.manual_aim=self.octant(v.x,v.y)
            elif event.type == pygame.FINGERUP:
                if self.touch_aim.pop(event.finger_id,None) is not None:self.manual_aim=None
                self.touches.pop(event.finger_id, None)
            elif event.type == pygame.MOUSEBUTTONUP:
                self.touches.pop('mouse', None)
        if suspended:
            self.reset_input()
        if self.state == 'playing' and not suspended:
            self.accumulator += min(elapsed, 4/60)
            while self.accumulator + 1e-10 >= 1/60 and self.state == 'playing':
                self.accumulator -= 1/60
                self.step()
        else:
            self.accumulator = 0
        draw_scene(self, canvas if target is None else target)
        return True

    def choose_stage(self):
        self.selection = self.stage
        self.state = 'select'
        self.reset_input()

    def pressed(self, action, *keys):
        return action in self.touches.values() or bool(self.keys.intersection(keys))

    def crab_rect(self, origin):
        if origin not in self.floor_at:
            self.floor_at[origin] = next(p.top for p in self.platforms if p.left <= origin < p.right)
        ground = self.floor_at[origin]
        return pygame.Rect(origin + round(44*math.sin(self.frozen.get(origin, (self.tick, 0))[0]/42+origin))-19, ground-25, 38, 25)

    @staticmethod
    def octant(x,y):
        a=round(math.atan2(y,x)/(math.pi/4))*(math.pi/4)
        return (round(math.cos(a)),round(math.sin(a)))

    def aim_direction(self):
        if self.manual_aim:return self.manual_aim
        pad=(int(pygame.K_KP6 in self.keys)-int(pygame.K_KP4 in self.keys),
             int(pygame.K_KP2 in self.keys)-int(pygame.K_KP8 in self.keys))
        if any(pad):return pad
        x=int(self.pressed('right',pygame.K_d,pygame.K_RIGHT))-int(self.pressed('left',pygame.K_a,pygame.K_LEFT))
        y=int(self.pressed('down',pygame.K_s,pygame.K_DOWN))-int(self.pressed('up',pygame.K_w,pygame.K_UP))
        return (x or (0 if y else self.facing),y)

    def step(self, *, cooperative=False):
        previous_cargo = self.cargo()
        self.tick += 1
        self.total_ticks += 1
        if not cooperative:self.encounter.advance([self])
        cargo = self.cargo()
        if self.support == len(self.platforms):
            self.x += cargo.x - previous_cargo.x
            self.y += cargo.y - previous_cargo.y
        dx = int(self.pressed('right', pygame.K_d, pygame.K_RIGHT)) - int(self.pressed('left', pygame.K_a, pygame.K_LEFT))
        down = self.pressed('down', pygame.K_s, pygame.K_DOWN)
        up = self.pressed('up', pygame.K_w, pygame.K_UP)
        if dx:
            self.facing = dx
        target = dx * (0 if pygame.K_l in self.keys else 245)
        self.vx += max(-30, min(30, target-self.vx))
        old_x=self.x
        self.x = max(14, min(self.length-14, self.x+self.vx/60))
        for wall in self.encounter.cover:
            if self.y<=wall.top or self.y-(26 if down else 54)>=wall.bottom:continue
            if old_x+14<=wall.left<self.x+14:self.x,self.vx=wall.left-14,0
            elif old_x-14>=wall.right>self.x-14:self.x,self.vx=wall.right+14,0
        if self.encounter.boss['hp']>0:
            self.x=min(self.x,self.EXIT-135)
        if self.grounded:
            self.coyote = 6
        if self.jump_buffer and (self.grounded or self.coyote):
            if down and self.support in (0, 1, 2, 3):
                self.ignore_platform = self.support
            else:
                self.vy = -590
                self.ignore_platform = None
            self.jump_buffer = self.coyote = 0
            self.grounded = False
        old_y = self.y
        if not self.pressed('jump', pygame.K_SPACE, pygame.K_k):
            self.vy = max(-310, self.vy)
        self.vy += 1550/60
        self.y += self.vy/60
        ladder=next(((x,y,h) for kind,x,y,w,h in self.props if kind=='ladder'
                     and x-10<=self.x<=x+w+10 and y-h-2<=old_y<=y+3),None)
        if ladder and (up or down) and not self.pressed('shoot',pygame.K_j):
            _,bottom,height=ladder
            self.vy=0
            self.y=max(bottom-height,min(bottom,old_y+(int(down)-int(up))*2.8))
        self.support = None
        self.grounded = False
        for i, rect in enumerate([*self.platforms, cargo]):
            if i != self.ignore_platform and old_y <= rect.top <= self.y and self.x+14 > rect.left and self.x-14 < rect.right:
                self.y, self.vy = float(rect.top), 0.
                self.grounded, self.support = True, i
                self.ignore_platform = None
        was_on_ramp=self.on_ramp
        self.on_ramp=False
        for left,low,right,high in self.ramps:
            if not left<=self.x<=right or self.vy<0:continue
            height=low+(self.x-left)*(high-low)/(right-left)
            previous_height=low+(old_x-left)*(high-low)/(right-left)
            if (old_y<=previous_height+2 and self.y>=height) or (was_on_ramp and abs(self.y-height)<6):
                self.y,self.vy=height,0
                self.grounded=self.on_ramp=True
                break
        self.jump_buffer = max(0, self.jump_buffer-1)
        self.coyote = max(0, self.coyote-1)
        self.crouching = down and self.grounded
        now = self.tick * 1000 // 60
        if self.auto or self.pressed('shoot', pygame.K_j):
            if self.player.can_shoot(now):
                aim_x,aim_y=self.aim_direction()
                if aim_x:self.facing=aim_x
                bearing = math.atan2(aim_y, aim_x)
                self.aim = (aim_x, aim_y)
                for shot in self.player.shoot(now):
                    angle = bearing + math.radians(shot.angle)
                    self.bullets.append([self.x+aim_x*19, self.y-(19 if self.crouching else 30)+aim_y*12,
                        math.cos(angle)*shot.speed, math.sin(angle)*shot.speed,
                        shot.weapon_name, config.CAMPAIGN_BULLET_DAMAGE[shot.weapon_name]])
        self.advance_effects()
        for bullet in self.bullets[:]:
            previous=bullet[:2]
            bullet[0] += bullet[2]
            bullet[1] += bullet[3]
            blocked=any(abs(w.x-bullet[0])<105 and w.clipline(previous,bullet[:2]) for w in self.encounter.cover)
            if blocked or self.encounter.hit(previous,bullet[:2],bullet[5]):
                self.bullets.remove(bullet)
                continue
            if self.stage == 2:
                core = next((i for i in range(2) if self.objectives[i]<10 and
                             self.core_rect(i).inflate(12,12).clipline(previous,bullet[:2])),None)
                if core is not None:
                    self.objectives[core] = min(10,self.objectives[core]+bullet[5])
                    self.bullets.remove(bullet)
                    continue
            hit = next((c for c in self.crabs if c[1] and abs(c[0]-bullet[0])<66 and self.crab_rect(c[0]).inflate(4,12).clipline(previous,bullet[:2])), None)
            if hit:
                hit[1] = max(0,hit[1]-bullet[5])
            if hit or not (-10 < bullet[1] < 550 and abs(bullet[0]-self.x)<1050):
                self.bullets.remove(bullet)
        body = pygame.Rect(self.x-14, self.y-(26 if self.crouching else 54), 28, 26 if self.crouching else 54)
        fallen = self.y > 590
        if fallen or (self.tick >= self.safe_until and (self.encounter.strikes(body) or any(hp and abs(origin-self.x)<80 and self.crab_rect(origin).colliderect(body) for origin,hp in self.crabs))):
            self.hp -= 1
            self.safe_until = self.tick+72
            if fallen:
                self.x,self.y = self.checkpoint
                self.vx=self.vy=0
                self.ignore_platform=None
            if self.hp <= 0:
                if cooperative:
                    self.state = 'down'
                elif self.retries:
                    self.retries -= 1
                    self.hp=3
                    self.x,self.y=self.checkpoint
                    self.vx=self.vy=0
                    self.bullets.clear()
                    self.ignore_platform=None
                else:
                    self.state='lost'
        if self.grounded and self.marker_index<len(self.markers) and self.x>=self.markers[self.marker_index]:
            self.checkpoint = (self.x,self.y)
            self.marker_index += 1
            self.hp=min(3,self.hp+1)
        self.camera = max(0, min(self.length-960, self.x-345))
        interact = self.pressed('use',pygame.K_e)
        if self.stage==0 and abs(self.x-self.EXIT)<75 and interact:
            self.objective_ticks += 1
        if self.stage==1 and interact:
            for i in range(2):
                if abs(self.x-(self.EXIT-155+i*120))<45:
                    self.objectives[i]=min(24,self.objectives[i]+1)
        ready = (self.objective_ticks>=360 if self.stage==0 else
                 min(self.objectives)>=(24 if self.stage==1 else 10))
        if not self.encounter.boss["hp"] and ready and self.x >= self.EXIT and self.grounded and self.state == 'playing':
            if cooperative:
                self.at_exit = True
            elif self.practice or self.stage==2:
                self.state='won'
            else:
                total=self.total_ticks
                self.__init__(self.stage+1,player=self.player,touch=self.auto)
                self.total_ticks=total

    def core_rect(self,i):
        return pygame.Rect(self.EXIT-25,260+115*i,50,35)

    def command(self, key):
        if key in (pygame.K_c, pygame.K_TAB):
            characters = [None, *config.CHARACTER_DEFS]
            weapons = list(config.WEAPON_DEFS)
            if key == pygame.K_c:
                self.player.character = characters[(characters.index(self.player.character)+1) % len(characters)]
            else:
                self.player.current_weapon = weapons[(weapons.index(self.player.current_weapon)+1) % len(weapons)]
        elif self.state == 'playing' and key in (pygame.K_u, pygame.K_i):
            character = config.CHARACTER_DEFS.get(self.player.character)
            if character:
                skill = character.skills[int(key == pygame.K_i)]
                kind, cooldown = skill.skill_type, skill.cooldown_ms
            elif key == pygame.K_u:
                kind, cooldown = 'fisher_grenade', 4000
            else:
                return
            if self.tick < self.cast_ready.get(kind, 0):
                return
            self.cast_ready[kind] = self.tick + math.ceil(cooldown * .06)
            self.player.animation_skill = kind
            self.player.animation_skill_at = self.tick * 1000 // 60
            if kind == 'water_heal':
                for ally in self.party:
                    if ally.state=='playing':ally.hp=min(3,ally.hp+1)
            elif kind == 'water_boost':
                for ally in self.party:
                    if ally.state=='playing':ally.player.apply_fire_speed_buff('water_boost_until',ally.tick*1000//60,6000)
            angles = {'fireball': (-32,-16,0,16,32), 'ice_balls': (-56,-40,-24,-8,8,24,40,56)}.get(kind,(0,))
            ax,ay=self.aim_direction()
            bearing=math.atan2(ay,ax)
            for angle in angles:
                effect = {'fisher_grenade':'grenade','ice_balls':'ice_ball'}.get(kind,kind)
                if kind=='fireball' and abs(angle)==16:
                    effect='fire_rocket'
                speed = {'grenade':6,'fireball':7,'fire_rocket':7,'ice_ball':6,'ice_floor':3.5}.get(effect,0)
                fx = self.x + (self.facing*95 if kind in ('magnetic_storm','fire_wall') else 0)
                self.effects.append([effect, fx, self.y-22, speed*math.cos(bearing+math.radians(angle)),
                                     speed*math.sin(bearing+math.radians(angle))-(2 if effect=="grenade" else 0), self.tick])

    def advance_effects(self):
        self.frozen = {k:v for k,v in self.frozen.items() if v[1]>self.tick}
        for effect in self.effects[:]:
            kind,x,y,dx,dy,start=effect
            age=self.tick-start
            if kind=='blast':
                if age>=14:self.effects.remove(effect)
                continue
            if kind=="grenade":effect[4]+=.11
            effect[1]+=dx
            effect[2]+=dy
            durations={'grenade':54,'fire_wall':150,'ice_floor':150,'magnetic_storm':180,
                       'water_heal':40,'water_boost':40,'lightning':18}
            expired=age>=durations.get(kind,150)
            radius={'grenade':65,'fire_wall':82,'ice_floor':65,'lightning':280,'magnetic_storm':125}.get(kind,20)
            if kind=='grenade':
                point=effect[1:3]
                ground=dy>=0 and any(p.left<=point[0]<p.right and y<=p.top<=point[1]+5 for p in self.platforms)
                impact=any(u['hp']>0 and self.encounter.box(u).inflate(8,8).collidepoint(point) for u in self.encounter.units)
                if not impact:impact=any(hp and abs(origin-point[0])<70 and self.crab_rect(origin).collidepoint(point) for origin,hp in self.crabs)
                if not (expired or ground or impact):continue
                expired=True
                self.effects.append(['blast',point[0],point[1],0,0,self.tick])
            if kind not in ('water_heal','water_boost'):
                pulse=(age==1 if kind=='lightning' else age%30==0 if kind in ('fire_wall','magnetic_storm','ice_floor') else True)
                if pulse:
                    for u in self.encounter.units:
                        if u['hp']<=0 or abs(u['x']-effect[1])>radius+90:continue
                        rect=self.encounter.box(u)
                        near=(max(rect.left,min(effect[1],rect.right)),max(rect.top,min(effect[2],rect.bottom)))
                        if math.dist(near,effect[1:3])<=radius:
                            u['hp']=max(0,u['hp']-config.SKILL_DAMAGE.get(kind,1))
                            if kind in ('fire_rocket','fireball','ice_ball','grenade'):expired=True
                for crab in self.crabs:
                    if not crab[1] or abs(crab[0]-effect[1])>radius+65:
                        continue
                    rect=self.crab_rect(crab[0])
                    if math.dist(rect.center,effect[1:3])>radius:
                        continue
                    if kind=='ice_floor':
                        self.frozen.setdefault(crab[0], (self.tick,self.tick+120))
                    elif kind in ('fire_wall','magnetic_storm') and age%30:
                        continue
                    elif kind=='lightning' and age>1:
                        continue
                    else:
                        crab[1]=max(0,crab[1]-config.SKILL_DAMAGE.get(kind,1))
                    if kind in ('fireball','fire_rocket','ice_ball','grenade'):
                        expired=True
            if expired:
                self.effects.remove(effect)
