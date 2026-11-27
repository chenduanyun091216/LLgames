"""Paint the side-view world directly into the selected output resolution."""
import math
import sys
from functools import lru_cache

import pygame

from . import config
from .asset_loader import cover_image_asset, image_asset, image_variant, scale_surface_cached
from .entities import FireWall, IceFloor, MagneticStorm, SkillProjectile
from .render import Draw, RenderSurface
from .run_gun_encounter import BOSSES

WEAPON_ART = {'pistol':'pistol','rifle':'rifle','shotgun':'shortgun','sniper':'awm'}
BACKDROPS = ('bg3','bg9','trench-boss-wide')
DECK_COLORS = (((98,61,45),(189,133,78)), ((49,68,82),(162,182,173)),
               ((32,69,83),(103,171,168)))


@lru_cache(maxsize=2)
def backdrop(stage,size,variant):
    stem = 'backgrounds/' + BACKDROPS[stage]
    for ext in ('jpg','png'):
        art = cover_image_asset(stem+'.'+ext,size,variant=variant)
        if art is not None:
            return art.convert()
    return None


@lru_cache(maxsize=32)
def font_at(size,bold):
    return config.make_font(size,bold)


@lru_cache(maxsize=128)
def flipped(image):
    return pygame.transform.flip(image,True,False)


@lru_cache(maxsize=128)
def aimed_gun(image, width, height, flip, angle):
    gun = scale_surface_cached(image,(width,height))
    if flip:
        gun=flipped(gun)
    return pygame.transform.rotate(gun,angle) if angle else gun


def draw_scene(a,target,*,teammates=(),notice=''):
    viewport = pygame.Rect(0,0,960,540).fit(target.get_rect())
    viewport.center = target.get_rect().center
    if viewport.size != target.get_size():
        target.fill((6,22,34))
    pixels = target.subsurface(viewport)
    s = RenderSurface(pixels,(960,540),viewport.size,(0,0),desktop_ui=True)
    r,line,circle=Draw.rect,Draw.line,Draw.circle
    def label(txt,x,y,size=15,color=(238,248,243),bold=False):
        face=font_at(max(1,round(size*s.scale)),bold)
        pixels.blit(face.render(txt,True,color),s.point((x,y)))
    def sprite(art,x,y,w,h,reverse=False):
        if art is None:return
        img=scale_surface_cached(art,(s.length(w),s.length(h)))
        pixels.blit(flipped(img) if reverse else img,img.get_rect(midbottom=s.point((x,y))))
    bg=backdrop(a.stage,viewport.size,image_variant())
    if bg is None:pixels.fill((16,69,86))
    else:pixels.blit(bg,(0,0))
    t=a.tick
    cam=int(a.camera)
    for i in range(26):
        x=(i*137-cam*.16+4*math.sin(t/100+i))%960
        y=(i*83-t*(.16+i%3*.08))%540
        circle(s,(134,204,205),(x,y),1+i%3,1)
    base,lip=DECK_COLORS[a.stage]
    for kind,wx,wy,w,h in a.props:
        x=wx-cam
        if x+w<0 or x>960:continue
        prop=image_asset('side_view/'+kind+'.png')
        if prop is not None:
            sprite(prop,x+w/2,wy,w,h)
        elif kind=='ladder':
            for col in (x+5,x+w-5):line(s,(177,148,86),(col,wy-h),(col,wy),4)
            for rung in range(wy-h,wy,14):line(s,(168,144,94),(x+6,rung),(x+w-6,rung),3)
        elif kind=='crane':
            line(s,(35,66,77),(x+w*.25,wy),(x+w*.25,wy-h),9)
            Draw.polygon(s,(179,130,65),[(x+w*.17,wy-h+8),(x+w*.92,wy-h+36),(x+w*.22,wy-h-4)])
            line(s,lip,(x+w*.9,wy-h+35),(x+w*.9,wy-26),2)
            Draw.arc(s,lip,(x+w*.9-6,wy-32,12,16),math.pi,2*math.pi,3)
        elif kind=='lift':
            for col in (x+4,x+w-4):line(s,lip,(col,wy),(col,wy-h),4)
            line(s,base,(x,wy-h),(x+w,wy-h),7)
        elif kind=='tunnel':
            Draw.arc(s,(70,151,156),(x,wy-h,w,h*2),0,math.pi,8)
        elif kind=='crate':
            sprite(image_asset('ui/gift_box.png'),x+w/2,wy,w,h)
    for platform in [*a.platforms,a.cargo()]:
        x,y,w,h=platform.move(-cam,0)
        if x+w<0 or x>960:continue
        deck=image_asset('side_view/dock.png')
        if deck is not None:
            count=max(1,round(w/(h*6)))
            for i in range(count):
                start=round(i*w/count)
                end=round((i+1)*w/count)
                if x+end>=0 and x+start<=960:
                    sprite(deck,x+(start+end)/2,y+h,end-start,h)
        else:
            r(s,base,(x,y,w,h))
            line(s,lip,(x,y),(x+w,y),2)
    for left,low,right,high in a.ramps:
        if right<cam or left>cam+960:continue
        span=right-left
        line(s,(26,54,65),(left-cam,low+9),(right-cam,high+9),9)
        line(s,(200,161,104),(left-cam,low),(right-cam,high),5)
        for dx in range(4,span,23):
            y=low+dx*(high-low)/span
            line(s,(119,106,88),(left-cam+dx,y+1),(left-cam+dx-3,y+9),3)
    for origin,hp in a.crabs:
        if hp and cam-70<origin<cam+1030:
            rect=a.crab_rect(origin)
            sprite(image_asset('enemies/enemy_crab.png'),rect.centerx-cam,rect.bottom+3,48,37)
    e=a.encounter
    boss_name,boss_asset,boss_max=BOSSES[a.stage]
    for u in e.units:
        x,y=u['x']-cam,u['y']
        if not u['hp'] or not -110<x<1070:continue
        kind=u['kind']
        names={'turret':'side_view/'+('turret_light.png' if a.stage==0 else 'turret.png'),'jelly':'enemies/enemy_jellyfish.png',
               'sentry':'enemies/enemy_mecha_crab.png','boss':f'bosses/{boss_asset}.png'}
        art=image_asset(names[kind]) or image_asset('enemies/enemy_mecha_crab.png')
        hitbox=e.box(u)
        sprite(art,x,hitbox.bottom,hitbox.w*1.2,hitbox.h*1.15,u['facing']>0)
        if kind=='turret' and image_asset('side_view/turret.png') is None:
            gun=image_asset('weapons/weapon_awm.png')
            sprite(gun,x+u['facing']*20,y+1,52,16,u['facing']>0)
        if kind=='turret':
            col=(255,168,76) if not u['fire'] else (255,73,65)
            circle(s,col,(x+u['facing']*12,y-5),3)
            if u['hp']<u['max_hp']:
                r(s,(37,55,64),(x-17,y-35,34,3))
                r(s,(245,153,80),(x-17,y-35,34*u['hp']/u['max_hp'],3))
        if u['fire']:
            extent=95 if kind=='boss' else 61
            end=(x+extent*u['dx'],y+extent*u['dy'])
            line(s,(250,132,84),(x,y),end,2)
            circle(s,(255,208,115),end,5,1)
        if kind=='boss':
            r(s,(27,36,53),(310,15,340,45),border_radius=6)
            label(boss_name,324,19,15,(255,219,158),True)
            r(s,(85,55,65),(325,46,310,5))
            r(s,(242,131,79),(325,46,310*u['hp']/boss_max,5))
    for kind,x,_,start,end in e.zones:
        x-=cam
        if e.clock<start:
            line(s,(255,178,100),(x-21,397),(x+21,397),4)
            label({'shockwave':'跃过冲击波','drill':'避开钻击','geyser':'离开水柱'}[kind],x-32,340,12)
        elif kind=='shockwave':
            sprite(image_asset('effects/whale_tidal_crescent.png'),x,473,53,99)
        else:
            effect='whale_rune_geyser' if kind=='geyser' else 'mecha_plasma_rail'
            sprite(image_asset('effects/'+effect+'.png'),x,484,50,318)
    for bx,by,dx,dy,_,strong in e.shots:
        line(s,(247,98,83),(bx-cam-dx*3,by-dy*3),(bx-cam,by),5)
        circle(s,(255,207,123),(bx-cam,by),6 if strong else 4)
        circle(s,(255,249,209),(bx-cam,by),2)
    def hero(x,y,character,facing,low,moving,weapon,skill=None,cast=None,shot=-1000,aim=None):
        now=t*1000//60
        running=moving and not low and (t//8)%2==0
        casting=cast is not None and 0<=now-cast<380
        pose='low' if low else 'cast' if casting else 'run' if running else 'idle'
        art=image_asset(f"side_view/{character or 'fisher'}_{pose}.png")
        height=43 if low else 65
        width=height*art.get_width()/art.get_height() if art else 52
        recoil=2 if 0<=now-shot<75 else 0
        bob=1 if running else 0
        sprite(art,x,y-bob,width,height,facing<0)
        gun=image_asset('weapons/weapon_'+WEAPON_ART[weapon]+'.png')
        if gun is not None and not casting:
            w=24 if weapon=='pistol' else 36
            gh=w*gun.get_height()/gun.get_width()
            ax,ay=aim if aim and 0<=now-shot<240 else (facing,0)
            theta=math.atan2(ay,ax)
            weapon_art=aimed_gun(gun,s.length(w),s.length(gh),(weapon!='rifle') != (facing<0),round(-math.degrees(theta)+(180 if facing<0 else 0)))
            hand=(x+facing*(width*.40-recoil),y-height*.5-bob)
            center=(hand[0]+math.cos(theta)*w*.22,hand[1]+math.sin(theta)*w*.22)
            pixels.blit(weapon_art,weapon_art.get_rect(center=s.point(center)))
    p=a.player
    if t>=a.safe_until or t%8<5:
        hero(a.x-cam,a.y,p.character,a.facing,getattr(a,'crouching',False),abs(a.vx)>5,p.current_weapon,
             p.animation_skill,p.animation_skill_at,p.last_shot_time,getattr(a,"aim",None))
    for mate in teammates:
        x=mate['x']-cam
        hero(x,mate['y'],mate.get('character'),mate['facing'],mate['crouching'],mate.get('moving'),
             mate.get('weapon','pistol'),mate.get('skill'),mate.get('cast'),mate.get('shot',-1000),mate.get('aim'))
        label('队友' if mate['alive'] else '按 E 救援',x-18,mate['y']-85,12)
    for bx,by,dx,dy,weapon,_ in a.bullets:
        x=bx-cam
        line(s,config.WEAPON_DEFS[weapon].color,(x-dx,by-dy),(x,by),3)
        circle(s,(255,252,216),(x,by),1.6)
    for kind,x,y,dx,dy,start in a.effects:
        x-=cam
        if not -160<x<1120:continue
        if kind=='blast':
            age=max(0,min(14,t-start))
            circle(s,(252,153,61),(x,y),10+age*3,3)
            for i in range(9):
                angle=i*math.tau/9
                line(s,(255,214,135),(x+math.cos(angle)*age*2,y+math.sin(angle)*age*2),
                     (x+math.cos(angle)*(age*3+6),y+math.sin(angle)*(age*3+6)),2)
            continue
        if kind in ('grenade','fireball','fire_rocket','ice_ball'):
            obj=SkillProjectile(x,y,math.degrees(math.atan2(dx,-dy)),0,kind)
        elif kind=='fire_wall':obj=FireWall(x,y+20)
        elif kind=='ice_floor':obj=IceFloor(x,y)
        elif kind=='magnetic_storm':
            obj=MagneticStorm(x,y)
            obj.spawn_time=config.game_ticks()-(t-start)*1000//60
        else:
            if kind=='lightning':
                for u in e.units:
                    if math.hypot(u['x']-cam-x,u['y']-y)<280:
                        ex=u['x']-cam
                        Draw.lines(s,(217,182,255),False,[(x,y),((x+ex)/2,y-20),(ex,u['y'])],3)
                for origin,hp in a.crabs:
                    ex=a.crab_rect(origin).centerx-cam
                    if abs(ex-x)<270:
                        Draw.lines(s,(217,182,255),False,[(x,y),((x+ex)/2,y-29),(ex,a.crab_rect(origin).centery)],3)
            else:circle(s,(125,244,237),(x,y),20+(t-start)%25,2)
            continue
        obj.draw(s)
    exit_x=a.EXIT-cam
    if exit_x<1100:
        line(s,(201,213,183),(exit_x,403),(exit_x,309),3)
        Draw.polygon(s,(255,193,82),[(exit_x,309),(exit_x+34,317),(exit_x,330)])
        if a.stage==1:
            for i in range(2):
                circle(s,(105,239,184) if a.objectives[i]>=24 else (255,177,70),(exit_x-155+i*120,340),15,4)
        if a.stage==2:
            for i in range(2):
                if a.objectives[i]<10:
                    core=a.core_rect(i).move(-cam,0)
                    Draw.ellipse(s,(17,66,86),core)
                    Draw.ellipse(s,(255,191,68),core,4)
                    circle(s,(255,236,164),core.center,7)
    def panel(x,y,w,h):
        r(s,(13,36,52),(x,y,w,h),border_radius=7)
        r(s,(79,118,123),(x,y,w,h),1,7)
    hud_left=max(54,config.WEB_SAFE_INSETS[0]+12) if sys.platform=="emscripten" else 16
    panel(hud_left,13,220,54)
    label('横版突围   /   '+a.title,hud_left+12,18,18,bold=True)
    nick=config.CHARACTER_DEFS[p.character].nick if p.character else '渔夫'
    label(nick+'   ·   '+config.WEAPON_DEFS[p.current_weapon].name,hud_left+13,44,13,(161,220,218))
    panel(721,13,223,54)
    label(f'生命  {a.hp} / 3',734,19,16,bold=True)
    label(f'撤离进度   {min(100,round(a.x/a.EXIT*100))}%',828,21,12)
    r(s,(49,80,88),(734,49,195,4))
    r(s,(242,187,97),(734,49,max(1,int(195*min(1,a.x/a.EXIT))),4))
    skills = config.CHARACTER_DEFS[p.character].skills if p.character else ()
    slots = [(sk.name,sk.skill_type) for sk in skills] or [('渔夫手雷','fisher_grenade')]
    if not a.auto:
        for i,(name,skill) in enumerate(slots):
            remaining=max(0,a.cast_ready.get(skill,0)-t)
            x=16+i*120
            panel(x,76,112,24)
            label(('U' if i==0 else 'I')+'  '+name+(f'  {math.ceil(remaining/60)}s' if remaining else ''),
                  x+8,80,12,(157,197,199) if remaining else (242,213,153))
    if a.auto:
        for name,rect in a.buttons().items():
            panel(*rect)
            label(dict(left='左',right='右',down='下',up='上',jump='跳',shoot='射击',use='操作',pause='暂停',
                       skill1='技能一',skill2='技能二',weapon='换枪',hero='角色')[name],rect.x+7,rect.y+15,14)
    else:
        panel(16,501,775,26)
        label('方向键 移动瞄准    小键盘 独立瞄准    K 跳跃    J 射击    E 交互    U / I 技能    Tab 换枪    C 角色    P 暂停',26,505,13)
    if a.x>a.EXIT-700 and not e.boss['hp']:
        panel(275,81,410,34)
        label((f'靠近绞盘按住 E   {min(6,a.objective_ticks//60)} / 6 秒','按住 E 打开两只阀门，再进入吊笼',
               '击破上下两个发光阀芯，穿过撤离门')[a.stage],301,87)
    if a.state=='select':
        panel(207,58,546,422)
        label('横版突围',230,78,27,bold=True)
        label('选择出发点',231,121,14,(157,216,211))
        for i,(name,*_) in enumerate(a.STAGES):
            r(s,(46,104,114) if i==a.selection else (30,62,78),(230,155+65*i,500,52),border_radius=5)
            label(name,247,167+65*i,19)
        label('左右切换   '+('单幕练习' if a.practice else '连续撤离'),230,368)
        label('回车出发   ·   Esc 返回',230,427)
    elif a.state!='playing' or notice:
        panel(190,195,580,100)
        label(notice or {'lost':'撤离失败','won':'撤离成功','paused':'已暂停'}.get(a.state,''),216,211,18,bold=True)
        label('P 继续   ·   Esc 返回' if a.state=='paused' else '回车或轻触继续',217,253)
