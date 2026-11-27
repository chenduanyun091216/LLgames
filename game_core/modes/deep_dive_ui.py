"""PC and main-Web outfit, input, and debrief for the salvage mode."""
import math
import secrets

import pygame

from .. import config
from ..arcade import pointer
from ..sounds import play_sound
from .deep_dive import CONTENT, HZ, RULES, TREASURES, Dive
from .dive_art import GOLD, INK, MINT, MUTED, PANEL, SIZE, TOOL_SYMBOL, Paint
from .dive_records import DiveRecords

SEAS = tuple(CONTENT['maps'])
TOOLS = tuple(CONTENT['tools'])
PAIRINGS = ((TOOLS[0], TOOLS[1]), (TOOLS[0], TOOLS[2]), (TOOLS[1], TOOLS[2]))
SOUNDS = {'sonar':'laser_hit', 'pickup':'coin', 'launch':'water_cast',
          'delivery':'level_up', 'cut':'hit', 'air':'water_cast'}


class DeepDiveMode:
    def __init__(self, player, touch=False):
        self.surface = pygame.Surface(SIZE)
        self.pilot = 'players/' + player._sprite_name() + '.png'
        self.touch = touch
        self.records = DiveRecords()
        self.screen = 'outfit'
        self.sea = 0
        self.pair = 0
        self.last = {}
        self.keys = set()
        self.fingers = {}
        self.stick = (0,0)
        self.edges = set()
        self.accumulator = 0.0
        self.dive = None
        self.cargo = False
        self.cargo_index = 0
        self.catalog_from = 'outfit'
        self.buttons = []
        self.focus = 0

    def change(self, screen):
        self.screen = screen
        self.focus = 0
        self.reset_input()

    def reset_input(self):
        self.keys.clear()
        self.edges.clear()
        self.fingers.clear()
        self.stick = (0,0)
        self.accumulator = 0.0

    def launch(self, same=False):
        sea = SEAS[self.sea]
        if same and sea in self.last:
            seed, teaching = self.last[sea]
        else:
            teaching = sea not in self.last and sea not in self.records.data['best'] and not any(
                p['treasure_id'] in self.records.data['discovered'] for p in CONTENT['maps'][sea]['placements'][0])
            seed = 0 if teaching else secrets.randbits(32)
        self.last[sea] = (seed, teaching)
        self.dive = Dive(sea, PAIRINGS[self.pair], seed, teaching)
        self.cargo = False
        self.cargo_index = 0
        self.change('diving')

    def choose(self, sea):
        self.sea = sea
        self.focus = 3

    def command(self, action):
        if action == 'pause':
            self.change('diving' if self.screen == 'pause' else 'pause')
        elif action == 'cargo':
            self.cargo = not self.cargo
            self.cargo_index = 0
        else:
            self.edges.add(action)

    def select_cargo(self, index):
        self.cargo_index = index
        hold = self.dive.hold
        if hold:
            self.dive.selected = hold[index % len(hold)]['instance_id']

    def interact(self):
        if self.cargo:
            if self.dive.hold:
                self.select_cargo(self.cargo_index)
                self.dive.unload(self.dive.selected)
                self.cargo_index = 0
            return False
        return True

    def step(self):
        d = self.dive
        x,y = self.stick
        x += int(bool(self.keys & {pygame.K_d,pygame.K_RIGHT})) - int(bool(self.keys & {pygame.K_a,pygame.K_LEFT}))
        y += int(bool(self.keys & {pygame.K_s,pygame.K_DOWN})) - int(bool(self.keys & {pygame.K_w,pygame.K_UP}))
        held = [tool for i,tool in enumerate(d.tools)
                if (pygame.K_j,pygame.K_k)[i] in self.keys or tool in self.fingers.values()]
        if self.cargo:
            x,y = 0,0
        interact = 'interact' in self.edges and self.interact()
        d.step(x,y,held,self.edges,interact)
        self.edges.clear()
        if d.pending or d.result:
            self.records.save(d)
        if 'hold' in d.events:
            self.cargo = True
            self.cargo_index = 0
        for event in d.events:
            if event in SOUNDS:
                play_sound(SOUNDS[event])
        d.events.clear()
        if d.result:
            self.change('debrief')

    def open_catalog(self):
        self.catalog_from = self.screen
        self.change('catalog')

    def retreat(self):
        self.dive.finish('withdraw')
        self.records.save(self.dive)
        self.change('debrief')

    def event(self, e):
        if e.type == pygame.KEYUP:
            self.keys.discard(e.key)
            return
        if e.type == pygame.WINDOWFOCUSLOST:
            if self.screen == 'diving':
                self.change('pause')
            else:
                self.reset_input()
            return
        if e.type in (pygame.FINGERUP,pygame.MOUSEBUTTONUP):
            identity = getattr(e,'finger_id','mouse')
            if self.fingers.pop(identity,None) == 'stick':
                self.stick = (0,0)
            return
        if e.type == pygame.FINGERMOTION and self.fingers.get(e.finger_id) == 'stick':
            self.move_stick(pointer(e, self.surface, motion=True))
            return
        if e.type == pygame.KEYDOWN and not getattr(e,'repeat',False):
            if self.screen == 'diving':
                if e.key in self.keys:
                    return
                self.keys.add(e.key)
                if e.key == pygame.K_ESCAPE:
                    self.command('pause')
                elif self.cargo and e.key in (pygame.K_UP,pygame.K_DOWN,pygame.K_w,pygame.K_s):
                    self.select_cargo((self.cargo_index + (1 if e.key in (pygame.K_DOWN,pygame.K_s) else -1))
                                      % max(1,len(self.dive.hold)))
                else:
                    action = {pygame.K_j:self.dive.tools[0],pygame.K_k:self.dive.tools[1],
                              pygame.K_e:'interact',pygame.K_TAB:'cargo'}.get(e.key)
                    if action:
                        self.command(action)
            elif e.key == pygame.K_ESCAPE:
                self.change({'pause':'diving','confirm':'pause','catalog':self.catalog_from,'debrief':'outfit'}.get(self.screen,'exit'))
            elif e.key in (pygame.K_UP,pygame.K_DOWN,pygame.K_LEFT,pygame.K_RIGHT,pygame.K_TAB):
                if self.buttons:
                    self.focus = (self.focus + (-1 if e.key in (pygame.K_UP,pygame.K_LEFT) else 1)) % len(self.buttons)
            elif e.key in (pygame.K_RETURN,pygame.K_KP_ENTER) and self.buttons:
                self.buttons[self.focus % len(self.buttons)][1]()
            return
        pos = pointer(e, self.surface)
        if pos is None:
            return
        if e.type == pygame.FINGERDOWN:
            self.touch = True
        identity = getattr(e,'finger_id','mouse')
        if self.screen == 'diving' and self.touch and pygame.Rect(0,386,148,154).collidepoint(pos):
            if 'stick' not in self.fingers.values():
                self.fingers[identity] = 'stick'
                self.move_stick(pos)
            return
        for i,(rect,callback) in enumerate(self.buttons):
            if rect.collidepoint(pos):
                self.focus = i
                callback()
                return
        if self.touch and self.screen == 'diving':
            for label,action,rect in self.touch_buttons():
                if pygame.Rect(rect).collidepoint(pos):
                    self.fingers[identity] = action
                    self.command(action)
                    return

    def move_stick(self, pos):
        if pos is None:
            return
        dx,dy = pos[0]-72,pos[1]-463
        length = math.hypot(dx,dy)
        self.stick = (0,0) if length < 7 else (dx/max(47,length),dy/max(47,length))

    def touch_buttons(self):
        t1,t2 = self.dive.tools
        return [(TOOL_SYMBOL[t1],t1,(540,473,72,59)), (TOOL_SYMBOL[t2],t2,(622,473,72,59)),
                ('交互','interact',(705,473,83,59)), ('货舱','cargo',(616,408,82,53)),
                ('暂停','pause',(706,408,82,53))]

    def frame(self, events, elapsed, suspended, font, target=None):
        if suspended:
            self.reset_input()
        else:
            for event in events:
                previous = self.screen
                self.event(event)
                if self.screen != previous:
                    break
        if self.screen == 'exit':
            self.records.close()
            return False
        if not suspended and self.screen == 'diving':
            self.accumulator += min(elapsed, 4/HZ)
            while self.accumulator + 1e-10 >= 1/HZ and self.screen == 'diving':
                self.accumulator -= 1/HZ
                self.step()
        if self.records.browser is not None:
            self.records.refresh()
        paint = Paint(config.SCR if target is None else target)
        self.buttons = []
        if self.screen in ('diving','pause','confirm'):
            self.draw_dive(paint)
        if self.screen != 'diving':
            if self.screen not in ('pause','confirm'):
                paint.backdrop(CONTENT['maps'][SEAS[self.sea]]['background'])
            getattr(self, 'draw_' + self.screen)(paint)
        if self.records.error:
            paint.rect(PANEL,(166,513,368,25),radius=6)
            paint.text('本次记录仅在当前会话有效',180,516,15,GOLD)
        return True

    def button(self, paint, box, label, callback, selected=False):
        paint.button(box,label,selected or (self.screen != 'diving' and len(self.buttons)==self.focus))
        self.buttons.append((pygame.Rect(box),callback))

    def draw_outfit(self, p):
        p.rect(PANEL,(30,28,740,484),radius=15)
        p.text('深潜寻宝',55,47,38,INK,True)
        p.text('单人探索  ·  装货或起吊，母船签收后计入图鉴',56,99,17,MUTED)
        p.art('sub',671,99,150,125)
        p.art(self.pilot,705,104,37,39,external=True)
        for i,sea in enumerate(SEAS):
            x = 55+i*230
            self.button(p,(x,163,214,43),CONTENT['maps'][sea]['name'],lambda i=i:self.choose(i),self.sea==i)
            best = self.records.data['best'].get(sea)
            p.text('最佳 ' + str(best) if best is not None else '未完成返港',x+10,214,13,MUTED)
        p.text('装备槽  J / K',56,253,17,GOLD,True)
        for i,pair in enumerate(PAIRINGS):
            label = ' + '.join(CONTENT['tools'][tool][0] for tool in pair)
            self.button(p,(55+i*230,282,214,42),label,lambda i=i:setattr(self,'pair',i),self.pair==i)
        p.text('WASD / 方向键驾驶     E 交互     Tab 货舱     Esc 暂停',56,350,16,INK)
        p.text('切割和绑袋按住，声呐轻按。停稳后按 E 签收返港。',56,381,16,MUTED)
        self.button(p,(55,436,150,44),'下潜',self.launch,True)
        if SEAS[self.sea] in self.last:
            self.button(p,(216,436,150,44),'同一海图',lambda:self.launch(True))
        self.button(p,(410,436,140,44),'藏品图鉴',self.open_catalog)
        self.button(p,(562,436,179,44),'返回玩法大厅',lambda:self.change('exit'))

    def draw_dive(self,p):
        d = self.dive
        seconds = p.world(d, self.pilot)
        p.minimap(d)
        p.rect(PANEL,(12,10,348,98),radius=9)
        oxygen = max(0, math.ceil(d.oxygen/HZ))
        warning = GOLD if oxygen < 30 else MINT
        if oxygen < 12:
            warning = (255,140,127)
        p.text('氧量',24,20,14,MUTED,True)
        p.text(f'{oxygen:03}',67,14,25,warning,True)
        p.rect((31,67,79),(123,25,215,8),radius=4)
        p.rect(warning,(123,25,215*max(0,d.oxygen)/(HZ*RULES['oxygen']),8),radius=4)
        eta = f'返航估算 {seconds} 秒' if seconds is not None else '沿最后已知出口返航'
        p.text((('危急  ·  ' if oxygen < 12 else '低氧  ·  ' if oxygen < 30 else '')+eta),24,53,15,warning)
        p.text('委托 ' + TREASURES[d.contract][0] + f'   ·   货舱 {d.weight}/6',24,79,15,INK)
        if self.screen != 'diving':
            return
        target,obj = d.target()
        hint = {'dock':'E  停稳并确认返港','air':'E  停靠补气 2 秒','hold':'E / Tab  查看货舱',
                'item':'E  装舱 ' + (TREASURES[obj['treasure_id']][0] if obj else '')}[target]
        if d.air_active and not d.air_used:
            hint = f'补气中 {d.air_ticks/60:.1f} / 2 秒'
        p.rect(PANEL,(177,440,353,88),radius=8)
        p.text(hint,190,448,16,MINT,True)
        for i, tool in enumerate(d.tools):
            suffix = ''
            if tool == 'sonar':
                cooldown = max(0, math.ceil((d.sonar_at+HZ*RULES['sonarCooldown']-d.tick)/HZ))
                suffix = f' · {cooldown}秒' if cooldown else ' · 就绪'
            elif tool == 'lift_bag':
                item = d.lift_target()
                suffix = f' · {d.bags}只'
                if item:
                    suffix += ' → ' + TREASURES[item['treasure_id']][0]
            elif gate := d.nearest_gate():
                suffix = f" → 闸门 {d.cut.get(gate['id'],0)*100//120}%"
            p.text('JK'[i]+'  '+CONTENT['tools'][tool][0]+suffix,190,473+i*23,14,INK)
        notice = d.notice if d.tick < d.notice_until else ''
        if not notice and d.teaching and d.sea == 'wreck':
            if d.demo_at is not None:
                notice = '演示浮袋 · 运输中' if d.tick < d.demo_at else '演示浮袋 · 母船已签收'
            else:
                notice = '沿泊位下潜，灯光可照见铜罗盘'
        if notice:
            p.rect(PANEL,(177,396,353,36),radius=6)
            p.text(notice,190,403,16,GOLD)
        if self.cargo:
            p.rect(PANEL,(224,146,351,222),radius=9)
            p.text('当前货舱',240,158,22,INK,True)
            p.text('选中货物后按 E 卸下',241,194,15,MUTED)
            for i,item in enumerate(d.hold):
                name,weight,_,_ = TREASURES[item['treasure_id']]
                self.button(p,(240,223+38*i,311,35),f'{name}  ·  {weight} 重',lambda i=i:self.select_cargo(i),i==self.cargo_index)
            if not d.hold:
                p.text('空舱',241,232,17,MUTED)
            self.button(p,(453,156,105,36),'关闭',lambda:self.command('cargo'))
        if self.touch:
            p.circle(PANEL,(72,463),58)
            p.circle(MUTED,(72,463),57,1)
            p.circle((51,128,144),(72+self.stick[0]*44,463+self.stick[1]*44),22)
            for label,action,rect in self.touch_buttons():
                p.button(rect,label,action in self.fingers.values())
                if action == 'lift_bag':
                    p.art('bag',rect[0]+51,rect[1]+28,21,30)

    def draw_pause(self,p):
        p.rect(PANEL,(200,154,400,227),radius=12)
        p.text('航次已暂停',222,178,28,INK,True)
        self.button(p,(222,245,354,48),'继续航行',lambda:self.change('diving'))
        self.button(p,(222,306,354,48),'紧急撤退…',lambda:self.change('confirm'))

    def draw_confirm(self,p):
        d=self.dive
        p.rect(PANEL,(176,145,448,241),radius=12)
        p.text('确认紧急撤退',200,172,27,INK,True)
        cargo = [TREASURES[i['treasure_id']][0] for i in d.items.values() if i['state'] in ('hold','in_transit')]
        p.text('将遗失：' + ('、'.join(cargo) if cargo else '无'),200,229,16,GOLD)
        p.text('母船已签收的货物仍会保留。',200,263,16,MUTED)
        self.button(p,(200,311,184,46),'取消',lambda:self.change('pause'))
        self.button(p,(409,311,191,46),'确认撤退',self.retreat)

    def draw_debrief(self,p):
        d = self.dive
        result = d.result
        reason = {'safe':'安全返航','oxygen':'氧气耗尽','withdraw':'主动撤退'}[result['reason']]
        p.rect(PANEL,(52,33,696,469),radius=14)
        p.text(reason,76,58,35,INK,True)
        p.text('委托' + ('已完成' if result['complete'] else '未完成') + ' · ' + TREASURES[d.contract][0],78,111,17,MINT)
        p.text(str(result['income']),598,57,47,GOLD,True)
        p.text('本航次收入',595,117,16,MUTED)
        for row,(kind,label) in enumerate((('delivered','已送达'),('lost','遗失'))):
            p.text(label,78,168+102*row,18,MUTED,True)
            for i,key in enumerate(result[kind]):
                x,y = 235+i*172,189+102*row
                p.art(key,x,y,47,55)
                p.text(TREASURES[key][0],x-33,y+32,14,INK)
            if not result[kind]:
                p.text('无',193,169+102*row,17,MUTED)
        if self.records.error and (result['reason']=='safe' or result['delivered']):
            self.button(p,(77,378,166,36),'重试保存',lambda:self.records.save(d,retry=True))
        self.button(p,(77,426,151,47),'同配装重试',lambda:self.launch(True))
        self.button(p,(238,426,132,47),'回母船',lambda:self.change('outfit'))
        self.button(p,(380,426,133,47),'藏品图鉴',self.open_catalog)
        self.button(p,(523,426,201,47),'返回玩法大厅',lambda:self.change('exit'))

    def draw_catalog(self,p):
        discovered = set(self.records.data['discovered'])
        if self.dive:
            discovered.update(i['treasure_id'] for i in self.dive.items.values() if i['state']=='delivered')
        p.rect(PANEL,(27,22,746,499),radius=13)
        p.text(f'藏品图鉴  {len(discovered)} / 9',48,37,27,INK,True)
        for i,(key,(name,_,_,hint)) in enumerate(TREASURES.items()):
            row,col = divmod(i,3)
            x,y = 47+col*238,95+row*118
            p.rect((19,48,65),(x,y,224,105),radius=6)
            if key in discovered:
                p.art(key,x+42,y+42,66,64)
            else:
                p.circle((50,83,101),(x+43,y+43),25,1)
                p.text('?',x+36,y+26,23,MUTED,True)
            p.text(name,x+83,y+17,17,INK,True)
            p.text(CONTENT['maps'][SEAS[row]]['name'],x+83,y+46,13,MUTED)
            p.text(hint,x+7,y+82,12,GOLD if key in discovered else MUTED)
        self.button(p,(50,460,150,42),'返回',lambda:self.change(self.catalog_from))
