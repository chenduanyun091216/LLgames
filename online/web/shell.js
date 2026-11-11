/* DOM lobby/controls; Python/Pygame alone renders the original game. */
'use strict';
window.ttgamesLoadStage = stage => { const box=document.querySelector('#infobox'); if(box) box.dataset.stage=stage; };
const markup = `<div id="toast" role="alert" hidden></div><div id="status" role="status">正在加载本地游戏引擎…</div>
<section id="lobby" class="panel"><h1>海洋生物入侵</h1><p>十一关战役 · 双人局域网协作</p><div id="join"><label for="code">房间码</label><input id="code" maxlength="12" placeholder="输入主机提供的房间码" autocomplete="off"><button id="connect" class="primary">加入房间</button></div><div id="room" hidden><p id="players"></p><label for="orientation">双方统一方向（P1 选择）</label><select id="orientation"><option value="landscape">横屏</option><option value="portrait">竖屏</option></select><div class="row"><button id="ready" disabled>准备</button><select id="difficulty" aria-label="难度"><option value="easy">简单</option><option value="medium">中等</option><option value="hard">困难</option></select></div><button id="start" class="primary">开始十一关战役</button></div><p id="error" role="alert"></p><p class="hint">两人连接并准备后，由 P1 开始。电脑：WASD / 方向键移动，空格射击，Q/E 技能，R 激光，F 飞镖，B 商店。手机支持多点触控。</p></section>
<div id="orientation-warning" role="alert" hidden></div><div id="transition-info" role="status" hidden></div>
<div id="controls" hidden><div id="stick" aria-label="移动摇杆"><i></i></div><div class="actions"><button data-action="skill1">技能 1</button><button data-action="skill2">技能 2</button><button id="shoot">射击</button><button data-action="laser">激光</button><button data-action="dart">飞镖</button></div><div class="toolbar"><button data-action="shop_open">商店</button><button data-action="revive">复活</button></div></div>
<section id="recovery" class="panel" hidden><h1>连接需要重试</h1><p id="recovery-detail"></p><button id="retry" class="primary">使用原身份重连</button><div class="row"><button id="change-room">更换房间码</button><button id="reset-token" hidden>清除失效凭证并重新加入</button></div></section>
<section id="shop" class="panel" hidden><h1>商店</h1><p>共享金币 · 任一玩家购物时，全局暂停</p><div id="catalog"></div><button data-action="shop_close" class="primary">关闭商店</button></section>
<section id="result" class="panel" hidden><h1 id="result-title"></h1><p id="result-detail">协作完成全部十一关普通战役，不含无限模式。</p><button data-action="restart" class="primary">重新挑战</button></section>`;
document.body.insertAdjacentHTML('beforeend', markup);
const $ = id => document.getElementById(id);
let state = null, ready = false, rendererReady = false, connected = false;
const held = new Set(), pointerHeld = new Set(); let stick = {x:0,y:0,id:null};
function clearInput() { held.clear(); pointerHeld.clear(); stick={x:0,y:0,id:null}; $('stick').firstChild.style.transform=''; bridge.input(0,0,false); }
function status(kind, detail) {
  if(kind==='connected') $('recovery').hidden=true;
  if(kind==='stopped') { $('recovery').hidden=false; $('recovery-detail').textContent=detail; $('reset-token').hidden=detail!=='invalid_reconnect_token'; }
  if(kind!=='error') connected = kind === 'connected';
  $('status').textContent = ({connecting:'连接主机中…',connected:'已连接，等待游戏状态',disconnected:'连接断开，正在重连；主机会暂停游戏',stopped:detail,error:detail})[kind] || kind;
  if(kind === 'connecting' || kind === 'disconnected' || kind === 'stopped') clearInput();
  if(kind==='error') { $('error').textContent=detail; $('toast').textContent=detail; $('toast').hidden=false; setTimeout(()=>$('toast').hidden=true,3500); }
}
const bridge = window.LLOnline = new window.LLBridge({onStatus:status,onState:renderState,isHidden:()=>document.hidden||!rendererReady});
$('orientation').value=bridge.getOrientation();
$('orientation').onchange=()=>{clearInput();bridge.send({type:'room_orientation',orientation:$('orientation').value});};
function reportOrientation(){clearInput();bridge.reportOrientation();if(state)renderState(state);}
addEventListener('resize',reportOrientation);
addEventListener('orientationchange',()=>setTimeout(reportOrientation,150));
$('ready').disabled=true;
bridge.readyRenderer = () => { rendererReady=true; $('ready').disabled=false; if(bridge.welcomed&&!document.hidden)bridge.action('resume'); if($('infobox')) $('infobox').style.display='none'; if(!connected) $('status').textContent='引擎已就绪，请输入房间码'; if(state) renderState(state); };
bridge.reportError = text => { $('error').textContent=text; $('status').textContent=text; };
$('connect').onclick = () => { const code=$('code').value.trim().toUpperCase(); if(!/^[A-Z0-9]{4,12}$/.test(code)){ $('error').textContent='请输入 4–12 位字母或数字房间码'; return; } $('error').textContent=''; bridge.connect(code); };
$('retry').onclick=()=>{ $('recovery').hidden=true;bridge.connect(bridge.code); };
$('reset-token').onclick=()=>{ if(bridge.resetRejectedToken(bridge.code)) $('recovery').hidden=true; };
$('change-room').onclick=()=>{ bridge.disconnect();connected=false;state=null;$('recovery').hidden=true;$('lobby').hidden=false;$('join').hidden=false;$('room').hidden=true;$('shop').hidden=true;$('result').hidden=true;$('controls').hidden=true;$('code').focus(); };
$('code').addEventListener('keydown',e=>{if(e.key==='Enter')$('connect').click();});
$('ready').onclick=()=>{if(rendererReady&&bridge.welcomed)bridge.send({type:'ready',ready:!ready});};
$('start').onclick=()=>bridge.send({type:'start',difficulty:$('difficulty').value});
function combatAvailable(){return state?.phase==='playing'&&state.stage!=='transition'&&state.orientation===bridge.getOrientation();}
function sendAction(action,key){if(['skill1','skill2','laser','dart','shop_open'].includes(action)&&!combatAvailable())return;clearInput();bridge.action(action,key);}
document.addEventListener('click',e=>{const b=e.target.closest('[data-action]');if(b)sendAction(b.dataset.action,b.dataset.key);});
function renderState(s) {
  if((s.paused&&!state?.paused)||(s.stage==='transition'&&state?.stage!=='transition'))clearInput();
  state=s; const me=s.players.find(p=>p.slot===bridge.slot); if(!me)return;
  if(!s.orientation&&bridge.slot===1)bridge.send({type:'room_orientation',orientation:$('orientation').value});
  if(s.orientation){$('orientation').value=s.orientation;document.documentElement.dataset.orientation=s.orientation;}
  $('orientation').disabled=bridge.slot!==1;
  const matches=!!s.orientation&&s.players.length===2&&s.players.every(p=>p.orientation===s.orientation);
  $('orientation-warning').hidden=matches||!s.orientation;
  $('orientation-warning').textContent=`双方必须使用${s.orientation==='portrait'?'竖屏':'横屏'}。请旋转设备或调整浏览器窗口；方向一致后自动继续。`;
  ready=me.ready; $('join').hidden=true; $('room').hidden=false;
  $('ready').textContent=ready?'取消准备':'准备';
  $('players').textContent=s.players.map(p=>`P${p.slot}${p.slot===bridge.slot?'（你）':''}：${p.connected?(p.ready?'已准备':'未准备'):'未连接'}`).join(' · ');
  $('start').hidden=bridge.slot!==1; $('difficulty').disabled=bridge.slot!==1;
  $('start').disabled=!rendererReady || s.players.length!==2 || !s.players.every(p=>p.connected&&p.ready)||!matches||!!s.paused;
  $('lobby').hidden=s.phase!=='lobby'; $('controls').hidden=!combatAvailable()||!rendererReady;
  $('transition-info').hidden=s.stage!=='transition';
  $('transition-info').textContent=`第 ${s.current_level||1} 关完成 · ${Math.ceil((s.transition_remaining_ms||0)/1000)} 秒后继续${s.paused?'（已暂停）':''}`;
  $('shop').hidden=!me.shop_open; $('result').hidden=!['won','lost'].includes(s.phase)&&s.pause_reason!=='server_error';
  $('result-title').textContent=s.pause_reason==='server_error'?'主机运行异常，游戏已暂停':s.phase==='won'?'十一关战役全部通关！':'挑战结束';
  $('result-detail').textContent=s.pause_reason==='server_error'?(bridge.slot===1?'请重新开始战役；本次进度将重置。':'请等待 P1 重新开始战役。'):'协作完成全部十一关普通战役，不含无限模式。';
  $('result').querySelector('button').disabled=bridge.slot!==1;
  $('status').textContent=`房间 ${bridge.code} · P${bridge.slot} · 第 ${s.current_level||1}/${s.total_levels||11} 关${s.level_title?' '+s.level_title:''} · 金币 ${s.gold} · 生命 ${s.lives} | `+s.players.map(p=>`P${p.slot} ${p.alive?`${Math.ceil(p.hp)}/${p.max_hp}`:'等待复活'}`).join(' · ')+(s.paused?` | 已暂停：${s.pause_reason||'等待玩家'}`:'');
  const boss=s.world?.objects?.find(o=>o.id===s.world.boss)?.fields;
  if(!boss&&combatAvailable()) $('status').textContent+=` | Boss 倒计时 ${Math.ceil((s.boss_remaining_ms||0)/1000)} 秒`;
  const revive=document.querySelector('[data-action="revive"]');
  revive.textContent=s.lives>0?'复活（消耗 1 条共享生命）':`复活 ${s.revive_cost} 金币（全队剩余 ${s.paid_revives_remaining} 次）`;
  revive.disabled=me.alive||(s.lives<=0&&s.paid_revives_remaining===0);
  const skillNames={fisher:[['手雷','fisher_grenade'],['无技能','']],fire:[['火墙','fire_wall'],['火球','fireball']],ice:[['冰墙','ice_floor'],['冰球','ice_balls']],water:[['水疗','water_heal'],['潮汐','water_boost']],radiation:[['闪电链','lightning'],['磁暴','magnetic_storm']]};
  (skillNames[me.character]||skillNames.fisher).forEach(([name,key],i)=>{const button=document.querySelector(`[data-action="skill${i+1}"]`),now=s.world?.time_ms||0;const remaining=Math.max(me.cooldowns?.[key]||0,me.active_until?.[key]||0)-now;button.textContent=name+(remaining>0?` ${Math.ceil(remaining/1000)}s`:'');button.disabled=!key||!me.alive;});
  if(me.shop_open) renderCatalog(s,me);
}
let catalogSignature='';
function renderCatalog(s,me) {
  const sig=JSON.stringify([s.catalog,me.weapon,me.character,s.gold]); if(sig===catalogSignature)return; catalogSignature=sig;
  const target=$('catalog');target.replaceChildren();
  for(const [group,action] of [['weapons','weapon'],['characters','character']]) {
    const items=s.catalog?.[group]||[];
    for(const [key,value] of (Array.isArray(items)?items.map(i=>[i.key,i]):Object.entries(items))) {
      const row=document.createElement('div');row.className='row'; const button=document.createElement('button');
      button.textContent=`${value.name||key} · ${value.owned?'已拥有':`${value.price} 金币`}`;button.dataset.action=action;button.dataset.key=key;row.append(button);target.append(row);
    }
  }
}
const movement=new Set(['KeyW','KeyA','KeyS','KeyD','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Space']);
const actions={KeyQ:'skill1',KeyE:'skill2',KeyR:'laser',KeyF:'dart',KeyB:'shop_open'};
addEventListener('keydown',e=>{if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;if(movement.has(e.code)){e.preventDefault();held.add(e.code);}if(actions[e.code]&&!e.repeat){e.preventDefault();sendAction(actions[e.code]);}});
addEventListener('keyup',e=>held.delete(e.code));addEventListener('blur',clearInput);document.addEventListener('visibilitychange',()=>{clearInput();bridge.reportOrientation();if(connected)bridge.action(document.hidden||!rendererReady?'suspend':'resume');});
$('shoot').addEventListener('pointerdown',e=>{e.preventDefault();e.currentTarget.setPointerCapture(e.pointerId);pointerHeld.add(e.pointerId);});
for(const type of ['pointerup','pointercancel','lostpointercapture'])$('shoot').addEventListener(type,e=>pointerHeld.delete(e.pointerId));
function moveStick(e){if(e.pointerId!==stick.id)return; const r=$('stick').getBoundingClientRect(),radius=r.width/2;let x=(e.clientX-r.left-radius)/radius,y=(e.clientY-r.top-radius)/radius;const n=Math.max(1,Math.hypot(x,y));stick.x=x/n;stick.y=y/n;$('stick').firstChild.style.transform=`translate(${stick.x*radius*.55}px,${stick.y*radius*.55}px)`;}
$('stick').addEventListener('pointerdown',e=>{e.preventDefault();if(stick.id!==null)return;stick.id=e.pointerId;e.currentTarget.setPointerCapture(e.pointerId);moveStick(e);});$('stick').addEventListener('pointermove',moveStick);
for(const type of ['pointerup','pointercancel','lostpointercapture'])$('stick').addEventListener(type,e=>{if(e.pointerId===stick.id){stick={x:0,y:0,id:null};$('stick').firstChild.style.transform='';}});
setInterval(()=>{if(!connected||!combatAvailable())return;let x=stick.x+Number(held.has('KeyD')||held.has('ArrowRight'))-Number(held.has('KeyA')||held.has('ArrowLeft')),y=stick.y+Number(held.has('KeyS')||held.has('ArrowDown'))-Number(held.has('KeyW')||held.has('ArrowUp'));const n=Math.max(1,Math.hypot(x,y));if(document.hidden||state.paused){x=0;y=0;}bridge.input(x/n,y/n,!document.hidden&&!state.paused&&(held.has('Space')||pointerHeld.size>0));},50);
