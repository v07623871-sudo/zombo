(()=>{
'use strict';
const tg=window.Telegram?.WebApp;
try{tg?.ready();tg?.expand();tg?.setHeaderColor('#11161b');tg?.setBackgroundColor('#0b0e12');}catch(e){}
const app=document.getElementById('app');
let warsData=null;
let clanMissions=null;
let selectedTerritory='bridge';
let raids=null;
let expeditions=null;
let navTrail=[],navigationBusy=false,leaderboardSort='level';
let gearMarket=null,gearMarketTab='browse',gearMarketPage=1;
let story=null;
let notificationData=null;
let worldEvents=null,adminWorldEvents=null;
let encounterData=null;
let adminEconomy=null,adminEconomyDays=7,adminGrantCatalog=null;
let adminSummary=null,adminPlayers=null,adminDetail=null,adminAudit=null,adminTransactions=null,adminRisk=null,adminOperations=null,adminNotifications=null,adminLedger=null,adminLedgerPage=1,adminLedgerPlayer='',adminLedgerKind='',adminTreasury=null,adminTreasuryPage=1,adminTreasuryClan='',adminTab='players',adminQuery='',adminClass='',adminMinLevel=1,adminPage=1,adminAuditPage=1,adminNoticePage=1,adminNoticeStatus='',adminNoticeCategory='';
let cfg=null,me=null,screen='home',activePath=0,sub='inventory',loading=false,modal=null,zone='body',pvp=null,clans=null,quests=null,boss=null,lots=null,territories=null,leaderboard=null,shop=null,stars=null,premium=null,choice=null;
let auth=tg?.initData?'tma '+tg.initData:(location.search.includes('demo=1')?'demo:1001':'');
let toastTimer;
let inventoryFilter='all',inventoryQuery='',craftFilter='all',craftQuery='',craftReadyOnly=false;
let gearSlotFilter='all',gearSort='equipped',gearQuery='';
const money=n=>Number(n||0).toLocaleString('ru-RU');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=(a,b)=>Math.min(100,Math.max(0,Math.round(a/Math.max(1,b)*100)));
const itemKind=item=>['weapon','armor','consumable','case','chest'].includes(item?.type)?item.type:'material';
const section=(title,meta='')=>`<div class="section-title"><h2>${title}</h2><span>${meta}</span></div>`;
const btn=(label,act,kind='soft',val='',disabled=false)=>`<button type="button" class="btn ${kind}" data-action="${act}" data-value="${esc(val)}" ${disabled?'disabled':''}>${label}</button>`;
const bar=(val,max,kind='')=>`<div class="progress ${kind}"><span style="width:${pct(val,max)}%"></span></div>`;
function notice(msg,error=false){const el=document.getElementById('toast');el.innerText=msg;el.className='visible'+(error?' error':'');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.className='',3600);try{tg?.HapticFeedback?.notificationOccurred(error?'error':'success')}catch(e){}}
async function api(url,method='GET',payload){const response=await fetch('/api/'+url,{method,headers:{'Content-Type':'application/json','Authorization':auth},body:payload?JSON.stringify(payload):undefined});let j;try{j=await response.json()}catch(e){throw new Error('Сервер недоступен, попробуй позже')};if(!response.ok)throw new Error(typeof j.detail==='string'?j.detail:'Ошибка запроса');return j}
async function act(url,body,refresh=true){if(loading)return;loading=true;try{const res=await api(url,'POST',body);if(res.message)notice(res.message);if(refresh)await sync();return res}catch(e){notice(e.message,true)}finally{loading=false}}
async function sync(){me=await api('me');await fetchScreen();render()}
async function fetchScreen(){if(screen==='encounters')encounterData=await api('encounters');if(screen==='world-events')worldEvents=await api('world-events');if(screen==='notifications')notificationData=await api('notifications');if(screen==='gear-market')gearMarket=await api('gear-market?page='+gearMarketPage);if(screen==='story')story=await api('story');if(screen==='raids')raids=await api('raids');if(screen==='expeditions')expeditions=await api('expeditions');if(screen==='quests')quests=await api('quests');if(screen==='boss')boss=await api('boss');if(screen==='map')territories=await api('territories');if(screen==='clan'){[clans,territories,warsData,clanMissions]=await Promise.all([api('clans'),api('territories'),api('territories/wars'),api('clan-missions')])};if(screen==='market')lots=await api('market');if(screen==='pvp')pvp=await api('pvp');if(screen==='leaders')leaderboard=await api('leaderboard?sort='+leaderboardSort);if(screen==='shop')shop=await api('shop');if(screen==='stars'){stars=await api('stars');premium=await api('premium')}if(screen==='admin')await fetchAdmin()}
async function fetchAdmin(){adminSummary=await api('admin/summary');if(adminTab==='players'){if(!adminGrantCatalog)adminGrantCatalog=await api('admin/grant-catalog');adminPlayers=await api('admin/players?q='+encodeURIComponent(adminQuery)+'&hero_class='+encodeURIComponent(adminClass)+'&min_level='+adminMinLevel+'&page='+adminPage);if(adminDetail)adminDetail=await api('admin/players/'+adminDetail.id)}if(adminTab==='audit')adminAudit=await api('admin/audit?page='+adminAuditPage);if(adminTab==='transactions')adminTransactions=await api('admin/transactions');if(adminTab==='ledger'){let query='admin/ledger?page='+adminLedgerPage;if(adminLedgerPlayer)query+='&player_id='+encodeURIComponent(adminLedgerPlayer);if(adminLedgerKind)query+='&kind='+encodeURIComponent(adminLedgerKind);adminLedger=await api(query)}if(adminTab==='treasury'){let query='admin/treasury-ledger?page='+adminTreasuryPage;if(adminTreasuryClan)query+='&clan_id='+encodeURIComponent(adminTreasuryClan);adminTreasury=await api(query)}if(adminTab==='economy')adminEconomy=await api('admin/economy/flows?days='+adminEconomyDays);if(adminTab==='risk')adminRisk=await api('admin/risk');if(adminTab==='events')adminWorldEvents=await api('admin/world-events');if(adminTab==='diagnostics')[adminOperations,adminNotifications]=await Promise.all([api('admin/operations'),api('admin/notifications?status='+encodeURIComponent(adminNoticeStatus)+'&category='+encodeURIComponent(adminNoticeCategory)+'&page='+adminNoticePage)])}
const screenNames={home:'База',map:'Карта',profile:'Герой',clan:'Клан',more:'Меню',fight:'Бой',talents:'Таланты',inventory:'Инвентарь',craft:'Мастерская',quests:'Задания',boss:'Мировой босс',market:'Биржа',pvp:'Арена',raids:'Рейды',expeditions:'Экспедиции',shop:'Торговец',cases:'Арсенал кейсов',gear:'Арсенал',pets:'Питомцы',story:'Сюжет',stars:'Zombo Stars',leaders:'Лидеры',bestiary:'Бестиарий','gear-market':'Рынок снаряжения',notifications:'Уведомления','world-events':'События',encounters:'Встречи',admin:'Админка'};
function fallbackScreen(){return screen==='fight'?'map':screen==='talents'?'profile':['home','map','profile','clan','more'].includes(screen)?'home':'more'}
function syncTelegramBack(){try{if(me?.class&&(modal||screen!=='home'||navTrail.length))tg?.BackButton?.show();else tg?.BackButton?.hide()}catch(e){}}
function screenPath(){if(!me?.class||(screen==='home'&&!navTrail.length))return '';const previous=navTrail.at(-1)||fallbackScreen();return `<div class="screen-path"><button type="button" data-action="back" aria-label="Назад к ${esc(screenNames[previous]||'предыдущему экрану')}">← НАЗАД</button><span>${esc(screenNames[screen]||'Терминал')}</span>${screen!=='more'?'<button type="button" data-action="nav" data-value="more">МЕНЮ</button>':''}</div>`}
function actionScreen(next,replace=false){if(next===screen)return;if(replace){if(navTrail.at(-1)===next)navTrail.pop()}else{navTrail.push(screen);if(navTrail.length>20)navTrail.shift()}screen=next}
async function nav(page){if(navigationBusy||page===screen)return;const previous=screen;navigationBusy=true;screen=page;try{await fetchScreen();navTrail.push(previous);if(navTrail.length>20)navTrail.shift();window.scrollTo(0,0);render()}catch(e){screen=previous;notice(e.message,true)}finally{navigationBusy=false}}
async function goBack(){if(loading||navigationBusy)return;if(modal){modal=null;render();return}if(screen==='home'&&!navTrail.length)return;let previous=navTrail.pop()||fallbackScreen();while(previous===screen&&navTrail.length)previous=navTrail.pop();if(previous==='fight'&&!me?.battle)previous='map';const current=screen;navigationBusy=true;screen=previous;try{await fetchScreen();window.scrollTo(0,0);render()}catch(e){screen=current;navTrail.push(previous);notice(e.message,true)}finally{navigationBusy=false}}
function art(klass='soldier',zombie=false){
  const colors={medic:'#acd8cb',soldier:'#b5bdb5',assassin:'#d0a09a',thief:'#c2b69e'};let col=zombie?'#869d80':colors[klass]||'#c4bb9f';
  let addon={medic:'<path d="M117 63h14v-12h13v12h13v12h-13v12h-13V75h-14z" fill="#d95755"/>',soldier:'<path d="M93 50q42-30 86 0v14H93z" fill="#4c625d"/><rect x="85" y="48" width="100" height="12" rx="4" fill="#6e8071"/>',assassin:'<path d="M74 87q-8-52 60-65 67 8 64 65l-30-21-19 11-21-12z" fill="#4b4144"/><path d="M110 84h50" stroke="#322e33" stroke-width="13"/>',thief:'<path d="M59 94q27-91 83-92 62 10 83 93l-48-32-72 0z" fill="#514c43"/><path d="M100 88h78" stroke="#786c59" stroke-width="7"/>'}[klass]||'';
  if(zombie)addon='<path d="M79 60q45-59 100-6l-13 23-65 2z" fill="#3b5149"/><path d="M101 111l12 4m29-13 17 5" stroke="#6a372f" stroke-width="7"/>';
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 270 320" aria-hidden="true"><defs><linearGradient id="j-${klass}-${zombie}" x1="0" x2="1" y1="0" y2="1"><stop stop-color="${col}"/><stop offset="1" stop-color="#434e4d"/></linearGradient></defs><ellipse cx="138" cy="304" rx="96" ry="12" fill="#080b0b" opacity=".3"/><path d="M78 185l-35 28-19 83h59l25-52 8 57h93l-8-57 22 51h45l-39-94-38-25z" fill="#303b3a" stroke="#5a655b" stroke-width="5"/><path d="M91 174q-43 22-48 64l45 18 19-43-3 87h70l-6-87 28 38 42-23q-2-36-45-60z" fill="url(#j-${klass}-${zombie})" stroke="#222e30" stroke-width="6"/><path d="M106 156v34q29 23 55 0v-35" fill="${col}"/><ellipse cx="134" cy="98" rx="53" ry="67" fill="${col}" stroke="#424743" stroke-width="5"/>${addon}<path d="M112 104l10 2m25-2 10-2" stroke="#171f1e" stroke-width="6" stroke-linecap="round"/><path d="M130 136l10 0" stroke="#3b3130" stroke-width="5" stroke-linecap="round"/><path d="M108 192h53m-40 20h26" stroke="#2f4140" stroke-width="6"/><path d="M197 177l34-56 7 7-28 70z" fill="#8e948d" stroke="#283239" stroke-width="4"/><path d="M110 263v39m45-40v40" stroke="#161e22" stroke-width="10"/></svg>`;
}
function uiIcon(name){return icon(name)}
function icon(name){const paths={book:'<path d="M12 6C9 4 6 4 3 5v15c4-2 7-1 9 1 2-2 5-3 9-1V5c-3-1-6-1-9 1zM12 6v15"/>',bag:'<path d="M5 9h14l1 12H4L5 9zm4 0V6a3 3 0 0 1 6 0v3"/>',hammer:'<path d="m4 20 12-12M12 4l4-2 6 6-2 4zM2 9l5-5"/>',shop:'<path d="M3 10h18v11H3zM2 10l3-7h14l3 7M9 21v-7h6v7"/>',exchange:'<path d="M4 8h16m-4-4 4 4-4 4M20 16H4m4-4-4 4 4 4"/>',check:'<path d="m3 12 6 6L21 6"/>',leader:'<path d="M4 7h16v4c0 5-3 7-8 7s-8-2-8-7V7zm8 11v3M7 21h10M4 9H2c0 4 1 6 4 6m14-6h2c0 4-1 6-4 6"/>',home:'<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1z"/>',map:'<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2.5 5-4.5 2 2-4.5z"/>',hero:'<circle cx="12" cy="7" r="4"/><path d="M4 21v-2c0-4 3-6 8-6s8 2 8 6v2"/>',clan:'<circle cx="8" cy="8" r="3"/><circle cx="17" cy="9" r="2"/><path d="M2 20v-2c0-4 2-6 6-6s7 2 7 6v2H2Zm14 0h6v-3q0-3-4-4"/>',menu:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',coins:'<circle cx="12" cy="12" r="9"/><path d="M15 8.5H10a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H9m3-11v13"/>',gem:'<path d="m2 9 4-5h12l4 5-10 12zM2 9h20M6 4l6 17L18 4"/>',skull:'<path d="M6 17V9a6 6 0 0 1 12 0v8l-2 2v2h-8v-2z"/><circle cx="9" cy="12" r="1" fill="currentColor"/><circle cx="15" cy="12" r="1" fill="currentColor"/><path d="M11 16h2"/>',shield:'<path d="m12 2 8 4v6c0 5-4 9-8 10-4-1-8-5-8-10V6z"/>',swords:'<path d="M4 20 17 7l1-4 3 3-4 1L4 20zm0-4 4 4m12 0L7 7 6 3 3 6l4 1 13 13zm0-4-4 4"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/>',target:'<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4"/>'};return `<svg class="ui-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name]||paths.menu}</svg>`}
function header(){return `<header class="top"><div class="brand">ZOMBO<span>AFTER THE FALL · 0.41.0</span></div><div class="currencies"><div class="currency">${icon('coins')} <b>${money(me?.caps)}</b></div><div class="currency gem">${icon('gem')} <b>${money(me?.zombo)}</b></div></div></header>`}

function navBar(){let tabs=[['home','home','База'],['map','map','Карта'],['profile','hero','Герой'],['clan','clan','Клан'],['more','menu','Меню']];return `<nav class="bottom-nav">${tabs.map(([id,ico,label])=>`<button data-action="nav" data-value="${id}" class="${(screen===id||(screen==='talents'&&id==='profile')||(['pvp','boss','market','leaders','quests','shop','cases','stars','pets','bestiary','raids','expeditions','gear','story','gear-market','admin','world-events','notifications','encounters'].includes(screen)&&id==='more'))?'active':''}"><span class="nav-ico">${icon(ico)}</span>${label}</button>`).join('')}</nav>`}
function miniStats(){return `<div class="panel"><div class="flex-between"><div><span class="tag">Здоровье · энергия · опыт</span><h3 style="margin:6px 0;font:600 18px Oswald">${esc(me.name)} <span style="color:var(--gold)">LVL ${me.level}</span></h3></div>${btn('Профиль ↗','nav','ghost','profile')}</div><div class="bar-label"><span>♥ Здоровье</span><em>${me.hp} / ${me.max_hp}</em></div>${bar(me.hp,me.max_hp,'red')}<div class="bar-label"><span>ϟ Энергия</span><em>${me.stamina} / 500</em></div>${bar(me.stamina,500,'blue')}<div class="bar-label"><span>✧ Опыт</span><em>${money(me.xp)} / ${money(me.xp_next)}</em></div>${bar(me.xp,me.xp_next)}</div>`}
function home(){let near=cfg.locations[me.location];let goal=me.kills===0?(me.location==='base'?{title:'ПЕРВЫЙ ВЫХОД',description:'Выбери Мёртвый лес и отправляйся в первую экспедицию.',action:'НА КАРТУ',dest:'map'}:{title:'ПЕРВАЯ ПОБЕДА',description:'Начни бой, чтобы открыть первый вид заражённых в бестиарии.',action:'В БОЙ',dest:me.battle?'fight':'map'}):me.skill_points>0?{title:'ПРОКАЧАЙ ГЕРОЯ',description:`У тебя ${me.skill_points} свободных очков навыков. Улучшай стиль боя.`,action:'ТАЛАНТЫ',dest:'talents'}:{title:'ИССЛЕДУЙ ПУСТОШЬ',description:'Ищи припасы, побеждай новые виды заражённых и помогай клану.',action:'ЭКСПЕДИЦИЯ',dest:'map'};return `${me.encounter_pending?`<div class="panel"><h3>⚠ НЕОКОНЧЕННАЯ ВСТРЕЧА</h3><p>В пустоши ждут твоего решения. Заверши встречу, прежде чем отправиться дальше.</p>${btn('ПРИНЯТЬ РЕШЕНИЕ','nav','gold','encounters')}</div>`:''}<div class="hero"><div class="hero-text"><div class="eyebrow">// СВОДКА УБЕЖИЩА</div><h1>МИР ПАЛ.<br>ТЫ ЕЩЁ НЕТ.</h1><p>За стенами убежища нет правил. Только выбор, который ты делаешь сегодня.</p>${btn('ВЫЙТИ В ПУСТОШЬ ↗','nav','gold','map')}</div><div class="hero-visual">${art(me.class||'soldier')}</div></div><div class="next-objective"><div class="next-objective-icon">${icon('target')}</div><div><small>ТВОЯ СЛЕДУЮЩАЯ ЦЕЛЬ</small><h3>${esc(goal.title)}</h3><p>${esc(goal.description)}</p></div>${btn(goal.action,'nav','small gold',goal.dest)}</div>${miniStats()}<div class="talent-promo"><div><span class="eyebrow">// ПЕРСОНАЛЬНЫЙ ПРОГРЕСС</span><h3>Стань легендой пустоши</h3><p>Три уникальных пути развития для твоего класса. ${me.skill_points?`<b class="gold-text">Доступно ${me.skill_points} очк.</b>`:'Открывай умения с каждым уровнем.'}</p></div>${btn('ДЕРЕВО ТАЛАНТОВ ↗','nav','gold','talents')}</div>${section('ВЫЖИВАНИЕ','ОБСТАНОВКА')}<div class="grid"><div class="card"><div class="card-icon">⌖</div><h3>${esc(near.name)}</h3><p>Текущая позиция. Опасность: ${near.threat}/5</p>${btn('Искать припасы','scavenge','ghost','',me.location==='base'||!!me.battle)}</div><div class="card"><div class="card-icon">☣</div><h3>Охота на заражённых</h3><p>Исследуй окраины и получай добычу</p>${btn(me.battle?'Продолжить бой':'Вступить в бой',me.battle?'nav':'combat-start','red',me.battle?'fight':'',me.location==='base'&&!me.battle)}</div><div class="card"><div class="card-icon">✹</div><h3>Ежедневные припасы</h3><p>Забирай набор выжившего каждый день</p>${btn('Забрать набор','daily','soft','',me.last_daily===new Date().toISOString().slice(0,10))}</div><div class="card"><div class="card-icon">♛</div><h3>Мировой босс</h3><p>Каждые три дня новая угроза. Участвуй в общем сражении.</p>${btn('К мировому боссу','nav','soft','boss')}</div></div><div class="panel story-home-link"><div class="flex-between"><div><span class="eyebrow">// ПРОТОКОЛ СЕДЬМОЙ</span><h3>📻 ИСТОРИЯ ПУСТОШИ</h3><p class="smallnote">10 сюжетных глав: разведка, опасные встречи и решения с последствиями.</p></div>${btn('ИГРАТЬ','nav','small gold','story')}</div></div>${section('ЗАДАНИЯ','НАГРАДЫ')}<div class="panel"><div class="flex-between"><div><b>Пора делать историю</b><p class="smallnote">Основные задания, развитие и награды</p></div>${btn('Открыть','nav','gold','quests')}</div></div><div class="footer">ZOMBO · TRANSMISSION 001 · END</div>`}
function map(){if(me.battle)return fight();let chosen=(territories||[]).find(t=>t.id===selectedTerritory);return `${me.encounter_pending?`<div class="panel"><h3>⚠ РЕШЕНИЕ НЕ ПРИНЯТО</h3><p>Сначала заверши случайную встречу.</p>${btn('К ВСТРЕЧЕ','nav','gold','encounters')}</div>`:''}${section('КАРТА ПУСТОШИ','ТЕРРИТОРИИ И ЗАРАЖЁННЫЕ')}${territoryMap(territories||[])}${chosen?`<div class="map-selected"><span class="tag">${icon('shield')} ${chosen.clan_id?'КОНТРОЛЬ КЛАНА':'КОНТРОЛЬ ЗОМБИ'}</span><h3>${esc(chosen.name)}</h3><p>Владелец: <b>${esc(chosen.clan_id?chosen.owner:'Зомби')}</b></p>${btn('КЛАНОВЫЕ ВОЙНЫ','nav','small gold','clan')}</div>`:''}${section('ЛОКАЦИИ','ВЫБЕРИ ТОЧКУ')}<div class="map-location-list">${Object.entries(cfg.locations).map(([id,l])=>`<div class="location-card compact ${id===me.location?'active':''}"><div class="map-location-body"><div class="location-icon">${icon(id==='base'?'home':'map')}</div><div><div class="tag">${id===me.location?'ТЫ ЗДЕСЬ':`УРОВЕНЬ ${l.min_level}+`}</div><h3>${esc(l.name)}</h3><p>Опасность ${l.threat}/5 · ${esc(l.desc)}</p></div></div>${btn(id===me.location?'ЗДЕСЬ':me.level<l.min_level?'ЗАКРЫТО':'ИДТИ','travel','small gold',id,id===me.location||me.level<l.min_level)}</div>`).join('')}</div>${me.location!=='base'?`<div class="panel mt"><b>Зона: ${esc(cfg.locations[me.location].name)}</b><div class="actions">${btn('НАЧАТЬ БОЙ','combat-start','red')}${btn('ИСКАТЬ РЕСУРСЫ','scavenge','gold','',!!me.encounter_pending)}${btn(me.encounter_pending?'ЗАВЕРШИТЬ ВСТРЕЧУ':'ИССЛЕДОВАТЬ ОКРЕСТНОСТИ',me.encounter_pending?'nav':'encounter-explore','soft',me.encounter_pending?'encounters':'')}</div></div>`:''}<div class="map-bestiary-link">${icon('skull')} В пустоши обитают 10 видов врагов. ${btn('БЕСТИАРИЙ','nav','small ghost','bestiary')}</div>`}

function mobPortrait(id){const key=/^[a-z_]{1,18}$/.test(id||'')?id:'walker';return `<img class="mob-portrait" src="/static/mobs/${key}.svg" alt="${esc(cfg.enemies?.[key]?.name||'Заражённый')}" draggable="false" loading="eager">`}
function eliteBanner(b){return b.elite?`<div class="elite-banner"><strong>ЭЛИТНАЯ ЦЕЛЬ · ${esc(b.elite.name)}</strong><span>${esc(b.elite.hint)}</span><small>Усиленный враг · больше опыта и крышек · повышенный шанс снаряжения</small></div>`:''}
function fight(){
  const b=me.battle,mob=cfg.enemies?.[b?.enemy_id]||{};
  if(!b)return `${section('СТОЛКНОВЕНИЕ','ТАКТИЧЕСКИЙ БОЙ')}<div class="empty"><strong>Противников поблизости нет</strong>Вернись к исследованию</div>${btn('Карта','nav','gold','map')}`;
  const canAttack=me.stamina>=2;
  const equippedGun=(me.gear||[]).find(g=>g.equipped&&g.ammo_key);
  const legendaryStock=(me.inventory||[]).find(i=>i.key==='legendary_ammo'&&!i.equipped)?.qty||0;
  const recent=b.turn>0?`<div class="fight-recent"><strong>ПОСЛЕДНИЙ ХОД</strong>${b.log.slice(-2).map(x=>`<span>${esc(x)}</span>`).join('')}</div>`:'';
  return `${section('СТОЛКНОВЕНИЕ','ТАКТИЧЕСКИЙ БОЙ')}<div class="enemy-art fight-screen mob-combat"><div class="combat-tag">${icon('skull')} ЗАРАЖЁННЫЙ · УГРОЗА ${b.tier||1}/5</div>${eliteBanner(b)}<div class="monster"><button type="button" class="mob-tap" data-action="fight-tap" aria-label="Ударить заражённого в корпус, 2 энергии" title="Удар в корпус · 2 энергии" ${canAttack?'':'disabled'}>${mobPortrait(b.enemy_id)}</button></div><div class="tap-hint">${canAttack?'НАЖМИ НА ЗАРАЖЁННОГО · УДАР В КОРПУС · ϟ 2':'НЕ ХВАТАЕТ ЭНЕРГИИ ДЛЯ УДАРА'}</div><h2>${esc(b.enemy)}</h2><p class="mob-description">${esc(b.lore||'Враг приближается')}</p><div class="mob-combat-trait">${esc(mob.skill||b.skill||'Обычная атака')}</div><div class="battle-tactic">${icon('shield')} ${esc(b.tactics||'Наблюдай за противником и используй защиту.')}</div>${b.incoming_special?`<div class="battle-warning">${icon('swords')} СЛЕДУЮЩИЙ ХОД — ${esc(b.elite_warning||b.skill||'ОСОБАЯ АТАКА').toUpperCase()} · ЗАЩИЩАЙСЯ!</div>`:''}<div class="battle-hp"><div class="bar-label"><span>Здоровье врага</span><em>${b.hp} / ${b.max_hp}</em></div>${bar(b.hp,b.max_hp,'red')}</div></div>${recent}<div class="panel mt fight-actions-panel"><div class="bar-label"><span>Твоё здоровье</span><em>${me.hp} / ${me.max_hp}</em></div>${bar(me.hp,me.max_hp,'red')}<div class="bar-label"><span>Энергия</span><em>${me.stamina} / 500</em></div>${bar(me.stamina,500,'blue')}${equippedGun?`<div class="fight-ammo ${legendaryStock>0?'':'empty'}"><span>✧ ЛЕГЕНДАРНЫЙ БОЕЗАПАС</span><strong>${legendaryStock} шт.</strong><small>${legendaryStock?'1 патрон на выстрел':'Без патронов — атака без бонуса легендарной пушки. Торговец / Мастерская'}</small></div>`:''}<div class="section-label">КУДА ЦЕЛИШЬСЯ?</div><div class="zones">${[['head','Голова ×1.5'],['body','Тело ×1'],['legs','Ноги ×0.7']].map(([k,l])=>`<button type="button" class="${zone===k?'active':''}" data-action="zone" data-value="${k}" aria-pressed="${zone===k}">${l}</button>`).join('')}</div><p class="fight-zone-hint">Кнопка атаки бьёт в выбранную область. Касание зомби всегда бьёт в корпус.</p><div class="actions">${btn('АТАКОВАТЬ · ϟ 2','fight-act','red','attack',!canAttack)}${btn('ЗАЩИТА','fight-act','soft','defend')}</div><div class="actions">${btn('АПТЕЧКА','fight-act','soft','medkit')}${btn('ОТСТУПИТЬ','fight-act','ghost','flee')}</div></div>${me.pet?`<div class=\"panel\">${btn(me.pet.icon+' '+me.pet.ability+' · 3ϟ','fight-act','soft full','pet',!b.pet_available||me.stamina<3)}</div>`:''}${knownAbilities()}${section('ХРОНИКА БОЯ')}<div class="combatlog">${b.log.map(x=>`<div>${esc(x)}</div>`).join('')}</div>`;
}
function showTapResult(message){
  const target=document.querySelector('.mob-tap');
  if(!target)return;
  const damage=/:\s*(\d+)\s+урона/.exec(message||'')?.[1];
  target.classList.add('hit-confirmed');
  const label=document.createElement('span');
  label.className='tap-damage'+(damage==='0'?' missed':'');
  label.textContent=damage==='0'?'ПРОМАХ':damage?`−${damage}`:'УДАР';
  target.append(label);
  setTimeout(()=>{target.classList.remove('hit-confirmed');label.remove()},750);
}

function talentRanks(){return me.talent_ranks||{}}
function talentRank(n){return Number(talentRanks()[n.key]||0)}
function talentEligible(n){return talentRank(n)<n.max_rank&&me.level>=n.min_level&&(!n.requires||(talentRanks()[n.requires]||0)>=n.required_rank)}
function talentValue(n){const value=n.per_rank;
 if(n.effect==='ability')return 'АКТИВНОЕ УМЕНИЕ';
 if(['health','regen'].includes(n.effect))return '+'+value+' за ранг';
 return '+'+Math.round(value*100)+'% за ранг';}
function knownAbilities(){const nodes=(cfg.skill_trees?.[me.class]||[]).flatMap(b=>b.nodes).filter(n=>n.kind==='active'&&talentRank(n));
 if(!nodes.length)return `<div class="talent-combat-hint">✦ Активные приёмы появятся здесь после изучения в дереве талантов. ${btn('ОТКРЫТЬ ДЕРЕВО','nav','ghost','talents')}</div>`;
 return `<div class="talent-fight-panel"><div class="eyebrow">// ОСОБЫЕ ПРИЁМЫ</div><div class="talent-fight-actions">${nodes.map(n=>{let cooldown=me.battle?.ability_cooldowns?.[n.key]||0;return `<button class="talent-fight-btn" data-action="fight-skill" data-value="${esc(n.key)}" ${cooldown||me.stamina<6?'disabled':''}><span>${n.icon}</span><strong>${esc(n.name)}</strong><small>${cooldown?`⏳ ${cooldown} ход.`:'ϟ 6 · Ранг '+talentRank(n)}</small></button>`}).join('')}</div></div>`}
function talentsScreen(){const branches=cfg.skill_trees?.[me.class]||[];
 const branch=branches[Math.min(activePath,branches.length-1)];if(!branch)return '';
 const ranks=talentRanks();const totalSpent=me.talent_spent||0;
 const extra=Object.entries(me.talent_bonuses||{}).filter(([key,val])=>val>0&&key!=='ability');
 const bonusLabels={power:'Урон',crit:'Криты',mitigation:'Защита',armor:'Броня',health:'Здоровье',healing:'Лечение',regen:'Регенерация',energy:'Энергия',boss:'Урон боссам',accuracy:'Точность',xp:'Опыт',loot:'Добыча',caps:'Крышки',scavenge:'Сбор припасов',execute:'Добивание',lifesteal:'Кража HP',dodge:'Уклонение'};
 return `<div class="talent-hero"><div class="eyebrow">// ДОСЬЕ / СПЕЦИАЛИЗАЦИЯ</div><h1>ДЕРЕВО<br><span>ТАЛАНТОВ</span></h1><div class="talent-class">${esc(cfg.classes[me.class]?.name||'Выживший')} · Ур. ${me.level}</div><div class="talent-score"><div><strong>${me.skill_points}</strong><small>СВОБОДНЫХ ОЧКОВ</small></div><div><strong>${totalSpent}</strong><small>ВЛОЖЕНО ОЧКОВ</small></div></div></div>
 <div class="talent-intro"><strong>Выбери свой путь</strong><p>В каждом пути три навыка с тремя рангами. Развилки можно развивать параллельно. Новые очки: каждые 2 уровня, бонусные — каждые 5 уровней.</p></div>
 <div class="talent-path-tabs">${branches.map((b,i)=>{let spent=b.nodes.reduce((x,n)=>x+(ranks[n.key]||0),0);return `<button class="talent-path-tab ${activePath===i?'active':''}" data-action="talent-path" data-value="${i}"><span>${b.icon}</span><strong>${esc(b.name)}</strong><small>${spent}/9</small></button>`}).join('')}</div>
 <div class="talent-path-header"><div class="talent-path-symbol">${branch.icon}</div><div><span class="eyebrow">// ВЕТКА ${Number(activePath)+1} / 3</span><h2>${esc(branch.name)}</h2><p>${esc(branch.description)}</p></div></div>
 <div class="talent-track">${branch.nodes.map((n,i)=>{const rank=talentRank(n);const max=rank>=n.max_rank;const eligible=talentEligible(n);const locked=!eligible&&!max;const req=n.requires?(cfg.skill_trees[me.class][activePath].nodes.find(v=>v.key===n.requires)?.name||n.requires):'';const active=n.kind==='active';const needLevel=me.level<n.min_level;
 return `<div class="talent-node ${rank?'learned':''} ${locked?'locked':''} ${active?'ability':''}"><div class="talent-rail"><div class="talent-rail-icon">${rank? n.icon : '♙'}</div>${i<2?'<div class="talent-rail-line"></div>':''}</div><div class="talent-node-content"><div class="talent-node-top"><span class="eyebrow">СТУПЕНЬ 0${i+1} · ${active?'АКТИВНЫЙ':'ПАССИВНЫЙ'}</span><span class="talent-node-rank">РАНГ ${rank}/${n.max_rank}</span></div><h3>${esc(n.name)}</h3><p>${esc(n.description)}</p><div class="talent-effect">${active?'✹':'✦'} ${talentValue(n)}</div><div class="talent-rank-bars">${Array.from({length:n.max_rank},(_,j)=>`<span class="${j<rank?'filled':''}"></span>`).join('')}</div><div class="talent-node-footer">${max?'<span class="talent-requirement done">✓ МАКСИМАЛЬНЫЙ РАНГ</span>':needLevel?`<span class="talent-requirement">🔒 ОТКРОЕТСЯ НА УР. ${n.min_level}</span>`:n.requires&&(ranks[n.requires]||0)<n.required_rank?`<span class="talent-requirement">🔒 ${esc(req)} · РАНГ ${n.required_rank}</span>`:`<span class="talent-requirement done">✓ ДОСТУПЕН</span>`}${btn(max?'ИЗУЧЕНО':rank?'УЛУЧШИТЬ':'ИЗУЧИТЬ','skill','small '+(eligible&&me.skill_points?'gold':'ghost'),n.key,max||!eligible||me.skill_points<1)}</div></div></div>`}).join('')}</div>
 <div class="panel talent-summary"><h3>ТВОИ УСИЛЕНИЯ</h3>${extra.length?`<div class="talent-perks">${extra.map(([key,val])=>`<div><span>${bonusLabels[key]||key}</span><strong>+${['health','regen'].includes(key)?Number(val):Math.round(Number(val)*100)+'%'}</strong></div>`).join('')}</div>`:'<p class="smallnote">Пока нет пассивных усилений. Выбери начальный талант, чтобы изменить характеристики.</p>'}</div>
 <div class="talent-reset"><div><strong>Переосмыслить путь</strong><p>Вернём все вложенные очки. ${me.talent_reset_cost?'Стоимость: '+money(me.talent_reset_cost)+' крышек.':'Первый сброс бесплатный.'}</p></div>${btn('↺ СБРОСИТЬ','skill-reset','ghost','',!me.talent_spent||me.caps<me.talent_reset_cost)}</div>${btn('← К ПЕРСОНАЖУ','nav','ghost full','profile')}`}
function profile(){let klass=cfg.classes[me.class];return `<div class="profilehead"><div class="portrait">${art(me.class)}</div><div class="profile-meta"><span class="eyebrow">ДОСЬЕ ВЫЖИВШЕГО</span><h1>${esc(me.name)}</h1><p>${klass?.icon||''} ${klass?.name||'Новичок'} · Уровень ${me.level}</p><div class="chips"><span class="chip gold">♛ ${me.rating} ELO</span><span class="chip">☣ ${me.kills} убийств</span></div></div></div>${miniStats()}<div class="talent-promo profile-talent-link"><div><span class="eyebrow">// РАЗВИТИЕ ПЕРСОНАЖА</span><h3>✦ УНИКАЛЬНЫЕ НАВЫКИ</h3><p>Три ветки талантов с активными приёмами и улучшениями рангов. ${me.skill_points?`<b class="gold-text">Свободно очков: ${me.skill_points}</b>`:''}</p></div>${btn('ПРОКАЧАТЬ ↗','nav','gold','talents')}</div>${section('ХАРАКТЕРИСТИКИ',`ОЧКОВ: ${me.stat_points}`)}<div class="panel">${Object.entries(cfg.stats).map(([key,label])=>`<div class="statline"><div><strong>${label}</strong><br><small>${({strength:'Сила удара',agility:'Крит и маневренность',endurance:'Макс. HP +5',accuracy:'Точность +0.5%',regen:'Восстановление здоровья',luck:'Поиск редкой добычи'})[key]}</small></div><strong>${me.stats[key]}</strong>${btn('+','stat','ghost',key,me.stat_points<1)}</div>`).join('')}</div><div class="panel gear-profile-link"><div class="flex-between"><div><strong>⚔ Арсенал выжившего</strong><p class="smallnote">${(me.gear||[]).length} уникальных предметов, усиление оружия и брони.</p></div>${btn('ОТКРЫТЬ','nav','small gold','gear')}</div></div>${section('СНАРЯЖЕНИЕ','СПИСОК ПРЕДМЕТОВ')}${inventory()}`}

function gearScreen(){
 const gear=(me.gear||[]),statistics=me.gear_stats||{power:0,defense:0};
 const equipped=gear.filter(g=>g.equipped);
 const visible=gear.filter(g=>gearSlotFilter==='all'||g.slot===gearSlotFilter).slice().sort((a,b)=>{
   if(gearSort==='rarity')return b.rarity_rank-a.rarity_rank||b.level-a.level||b.id-a.id;
   if(gearSort==='power')return (b.slot==='weapon'?b.power:b.defense)-(a.slot==='weapon'?a.power:a.defense)||b.rarity_rank-a.rarity_rank;
   if(gearSort==='worn')return a.durability-b.durability||b.id-a.id;
   return Number(b.equipped)-Number(a.equipped)||b.rarity_rank-a.rarity_rank||b.id-a.id;
 });
 const invcount=(key)=>(me.inventory||[]).filter(i=>i.key===key&&!i.equipped).reduce((n,i)=>n+i.qty,0);
 const bySlot=slot=>equipped.find(g=>g.slot===slot);
 const slotLine=(slot,label,empty)=>{const g=bySlot(slot);return `<div class="gear-slot"><span class="gear-slot-icon">${g?esc(g.icon):slot==='weapon'?'⚔':'⬡'}</span><div><small>${label}</small><strong>${g?esc(g.name)+' +'+g.level:empty}</strong>${g?`<span style="color:${g.color}">${esc(g.rarity_name)}</span>`:''}</div><b>${g?(slot==='weapon'?'⚔ '+g.power:'⛨ '+g.defense):'—'}</b></div>`};
 const repairable=equipped.filter(g=>g.repair_cost);
 const fullCost=repairable.reduce((sum,g)=>{
   const r=g.repair_cost;sum.caps+=r.caps;
   sum.materials[r.material]=(sum.materials[r.material]||0)+r.qty;
   if(r.rare)sum.materials.rare=(sum.materials.rare||0)+r.rare;
   return sum;
 },{caps:0,materials:{}});
 const canRepairAll=me.caps>=fullCost.caps&&Object.entries(fullCost.materials).every(([key,qty])=>invcount(key)>=qty);
 const box=g=>{const c=g.upgrade_cost,r=g.repair_cost,canUp=c&&me.caps>=c.caps&&invcount(c.material)>=c.qty&&invcount('rare')>=c.rare;
 const canRepair=r&&me.caps>=r.caps&&invcount(r.material)>=r.qty&&invcount('rare')>=r.rare;
 const current=equipped.find(item=>item.slot===g.slot),delta=current&&!g.equipped?(g.slot==='weapon'?g.power-current.power:g.defense-current.defense):null;
 const legendaryAmmo=g.ammo_key?`<p class="gear-ammo">✧ Легендарные патроны: <b>${invcount(g.ammo_key)}</b> · 1 на атаку. Без патронов пушка не даёт бонус урона.</p>`:'';
 return `<div class="gear-card ${g.equipped?'gear-equipped':''}" data-search-group="gear" data-search="${esc((g.name+' '+g.key+' '+g.rarity_name+' '+g.slot).toLowerCase())}" style="--rarity:${esc(g.color)}"><div class="gear-item-top"><div class="gear-item-art">${esc(g.icon)}</div><div class="gear-item-title"><span class="gear-rarity">${esc(g.rarity_name)} · ${g.slot==='weapon'?'ОРУЖИЕ':'БРОНЯ'}</span><h3>${esc(g.name)} <span>+${g.level}</span></h3><p>${g.slot==='weapon'?'Урон: '+g.power:'Броня: '+g.defense} ${g.equipped?' · НАДЕТО':''}${g.exclusive?' · ТОЛЬКО ИЗ КЕЙСА':''}</p><p class="smallnote">${g.durability<=0?'⚠ СЛОМАНО':'🔧 ПРОЧНОСТЬ'}: ${g.durability}/100 · ${g.durability<40?'снижены характеристики':'полная эффективность'}</p>${legendaryAmmo}${delta!==null?`<p class="gear-compare ${delta>=0?'good':'bad'}">↔ Относительно надетого: ${delta>=0?'+':''}${delta} ${g.slot==='weapon'?'к урону':'к броне'}</p>`:''}</div></div><div class="gear-rank-track">${Array.from({length:10},(_,i)=>`<span class="${i<g.level?'done':''}"></span>`).join('')}</div>
 ${r?`<p class="gear-cost">Ремонт: 🪙 ${money(r.caps)} · ${esc(cfg.items[r.material]?.icon||'⚙')} ${r.qty}${r.rare?' · 🏅 '+r.rare:''}</p>`:''}
 ${c?`<p class="gear-cost">Улучшение +${g.level+1}: 🪙 ${money(c.caps)} · ${esc(cfg.items[c.material]?.icon||'⚙')} ${c.qty}${c.rare?' · 🏅 '+c.rare:''}</p>`:'<p class="gear-cost">✦ Максимальный уровень улучшения!</p>'}
 <div class="gear-actions">${btn(g.equipped?'СНЯТЬ':'НАДЕТЬ',g.equipped?'gear-unequip':'gear-equip','small '+(g.equipped?'ghost':'gold'),g.id)}${btn('УЛУЧШИТЬ','gear-upgrade','small soft',g.id,!canUp)}${btn('ПОЧИНИТЬ','gear-repair','small gold',g.id,!canRepair)}${btn('РАЗОБРАТЬ','gear-dismantle','small ghost',g.id,g.equipped)}</div></div>`};
 return `${section('АРСЕНАЛ ПУСТОШИ','УНИКАЛЬНАЯ ЭКИПИРОВКА')}<div class="gear-hero"><div class="eyebrow">// ОРУЖЕЙНЫЙ ОТСЕК</div><h1>ВЫЖИВАЙ<br><span>СИЛЬНЕЕ.</span></h1><p>Найди редкое оружие в боях и рейдах, собери комплект и прокачай его до +10.</p><div class="gear-hero-stats"><div><small>ОРУЖИЕ</small><b>+${statistics.power||0}</b></div><div><small>БРОНЯ</small><b>+${statistics.defense||0}</b></div><div><small>НА СКЛАДЕ</small><b>${gear.length}/80</b></div></div></div>
 ${section('НАДЕТО','БОЕВЫЕ СЛОТЫ')}<div class="gear-equipped-panel">${slotLine('weapon','ОСНОВНОЕ ОРУЖИЕ','Без уникального оружия')}${slotLine('armor','ЗАЩИТА','Без уникальной брони')}</div>
 ${repairable.length?`<div class="panel gear-repair-batch"><div class="flex-between"><div><h3>🔧 Ремонт комплекта</h3><p class="smallnote">${repairable.length} предметов · ${money(fullCost.caps)} крышек · ${Object.entries(fullCost.materials).map(([key,n])=>esc(cfg.items[key]?.name||key)+' ×'+n).join(', ')}</p></div>${btn('ПОЧИНИТЬ ВСЁ','gear-repair-all','small gold','',!canRepairAll)}</div>${!canRepairAll?'<p class="smallnote">Недостаточно крышек или материалов. Ничего не будет списано.</p>':''}</div>`:''}
 ${section('КОЛЛЕКЦИЯ',`${gear.length} ПРЕДМЕТОВ`)}<div class="panel item-filters">${searchBox('gear',gearQuery,'ПОИСК В АРСЕНАЛЕ')}${filterTabs('gear-filter',gearSlotFilter,[['all','Всё'],['weapon','Оружие'],['armor','Броня']])}<label class="search-label" for="gear-sort">СОРТИРОВКА</label><select id="gear-sort"><option value="equipped" ${gearSort==='equipped'?'selected':''}>Сначала надетое</option><option value="rarity" ${gearSort==='rarity'?'selected':''}>По редкости</option><option value="power" ${gearSort==='power'?'selected':''}>По силе</option><option value="worn" ${gearSort==='worn'?'selected':''}>По износу</option></select></div>${gear.length?`<div class="gear-collection">${visible.map(box).join('')}${!visible.length?'<div class="empty">В категории пока нет вещей.</div>':''}</div><div class="empty search-empty" data-filter-empty="gear" hidden>Ничего не найдено.</div>`:`<div class="panel gear-empty"><h3>Пока пусто</h3><p>Ищи снаряжение в боях с заражёнными, проходи групповые рейды или создавай его в мастерской.</p>${btn('НА КАРТУ','nav','gold','map')}${btn('К МАСТЕРСКОЙ','nav','ghost','craft')}</div>`}
 <div class="panel gear-help"><h3>Как работает снаряжение?</h3><p><b>Обычное → Необычное → Редкое → Эпическое → Легендарное.</b> Больше редкость — сильнее базовые характеристики. Улучшение до +10 расходует крышки и материалы, на уровнях +5, +8 и +10 нужны военные жетоны. Экипировка изнашивается при атаках и ударах врага. При прочности меньше 40 снижаются параметры, при 0 бонус равен нулю. Ремонт за крышки и материалы восстанавливает 100%. Особые пушки доступны только из кейсов. Ненужную вещь можно разобрать, но экипированные предметы разбирать нельзя. Старое снаряжение остаётся доступным в рюкзаке.</p></div>`;
}
// One backpack presentation for both ItemStack consumables and unique GearItem.
// Gear remains stored in its own table to keep unique IDs, levels and durability.
function ownedInventory(){
 const stacks=(me.inventory||[]).map(item=>({...item,isUniqueGear:false}));
 const unique=(me.gear||[]).map(g=>({
   ...g,type:g.slot,qty:1,isUniqueGear:true,
   desc:`${g.rarity_name} · +${g.level} · ${g.slot==='weapon'?'Урон: '+g.power:'Броня: '+g.defense} · Прочность ${g.durability}/100`
 }));
 return [...unique,...stacks];
}
function inventory(filtered=false){
 const items=ownedInventory().filter(item=>!filtered||inventoryFilter==='all'||
   (inventoryFilter==='unique'?item.isUniqueGear:itemKind(item)===inventoryFilter));
 return `<div class="list inventory-list">${items.map(i=>{
  const search=`${i.name||''} ${i.key||''} ${i.desc||''} ${i.rarity_name||''}`.toLowerCase();
  const unique=i.isUniqueGear;
  return `<div class="row ${unique?'inventory-unique':''}" ${filtered?`data-search-group="inventory" data-search="${esc(search)}"`:''}>
   <div class="symbol">${esc(i.icon)}</div><div class="row-main">
     <h3>${esc(i.name)} ${unique?`<span class="badge" style="color:${esc(i.color||'#e6c48e')}">${esc(i.rarity_name)} +${i.level}</span>`:`<span class="badge">×${i.qty}</span>`}</h3>
     <p>${esc(i.desc||i.type||'Ресурс для выживания')}${unique?' · Уникальный экземпляр':''}</p>
   </div>
   ${unique?btn(i.equipped?'НАДЕТО ↗':'К ПУШКЕ ↗','nav','small gold','gear'):i.equipped?'<span class="badge">Надето</span>':i.type==='consumable'?btn('Использовать','use','small gold',i.key):i.type==='case'?btn('ОТКРЫТЬ','case-open','small gold',i.key):i.type==='chest'?btn('ОТКРЫТЬ','chest-open','small gold',i.key):['weapon','armor'].includes(i.type)?btn('Надеть','equip','small ghost',i.key):''}
 </div>`;
 }).join('')||'<div class="empty">В этой категории пока нет предметов</div>'}</div>${filtered?'<div class="empty search-empty" data-filter-empty="inventory" hidden>Ничего не найдено. Попробуй другой запрос.</div>':''}`;
}
function bestiaryScreen(){const enemies=cfg.enemies||{},codex=me.enemy_codex||{};const total=Object.keys(codex).length,defeated=Object.values(codex).filter(x=>x.kills>0).length;
 return `${section('ПОЛЕВОЙ БЕСТИАРИЙ',`${total}/10 ОБНАРУЖЕНО`)}<div class="codex-summary"><div><span class="eyebrow">АРХИВ ЗАРАЖЁННЫХ</span><h3>${total} обнаружено · ${defeated} побеждено</h3><p>Первая победа над новым видом: +25 XP и +15 крышек. Собери все десять досье.</p></div>${icon('book')}</div><div class="bestiary-grid">${Object.entries(enemies).map(([id,m])=>{const entry=codex[id]||{},seen=!!entry.seen;return `<article class="bestiary-card ${seen?'seen':'undiscovered'}"><div class="bestiary-portrait">${mobPortrait(id)}</div><div class="bestiary-rank">${seen?'ВСТРЕЧЕН':'НЕИЗВЕСТЕН'} · РАНГ ${m.tier}/5</div><h3>${esc(m.name)}</h3><p>${seen?esc(m.lore):'Не обнаружен. Исследуй более опасные локации.'}</p>${seen?`<div class="bestiary-ability">${icon('target')} ${esc(m.skill)}</div><div class="bestiary-counter">Побед: <b>${Number(entry.kills)||0}</b> · ${Number(entry.kills)>0?'ДОСЬЕ ЗАКРЫТО':'ТРОФЕЙ НЕ ПОЛУЧЕН'}</div>`:`<div class="bestiary-ability muted">${icon('target')} Приём неизвестен</div>`}</article>`}).join('')}</div>${btn('НА КАРТУ','nav','gold full','map')}`}
function raidScreen(){
 if(!raids)return `<div class="panel">Загружаем рейды…</div>`;
 const current=raids.my_raid,scenarios=raids.scenarios||{}, recent=raids.recent||[];
 const member=current?.members.find(m=>m.id===me.id);
 const canAct=current?.status==='active'&&member?.hp>0&&(!member.next_action_at||Date.now()>=new Date(member.next_action_at).getTime());
 return `${section('ГРУППОВЫЕ РЕЙДЫ','3–10 ИГРОКОВ')}
 <div class="raid-lead"><div class="eyebrow">// ЭКСПЕДИЦИИ В ПУСТОШЬ</div><h1>ОДИН ТЫ НЕ ВЫЖИВЕШЬ</h1><p>Собери отряд, пройди три этапа и получи добычу. В каждом столкновении важны твои характеристики, оружие и решения команды.</p><div class="raid-meta"><span>⚔ 3 этапа</span><span>👥 3–10 выживших</span><span>🏆 Опыт + крышки + лут</span></div></div>
 ${current?`<div class="raid-active"><div class="flex-between"><span class="tag">${current.status==='lobby'?'СБОР ОТРЯДА':'РЕЙД ИДЁТ'}</span><span class="tag">№ ${current.id}</span></div><h2>${esc(current.name)}</h2><div class="raid-stage">ЭТАП ${current.stage}/3 <span>· ${esc(current.enemy)}</span></div>${current.status==='active'?`<div class="bar-label"><span>Здоровье врага</span><em>${money(current.hp)} / ${money(current.max_hp)}</em></div>${bar(current.hp,current.max_hp,'red')}`:''}<div class="raid-deadline">⏳ Время завершения: ${new Date(current.expires_at).toLocaleString('ru-RU')}</div><div class="raid-roster">${current.members.map(m=>`<div class="raid-member ${m.hp<=0?'out':''}"><span>${m.hp<=0?'☠':'🛡'}</span><div><strong>${esc(m.name)}</strong><small>${m.hp}/${m.max_hp} HP · Урон ${money(m.contribution)}</small></div></div>`).join('')}</div>
 ${current.status==='lobby'?`<p class="smallnote">Для запуска необходимо минимум 3 участника. Пригласи других игроков найти группу №${current.id}.</p><div class="actions">${btn('НАЧАТЬ РЕЙД','raid-launch','gold',current.id,me.id!==current.leader_id||current.member_count<3)}${btn('ПОКИНУТЬ','raid-leave','ghost',current.id)}</div>`:
 `<div class="raid-abilities"><h3>БОЕВЫЕ ДЕЙСТВИЯ</h3><div class="actions">${btn('⚔ АТАКА · 6⚡','raid-act','red','attack',!canAct||me.stamina<6)}${btn('🛡 ЗАЩИТА · 3⚡','raid-act','soft','guard',!canAct||me.stamina<3)}</div><div class="actions">${btn('✚ АПТЕЧКА · 3⚡','raid-act','soft','medkit',!canAct||me.stamina<3||member?.hp>=member?.max_hp)}</div>${me.class==='medic'?current.members.filter(m=>m.hp<=0).map(m=>btn('✚ ПОДНЯТЬ '+esc(m.name),'raid-rescue','gold full',m.id,!canAct||me.stamina<5)).join(''):''}</div>`}
 ${current.log?.length?`<details class="raid-chronicle"><summary>Журнал экспедиции (${current.log.length})</summary>${current.log.map(s=>`<div>${esc(s)}</div>`).join('')}</details>`:''}${btn('↻ ОБНОВИТЬ','refresh','ghost full')}
 </div>`:''}
 ${!current?`${section('ДОСТУПНЫЕ ОПЕРАЦИИ','3 РЕЙДА')}<div class="raid-scenario-grid">${Object.entries(scenarios).map(([key,r])=>`<div class="raid-scenario"><div class="raid-scenario-icon">${r.icon}</div><h3>${esc(r.name)}</h3><p>${esc(r.desc)}</p><div class="raid-scenario-meta"><span>Ур. ${r.level}+</span><span>⏱ ${r.duration_hours} ч.</span><span>⚔ 3 этапа</span></div>${btn('СОБРАТЬ ОТРЯД','raid-create','gold full',key,me.level<r.level)}</div>`).join('')}</div>`:''}
 ${section('ОТКРЫТЫЕ ГРУППЫ','ЗАПИСЬ В РЕЙДЫ')}<div class="list">${(raids.lobbies||[]).map(r=>`<div class="row"><div class="symbol">👥</div><div class="row-main"><h3>${esc(r.name)} · №${r.id}</h3><p>${r.member_count}/10 бойцов · Лидер #${r.leader_id}</p></div>${!current?btn('ВСТУПИТЬ','raid-join','small gold',r.id,me.level<scenarios[r.scenario]?.level):''}</div>`).join('')||'<div class="empty">Открытых отрядов пока нет. Создай свой!</div>'}</div>
 ${recent.length?`${section('ПРОШЕДШИЕ РЕЙДЫ','НАГРАДЫ')}<div class="list">${recent.map(r=>{const self=r.members.find(m=>m.id===me.id);return `<div class="row"><div class="symbol">${r.status==='cleared'?'🏆':'☠'}</div><div class="row-main"><h3>${esc(r.name)}</h3><p>${{cleared:'Зачищен',failed:'Провален',expired:'Время вышло'}[r.status]||r.status} · ${money(self?.contribution)} урона</p></div>${r.status==='cleared'&&self&&!self.rewarded?btn('НАГРАДА','raid-claim','small gold',r.id,self.actions<1):self?.rewarded?'<span class="badge">Получено</span>':''}</div>`}).join('')}</div>`:''}
 `;
}
function expeditionScreen(){
 if(!expeditions)return '<div class="panel">Загружаем экспедиции…</div>';
 const current=expeditions.my_run, scenarios=expeditions.scenarios||{}, roles=expeditions.roles||{};
 const mine=current?.members.find(m=>m.id===me.id), recent=expeditions.recent||[];
 return `${section('ДАЛЬНИЕ ЭКСПЕДИЦИИ','12 ЧАСОВ')}
 <div class="raid-lead"><div class="eyebrow">// ОПЕРАЦИИ ЗА ПРЕДЕЛАМИ КАРТЫ</div><h1>ОТРЯД УХОДИТ НА 12 ЧАСОВ</h1><p>Собери 3–10 выживших, распредели роли и отправь группу. Результат сохранится на сервере и будет доступен после возвращения.</p><div class="raid-meta"><span>⏱ 12 часов</span><span>👥 3–10 игроков</span><span>🏆 Уникальное снаряжение</span></div></div>
 ${current?`<div class="raid-active"><div class="flex-between"><span class="tag">${current.status==='lobby'?'СБОР И ПОДГОТОВКА':'ОТРЯД В ПУТИ'}</span><span class="tag">№ ${current.id}</span></div><h2>${esc(current.name)}</h2><p class="smallnote">${current.status==='lobby'?'Набор до '+new Date(current.lobby_expires_at).toLocaleString('ru-RU'):'Возвращение '+new Date(current.finishes_at).toLocaleString('ru-RU')}${current.success_chance!=null?' · Шанс успеха '+current.success_chance+'%':''}</p><div class="raid-roster">${current.members.map(m=>`<div class="raid-member"><span>${m.role?'◆':'◇'}</span><div><strong>${esc(m.name)}</strong><small>${m.role?esc(roles[m.role]):'Роль не выбрана'}${m.id===current.leader_id?' · Лидер':''}</small></div></div>`).join('')}</div>
 ${current.status==='lobby'?`<div class="panel mt"><h3>ТВОЯ РОЛЬ: ${mine?.role?esc(roles[mine.role]).toUpperCase():'НЕ ВЫБРАНА'}</h3><p class="smallnote">Разные роли повышают шанс успеха. Для старта нужны минимум две разные роли и подготовка каждого участника.</p><div class="actions">${Object.entries(roles).map(([key,name])=>btn(name,'exp-prepare',mine?.role===key?'gold':'soft',key)).join('')}</div></div><div class="actions">${btn('ОТПРАВИТЬ ОТРЯД','exp-launch','gold',current.id,me.id!==current.leader_id||current.member_count<3||current.members.some(m=>!m.role)||new Set(current.members.map(m=>m.role)).size<2)}${btn('ПОКИНУТЬ','exp-leave','ghost',current.id)}</div>`:''}${current.event?`<div class='panel mt'><span class='eyebrow'>// ИНЦИДЕНТ В ПУТИ</span><h3>${esc(current.event.title)}</h3><p class='smallnote'>${esc(current.event.description)}</p>${current.event.choice?`<p class='smallnote'>Решение: ${esc(current.event.choice_label)} · Награды ${current.event.reward_percent}% от базовых.</p>`:current.event.ready?me.id===current.leader_id?`<div class='actions'>${Object.entries(current.event.options).map(([key,option])=>btn(`${esc(option.text)} · ${esc(option.hint)}`,'exp-event',key==='cautious'?'gold':'soft',key)).join('')}</div>`:`<p class='smallnote'>Лидер выбирает решение. Ты увидишь его здесь.</p>`:`<p class='smallnote'>Выбор появится ${new Date(current.event.available_at).toLocaleString('ru-RU')}.</p>`}</div>`:''}${btn('↻ ОБНОВИТЬ','refresh','ghost full')}</div>`:''}
 ${!current?`${section('МАРШРУТЫ','ВЫБЕРИ ОПЕРАЦИЮ')}<div class="raid-scenario-grid">${Object.entries(scenarios).map(([key,r])=>`<div class="raid-scenario"><div class="raid-scenario-icon">⌖</div><h3>${esc(r.name)}</h3><p>${esc(r.desc)}</p><div class="raid-scenario-meta"><span>Ур. ${r.level}+</span><span>⏱ 12 ч.</span><span>🏆 ${esc(r.rarity)}</span></div>${btn('СОБРАТЬ ОТРЯД','exp-create','gold full',key,me.level<r.level)}</div>`).join('')}</div>`:''}
 ${section('ОТКРЫТЫЕ ГРУППЫ','ЗАПИСЬ')}<div class="list">${(expeditions.lobbies||[]).map(r=>`<div class="row"><div class="symbol">⌖</div><div class="row-main"><h3>${esc(r.name)} · №${r.id}</h3><p>${r.member_count}/10 выживших · Лидер #${r.leader_id}</p></div>${!current?btn('ВСТУПИТЬ','exp-join','small gold',r.id,me.level<scenarios[r.scenario]?.level):''}</div>`).join('')||'<div class="empty">Открытых групп пока нет.</div>'}</div>
 ${recent.length?`${section('ВЕРНУВШИЕСЯ ОТРЯДЫ','НАГРАДЫ')}<div class="list">${recent.map(r=>{const member=r.members.find(m=>m.id===me.id);return `<div class="row"><div class="symbol">${r.status==='cleared'?'🏆':'☠'}</div><div class="row-main"><h3>${esc(r.name)}</h3><p>${{cleared:'Успех',failed:'Неудача',expired:'Группа распущена'}[r.status]||r.status} · №${r.id}${r.event?.choice?' · '+esc(r.event.choice_label):''}</p></div>${['cleared','failed'].includes(r.status)&&member&&!member.rewarded?btn('НАГРАДА','exp-claim','small gold',r.id):member?.rewarded?'<span class="badge">Получено</span>':''}</div>`}).join('')}</div>`:''}`;
}
function storyScreen(){
  if(!story)return `<div class="panel">Загружаем радиоперехват...</div>`;
  const histories=story.decisions||[];
  const stages=['РАЗВЕДКА','СТОЛКНОВЕНИЕ','РЕШЕНИЕ'];
  const marker=story.finished?'ФИНАЛ':`ГЛАВА ${String(story.chapter_index).padStart(2,'0')} / ${String(story.total).padStart(2,'0')}`;
  const act=story.scene;
  const milestones=(story.chapters||[]).map((c,i)=>{
    const state=c.status==='completed'?'chapter-done':c.status==='current'?'chapter-current':'chapter-locked';
    const tag=c.status==='completed'?'✓ ПРОЙДЕНО':c.status==='current'?'СЕЙЧАС':`УРОВЕНЬ ${c.level}`;
    return `<div class="story-chapter ${state}"><span class="story-chapter-number">${String(i+1).padStart(2,'0')}</span><div><strong>${esc(c.title)}</strong><small>${tag}</small></div><span class="story-chapter-dot">${c.status==='completed'?'✓':c.status==='current'?'◆':'◇'}</span></div>`;
  }).join('');
  const path=story.trust>=3?'СОЮЗНИКИ':story.trust<=-3?'ОДИНОЧКА':'НА ПЕРЕПУТЬЕ';
  return `${section('СЮЖЕТНАЯ КАМПАНИЯ','ЗАПИСИ / ДЕЛО № 07')}
  <div class="story-hero"><span class="eyebrow">// ${marker} · ZOMBO ARCHIVE</span><h1>${story.finished?'СИГНАЛ<br><em>ЗАВЕРШЁН</em>':'ПРОТОКОЛ<br><em>«СЕДЬМОЙ»</em>'}</h1><p>${story.finished?'Твоя история стала легендой пустоши.': 'У каждого сигнала есть источник. У каждой правды — своя цена.'}</p><div class="story-progress-label"><strong>${story.completed_count} / ${story.total}</strong><span>ГЛАВ ПРОЙДЕНО</span></div>${bar(story.completed_count,story.total)}</div>
  <div class="story-reputation"><span class="story-reputation-icon">◈</span><div><small>ТВОЙ ПУТЬ · ${path}</small><strong>${story.trust>0?'+':''}${story.trust} доверия · ${story.karma} кармы</strong><p>${esc(story.perk)}</p></div></div>
  ${story.finished?`<div class="story-ending"><span class="eyebrow">// ЗАВЕРШЕНИЕ ИСТОРИИ</span><h2>${esc(story.ending)}</h2><p>${esc(story.ending_text)}</p><div class="story-ending-seal">✦ ИСТОРИЯ ВЫЖИВШЕГО ЗАВЕРШЕНА ✦</div></div>`:
  `<div class="story-case"><div class="story-case-head"><span class="tag">${marker}</span><span class="tag">⌖ ${esc(story.location)}</span></div><h2>${esc(story.chapter_title)}</h2><p>${esc(story.intro)}</p></div>
  <div class="story-act-track">${stages.map((name,i)=>`<div class="story-act-step ${i<story.stage?'done':i===story.stage?'current':''}"><span>${i<story.stage?'✓':i+1}</span><small>${name}</small></div>`).join('')}</div>
  ${story.available?`<div class="story-scene"><span class="eyebrow">// ЭТАП ${story.stage+1} · ${stages[story.stage]}</span><h2>${esc(act?.title||'')}</h2><p>${esc(act?.text||'')}</p>
  <div class="story-decisions">${(act?.actions||[]).map((choice,index)=>`<button class="story-decision ${act.kind==='choice'?(index===0?'story-mercy':'story-pragmatic'):''}" data-action="story-act" data-value="${esc(choice.key)}"><span class="story-decision-icon">${act.kind==='scout'?'⌖':act.kind==='combat'?'⚔':index===0?'✚':'◈'}</span><span><strong>${esc(choice.title)}</strong>${choice.description?`<small>${esc(choice.description)}</small>`:''}</span>${choice.energy?`<em>⚡${choice.energy}</em>`:'<em>➜</em>'}</button>`).join('')}</div>
  ${act.kind==='combat'?'<div class="story-warning">⚠ Бой расходует энергию и здоровье. Перед схваткой проверь броню и запас аптечек.</div>':act.kind==='choice'?'<div class="story-warning">◈ Выбор сохранится навсегда и повлияет на доверие, карму и будущие награды.</div>':''}</div>`:
  `<div class="story-locked"><strong>🔒 Глава пока недоступна</strong><p>Нужен уровень <b>${story.level_required}</b>, сейчас у тебя ${me.level}. Сражайся, проходи рейды и изучай пустошь, чтобы продолжить историю.</p>${btn('КАРТА ПУСТОШИ','nav','gold','map')}</div>`}`}
  ${section('АРХИВ ЗАПИСЕЙ',`${story.completed_count} / ${story.total} ГЛАВ`)}
  <div class="story-chapter-list">${milestones}</div>
  ${histories.length?`${section('ПОСЛЕДСТВИЯ','ТВОИ РЕШЕНИЯ')}<div class="story-history">${histories.slice().reverse().map(d=>`<div><span>ГЛАВА ${d.chapter}</span><strong>${esc(d.decision)}</strong><small>${esc(d.title)}</small></div>`).join('')}</div>`:''}
  ${btn('← В УБЕЖИЩЕ','nav','ghost full','home')}`;
}
function petsScreen(){
  const pet=me.pet,pets=cfg.pets||{};
  return `${section('СПУТНИК В ПУСТОШИ','6 ВИДОВ · 10 УРОВНЕЙ')}
  ${pet?`<div class="panel"><div class="flex-between"><div><span class="tag">ТВОЙ СПУТНИК</span><h2>${pet.icon} ${esc(pet.name)}</h2><p>Уровень ${pet.level}/10 · Способность «${esc(pet.ability)}»</p><p class="smallnote">Постоянный бонус: ${esc(pet.bonus)} +${Math.round(pet.per_level*pet.level*1000)/10}%</p></div></div>${pet.level<10?`<div class="bar-label"><span>Опыт питомца</span><em>${pet.xp}/${pet.xp_next}</em></div>${bar(pet.xp,pet.xp_next)}`:''}<p class="smallnote">Питомец набирает опыт за победы над заражёнными. В бою доступна его особая помощь один раз за столкновение (3 энергии).</p></div>`:
  `<div class="panel"><h3>НАЙТИ СПУТНИКА</h3><p>Питомец может присоединиться после победы над заражённым с шансом 0,5%. Или приручи его у торговца: случайный за 750 крышек, выбранный за 1250.</p>${btn('ПРИРУЧИТЬ СЛУЧАЙНОГО · 750 🪙','pet-adopt','gold full','random',me.caps<750)}</div>`}
  <div class="list">${Object.entries(pets).map(([key,s])=>`<div class="row"><div class="symbol">${s.icon}</div><div class="row-main"><h3>${esc(s.name)} · ${esc(s.ability)}</h3><p>Бонус: ${esc(s.bonus)} · +${(s.per_level*100).toFixed(1)}% за уровень</p></div>${!pet?btn('1250 🪙','pet-adopt','small ghost',key,me.caps<1250):''}</div>`).join('')}</div>`;
}
function more(){
 const groups=[
  ['ВЫЛАЗКИ И ИСТОРИЯ','МИР ZOMBO',[
   ['story','book','Сюжетная кампания','10 глав · решения и последствия'],
   ['raids','skull','Групповые рейды','3–10 игроков · три этапа'],
   ['expeditions','clock','Дальние экспедиции','3–10 игроков · роли · 12 часов'],
   ['world-events','skull','Глобальные события','Орда заражённых и военные грузы'],
   ['encounters','map','Случайные встречи','Решения, риск и уникальная добыча в пустоши'],
   ['boss','skull','Мировой босс','Общая битва каждые три дня'],
   ['quests','check','Задания','Выполняй поручения и получай опыт'],
   ['bestiary','book','Бестиарий','10 видов заражённых и их приёмы']]],
  ['РАЗВИТИЕ ГЕРОЯ','СНАРЯЖЕНИЕ И НАВЫКИ',[
   ['gear','shield','Арсенал и улучшения','Редкость предметов и прокачка +10'],
   ['cases','bag','Кейсы: 7 коллекций','28 эксклюзивных пушек и шансы выпадения'],
   ['talents','target','Дерево талантов','Три пути и 27 рангов улучшений'],
   ['inventory','bag','Инвентарь','Твоя экипировка, медицина и материалы'],
   ['craft','hammer','Мастерская','Создавай оружие и расходники'],
    ['pets','hero','Питомцы','6 спутников · реальные боевые навыки']]],
  ['ТОРГОВЛЯ','ЭКОНОМИКА',[
   ['gear-market','exchange','Рынок редкого снаряжения','Купля-продажа уникального оружия и брони'],
   ['market','exchange','Биржа','Обмен между выжившими'],
   ['shop','shop','Торговец','Закупай припасы за крышки'],
   ['stars','gem','Zombo Stars','Премиум-валюта через Telegram']]],
  ['СВЯЗЬ С УБЕЖИЩЕМ','НАСТРОЙКИ', [['notifications','clock','Уведомления Telegram','Экспедиции, торговля, рейды и КВ']]],
  ['СОРЕВНОВАНИЕ','ИГРОКИ',[
   ['pvp','swords','Арена','Вызовы другим игрокам'],
   ['leaders','leader','Топ игроков','Уровень · заражённые · арена']]]
 ];
 if(me.admin)groups.push(['УПРАВЛЕНИЕ','ТОЛЬКО АДМИНИСТРАТОР',[['admin','shield','Админский терминал','Игроки, модерация, экономика и журнал']]]);
 return `${section('ТЕРМИНАЛ УБЕЖИЩА','МЕНЮ')}${groups.map(([title,meta,options])=>`<div class="menu-group">${section(title,meta)}<div class="list">${options.map(([id,ico,name,desc])=>`<div class="row" data-action="nav" data-value="${id}" style="cursor:pointer"><div class="symbol">${uiIcon(ico)}</div><div class="row-main"><h3>${name}</h3><p>${desc}</p></div><span style="color:var(--gold)">↗</span></div>`).join('')}</div></div>`).join('')}`;
}
function encountersScreen(){
 const data=encounterData||{},e=data.encounter;
 const zone=cfg.locations[me.location]?.name||me.location;
 const top=`${section('ВСТРЕЧИ В ПУСТОШИ','РАЗВЕДКА')}<div class="panel"><p>В каждой локации можно встретить выживших, обнаружить заброшенные машины, тайники и ловушки. Вид встречи и результат рискованного решения определяются сервером и не меняются от перезагрузки.</p><p class="smallnote">Стоимость разведки: ${data.explore_cost||6} энергии · пауза после решения: ${data.cooldown_seconds||60} сек.</p>${(data.clues||[]).length?`<p class="smallnote">Зацепки: ${data.clues.map(esc).join(', ')}. Они открывают особые решения и расходуются при использовании.</p>`:''}</div>`;
 if(e?.status==='pending')return `${top}<div class="panel"><span class="eyebrow">// НЕОЖИДАННАЯ ВСТРЕЧА · ${esc(cfg.locations[e.location]?.name||zone)} · ОПАСНОСТЬ ${e.danger||1}/5</span><h2>${esc(e.title)}</h2><p>${esc(e.description)}</p><div class="list mt">${Object.entries(e.choices||{}).map(([key,opt])=>`<div class="card"><h3>${esc(opt.label)}</h3><p>${esc(opt.hint)}</p>${btn(opt.locked?'НУЖНА ЗАЦЕПКА':'ВЫБРАТЬ','encounter-resolve','gold full',key,!!opt.locked)}</div>`).join('')}</div></div>`;
 return `${top}${e?.outcome?`<div class="panel"><span class="tag">ПРЕДЫДУЩАЯ ВСТРЕЧА</span><h3>${esc(e.title)}</h3><p>${esc(e.outcome)}</p></div>`:''}<div class="panel mt"><h3>ПРОЧЕСАТЬ ${esc(zone.toUpperCase())}</h3><p class="smallnote">${me.location==='base'?'Сначала выйди из убежища.':'Новая встреча может принести добычу, карму или травмы. Если не хочешь рисковать, всегда можешь уйти.'}</p>${btn('ИСКАТЬ ВСТРЕЧУ','encounter-explore','gold full','',me.location==='base'||me.stamina<(data.explore_cost||6))}</div>`;
}
function worldEventsScreen(){
 const data=worldEvents||{},events=data.events||[];
 const labels={scheduled:'СКОРО',active:'ИДЁТ',finished:'ЗАВЕРШЕНО',stopped:'ОСТАНОВЛЕНО'};
 const active=events.filter(e=>e.status==='active'||e.status==='scheduled');
 const closed=events.filter(e=>e.status==='finished'||e.status==='stopped');
 function card(e){
  const zone=cfg.locations[e.location]?.name||e.location;
  const interval=new Date(e.starts_at).toLocaleString('ru-RU')+' → '+new Date(e.ends_at).toLocaleString('ru-RU');
  return `<div class="panel"><div class="flex-between"><h3>${esc(e.name)}</h3><span class="tag">${labels[e.status]}</span></div><p>${esc(e.description)}</p><p class="smallnote">☣ ${esc(zone)} · ${esc(interval)}</p><p>Общий прогресс: <strong>${money(e.progress)} / ${money(e.goal)}</strong> · твой вклад: ${money(e.my_actions)}</p>${bar(e.progress,e.goal)}<div class="flex-between mt"><span class="smallnote">Награда за участие при достижении общей цели: +${money(e.reward.caps)} крышек · +${money(e.reward.xp)} XP</span>${e.claimed?'<span class="tag">ПОЛУЧЕНО</span>':e.can_claim?btn('ЗАБРАТЬ','world-event-claim','small gold',e.id):''}</div></div>`;
 }
 return `${section('ЭФИР ПУСТОШИ','ГЛОБАЛЬНЫЕ СОБЫТИЯ')}<div class="notice">Бонусы работают только во время события и только в указанной локации. Награда за общий результат доступна после завершения события участникам, внёсшим вклад. Если общая цель не достигнута, итоговой награды нет.</div>
 ${section('АКТИВНЫЕ И ЗАПЛАНИРОВАННЫЕ',String(active.length))}
 <div class="list">${active.map(card).join('')||'<div class="empty">Сейчас эфир спокоен. Новые события создают администраторы.</div>'}</div>
 ${section('ПОСЛЕДНИЕ СОБЫТИЯ',String(closed.length))}
 <div class="list">${closed.map(card).join('')||'<div class="empty">Завершённых событий пока нет.</div>'}</div>`;
}
function notificationsScreen(){
 const n=notificationData||{},prefs=n.settings||{},history=n.history||[];
 const labels={expeditions:'Экспедиции',market:'Рынок снаряжения',raids:'Рейды',clans:'Клановые войны'};
 const hints={expeditions:'Старт, выбор решения через 4 часа и возвращение отряда.',
              market:'Уведомления о продаже или возврате снаряжения.',
              raids:'Группа готова, рейд начался, завершён или истёк.',
              clans:'Начало и итог КВ, новые недельные поручения.'};
 const states={pending:'ОЖИДАЕТ',sending:'ОТПРАВЛЯЕТСЯ',sent:'ОТПРАВЛЕНО',skipped:'ПРОПУЩЕНО',failed:'НЕ ДОСТАВЛЕНО'};
 return `${section('РАДИОСВЯЗЬ','УВЕДОМЛЕНИЯ TELEGRAM')}
 <div class="panel"><p class="smallnote">По умолчанию выключено. Сообщения приходят только после включения выбранной категории. Отправка возможна, если бот может написать тебе в личные сообщения.</p></div>
 <div class="list">${Object.entries(labels).map(([key,label])=>`<div class="row"><div class="row-main"><h3>${esc(label)}</h3><p>${esc(hints[key])}</p><span class="tag">${prefs[key]?'ВКЛЮЧЕНО':'ВЫКЛЮЧЕНО'}</span></div>${btn(prefs[key]?'ОТКЛЮЧИТЬ':'ВКЛЮЧИТЬ','notify-toggle','small '+(prefs[key]?'soft':'gold'),key)}</div>`).join('')}</div>
 ${section('ИСТОРИЯ СИГНАЛОВ','ПОСЛЕДНИЕ 15')}
 <div class="list">${history.map(x=>`<div class="row"><div class="row-main"><h3>${esc(labels[x.category]||'Событие')} <span class="tag">${esc(states[x.status]||x.status)}</span></h3><p>${esc(x.message)}</p></div></div>`).join('')||'<div class="empty">Уведомлений ещё нет. Включи нужные категории и продолжай играть.</div>'}</div>`;
}
function filterTabs(action,active,choices){return `<div class="filter-tabs">${choices.map(([key,label])=>`<button type="button" class="filter-pill ${active===key?'active':''}" data-action="${action}" data-value="${key}">${esc(label)}</button>`).join('')}</div>`}
function searchBox(group,value,label){return `<label class="search-label" for="search-${group}">${label}</label><input id="search-${group}" class="list-search" data-list-search="${group}" type="search" value="${esc(value)}" placeholder="Название или материал…" autocomplete="off" maxlength="64">`}
function inventoryScreen(){
 const total=ownedInventory().reduce((n,i)=>n+i.qty,0);
 return `<div class="panel"><div class="flex-between"><div><strong>⚔ Твоя уникальная экипировка</strong><p class="smallnote">${(me.gear||[]).length} предметов на складе</p></div>${btn('АРСЕНАЛ ↗','nav','small gold','gear')}</div></div>${section('РЮКЗАК',`${total} ПРЕДМЕТОВ`)}<div class="panel item-filters">${searchBox('inventory',inventoryQuery,'БЫСТРЫЙ ПОИСК')}${filterTabs('inventory-filter',inventoryFilter,[['all','Все'],['unique','Уникальное'],['material','Ресурсы'],['consumable','Расходники'],['weapon','Оружие'],['armor','Броня'],['case','Кейсы'],['chest','Сундуки']])}</div>${inventory(true)}`;
}
function craftScreen(){
 const entries=Object.entries(cfg.recipes||{}).map(([key,r])=>{const item=cfg.items[r.output||key];
  const missing=Object.entries(r.cost).filter(([mat,qty])=>(me.inventory||[]).filter(x=>x.key===mat&&!x.equipped).reduce((n,x)=>n+x.qty,0)<qty);
  return {key,r,item,missing,ready:missing.length===0,kind:itemKind(item)};}).filter(x=>(craftFilter==='all'||x.kind===craftFilter)&&(!craftReadyOnly||x.ready));
 const available=Object.entries(cfg.recipes||{}).filter(([key,r])=>Object.entries(r.cost).every(([mat,qty])=>(me.inventory||[]).filter(x=>x.key===mat&&!x.equipped).reduce((n,x)=>n+x.qty,0)>=qty)).length;
 return `${section('МАСТЕРСКАЯ',`${available} ГОТОВО К СОЗДАНИЮ`)}<div class="panel item-filters"><p class="smallnote">Собирай материалы в лесу, городе и на заводе. Не хватает ресурсов? Смотри красные числа и отправляйся на карту.</p>${searchBox('craft',craftQuery,'ПОИСК РЕЦЕПТА')}${filterTabs('craft-filter',craftFilter,[['all','Все'],['weapon','Оружие'],['armor','Броня'],['consumable','Расходники']])}<button type="button" class="filter-pill ${craftReadyOnly?'active':''}" data-action="craft-available">✓ Только доступные (${available})</button></div><div class="list">${entries.map(({key,r,item,ready})=>`<div class="row" data-search-group="craft" data-search="${esc(((r.name||item.name)+' '+key+' '+Object.keys(r.cost).map(k=>cfg.items[k]?.name||k).join(' ')).toLowerCase())}"><div class="symbol">${esc(item.icon)}</div><div class="row-main"><h3>${esc(r.name||item.name)}${r.qty>1?' ×'+r.qty:''}</h3><p>${Object.entries(r.cost).map(([mat,qty])=>{const own=(me.inventory||[]).filter(x=>x.key===mat&&!x.equipped).reduce((n,x)=>n+x.qty,0);return `<span class="material-cost ${own<qty?'missing':''}">${esc(cfg.items[mat]?.icon||'⚙')} ${qty} ${esc(cfg.items[mat]?.name||mat)} (${own})</span>`}).join(' · ')}</p></div>${btn(ready?'СОЗДАТЬ':'НЕ ХВАТАЕТ','craft','small '+(ready?'gold':'ghost'),key,!ready)}</div>`).join('')||'<div class="empty">В выбранной категории рецептов нет.</div>'}</div><div class="empty search-empty" data-filter-empty="craft" hidden>Рецептов с таким названием нет.</div>`;
}
function questsScreen(){return `${section('ДЕЛА ВЫЖИВШЕГО','ПОСТОЯННЫЕ')}<div class="list">${(quests||[]).map(q=>`<div class="card"><div class="flex-between"><h3>◈ ${q.name}</h3><span class="tag">${q.claimed?'ВЫПОЛНЕНО':q.amount>=q.target?'ГОТОВО':`${Math.min(q.amount,q.target)}/${q.target}`}</span></div><p>${q.description}</p>${bar(Math.min(q.amount,q.target),q.target)}<div class="flex-between mt"><span class="smallnote">🪙 ${q.reward.caps} · ★ ${q.reward.xp} XP</span>${btn(q.claimed?'Получено':'Забрать','quest','small gold',q.code,q.amount<q.target||q.claimed)}</div></div>`).join('')}</div>`}
function bossScreen(){if(!boss)return '';return `${section('МИРОВОЙ БОСС','ГЛОБАЛЬНОЕ СОБЫТИЕ')}<div class="enemy-art fight-screen"><span class="eyebrow">ОПАСНОСТЬ V КЛАССА</span><div style="font-size:92px;margin:10px 0">☣</div><h2>${esc(boss.name)}</h2><p class="smallnote">${esc(boss.hint||'Только объединённая сила выживших остановит его.')}</p><p class="smallnote">⚔ ${esc(boss.attack_name||'Атака')} · ${esc(boss.mechanic||'')} · Фаза: ${esc(boss.phase||'Обычная')}</p><p class="smallnote">Ротация: ${boss.cycle_bosses||5} мировых боссов · новый каждые 3 дня</p><p class="smallnote">🏆 ${esc(boss.top_prize||'Приз лидеру урона')}</p><p class="smallnote">Следующий цикл: ${new Date(boss.ends_at).toLocaleString('ru-RU')}</p><div style="max-width:270px;margin:10px auto"><div class="bar-label"><span>ЗДОРОВЬЕ БОССА</span><em>${money(boss.hp)} / ${money(boss.max_hp)}</em></div>${bar(boss.hp,boss.max_hp,'red')}</div></div><div class="panel mt"><div class="notice">Атака расходует 5⚡, наносит урон по силе персонажа. Повторный удар через 30 сек. Босс отвечает ударом, каждая третья атака — особая. Опыт +50 XP за выживший ход.</div>${btn('⚔ АТАКОВАТЬ БОССА','boss-hit','red full','',boss.hp<1)}</div>${section('ТОП УЧАСТНИКОВ')}<div class="list">${(boss.top||[]).map((r,i)=>`<div class="row"><div class="symbol">${i+1}</div><div class="row-main"><h3>${esc(r.name)}</h3><p>Нанесено урона</p></div><strong>${money(r.damage)}</strong></div>`).join('')||'<div class="empty">Первый удар ещё не нанесён</div>'}</div>`}
function warBadge(status){return ({bidding:'ТОРГИ',formation:'РАССТАНОВКА',battle:'⚔ БИТВА',resolved:'ЗАВЕРШЕНО'})[status]||status}
function territoryMap(items){const ids=['bridge','tower','depot','clinic'];const paths={bridge:'M10 30 166 12 184 89 115 136 17 123Z',tower:'M183 12 349 34 346 119 257 135 187 93Z',depot:'M16 139 118 153 180 106 260 145 261 222 30 223Z',clinic:'M270 146 345 130 349 220 271 222Z'};
 const coords={bridge:[24,36],tower:[72,34],depot:[39,73],clinic:[85,78]};const pathElems=ids.map(id=>{const t=items.find(x=>x.id===id)||{};const hue=t.clan_id?(t.clan_id===me.clan_id?'#20573e':['#63392f','#574632','#493a56'][Math.abs(t.clan_id)%3]):'#334047';return `<path d="${paths[id]}" fill="${hue}" fill-opacity=".86" stroke="${id===selectedTerritory?'#e6bb75':'#809095'}" stroke-width="${id===selectedTerritory?'3.2':'1.3'}" stroke-linejoin="round"/>`}).join('');const pins=ids.map(id=>{let t=items.find(x=>x.id===id)||{};let name=t.clan_id?(t.owner||'Клан'):'Зомби';let [x,y]=coords[id];return `<button class="territory-pin ${id===selectedTerritory?'active':''} ${t.clan_id?(t.clan_id===me.clan_id?'mine':'captured'):'unclaimed'}" style="left:${x}%;top:${y}%" data-action="territory-select" data-value="${id}" title="${esc(t.name||id)}: ${esc(name)}"><span>${esc(t.name||id)}</span><b>${esc(name.length>15?name.slice(0,13)+'…':name)}</b></button>`}).join('');
 return `<div class="territory-map"><div class="territory-map-head"><span>${icon('map')} ТАКТИЧЕСКАЯ КАРТА</span><small>Нажми на регион</small></div><div class="territory-map-stage"><svg viewBox="0 0 360 235" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Карта четырёх территорий"><defs><pattern id="map-grid" width="22" height="22" patternUnits="userSpaceOnUse"><path d="M22 0H0V22" fill="none" stroke="#8096a0" opacity=".10" stroke-width=".8"/></pattern></defs><rect width="360" height="235" fill="#141b20"/><rect width="360" height="235" fill="url(#map-grid)"/><path d="M0 113Q85 106 122 132T360 106" stroke="#1f4552" stroke-width="20" fill="none"/><path d="M0 113Q85 106 122 132T360 106" stroke="#648c94" stroke-width="1" fill="none" stroke-dasharray="6 8"/>${pathElems}<path d="M0 113Q85 106 122 132T360 106" stroke="#182830" stroke-width="12" fill="none"/><path d="M0 113Q85 106 122 132T360 106" stroke="#50727c" stroke-width="1.5" fill="none"/></svg>${pins}</div><div class="territory-legend"><span><i class="unclaimed"></i> Зомби</span><span><i class="mine"></i> Наш клан</span><span><i class="captured"></i> Другие кланы</span></div></div>`}
function clanMissionsBoard(){
  const data=clanMissions;
  if(!data)return '';
  const tasks=(data.missions||[]);
  const ranking=(data.ranking||[]).slice(0,6);
  const reward=data.season_reward, history=data.season_history||[];
  const ends=data.ends_at?new Date(data.ends_at).toLocaleString('ru-RU',{day:'numeric',month:'long',hour:'2-digit',minute:'2-digit',timeZone:'UTC'})+' UTC':'—';
  return `${section('КЛАНОВЫЕ ПОРУЧЕНИЯ','НЕДЕЛЬНЫЕ ЦЕЛИ')}
  ${data.clan_id?`<div class="mission-head panel"><div class="flex-between"><div><span class="eyebrow">// ОБЩЕЕ ДЕЛО КЛАНА</span><h3>${esc(data.clan_name)} · уровень ${Number(data.clan_level||1)}</h3></div><span class="tag">СЕЗОН ${esc(data.season)}</span></div><p class="smallnote">Обновление задач: ${esc(ends)}. Вместе зарабатывайте крышки в казну и репутацию клана. Личная награда открывается после общего выполнения и минимального вклада.</p><div class="mission-meta"><span>✦ Репутация: <b>${money(data.renown)}</b></span><span>🏆 За сезон: <b>${money(data.season_points)}</b></span></div></div>
  <div class="mission-list">${tasks.map(t=>`<article class="mission-card ${t.completed?'is-complete':''}">
  <div class="flex-between"><span class="tag">${esc(t.icon)} ${t.completed?'ВЫПОЛНЕНО':'АКТИВНО'}</span><strong>${Math.min(t.target,t.progress)}/${t.target}</strong></div>
  <h3>${esc(t.name)}</h3><p>${esc(t.desc)}</p>
  ${bar(t.progress,t.target)}
  <div class="mission-rewards"><span>🏦 +${money(t.treasury)} крышек клану</span><span>✦ +${money(t.renown)} репутации</span></div>
  <div class="mission-footer"><div><strong>Твой вклад: ${money(t.mine)} / ${t.minimum}</strong><small>Личная награда: ${money(t.personal_caps)} крышек · ${money(t.personal_xp)} XP</small></div>
  ${btn(t.claimed?'ПОЛУЧЕНО':t.can_claim?'ЗАБРАТЬ':'НЕ ГОТОВО','clan-mission-claim','small gold',t.code,!t.can_claim)}
  </div></article>`).join('')}</div>`:
  `<div class="panel"><strong>Общие задания открываются после вступления в клан.</strong><p class="smallnote">Собирайте припасы, уничтожайте заражённых и сражайтесь с мировым боссом, чтобы пополнять казну и повышать уровень клана.</p></div>`}
  ${section('РЕЙТИНГ КЛАНОВ','ТЕКУЩИЙ МЕСЯЦ')}
  <div class="mission-rank-list">${ranking.map((r,i)=>`<div class="mission-rank"><span class="mission-place">${i+1}</span><div><strong>${esc(r.name)}</strong><small>${r.completed} заданий завершено</small></div><b>${money(r.points)} ✦</b></div>`).join('')||'<div class="panel smallnote">Пока ни один клан не выполнил поручения в этом сезоне.</div>'}</div>
  ${section('ИСТОРИЯ СЕЗОНОВ','ПРИЗОВАЯ ТРОЙКА')}
  <div class="mission-rank-list">${history.map(r=>`<div class="mission-rank"><span class="mission-place">${r.place}</span><div><strong>${esc(r.name)}</strong><small>${esc(r.season)} · ${r.completed} поручений</small></div><b>${money(r.points)} ✦</b></div>`).join('')||'<div class="panel smallnote">Завершённых сезонов пока нет.</div>'}</div>
  ${reward?`<div class="panel"><h3>НАГРАДА ЗА СЕЗОН ${esc(reward.season)}</h3><p class="smallnote">Место клана: ${reward.place}. Твой вклад: ${money(reward.contribution)} / ${reward.minimum}. Награда: ${money(reward.caps)} крышек и ${money(reward.xp)} XP.</p>${btn(reward.claimed?'ПОЛУЧЕНО':reward.can_claim?'ЗАБРАТЬ':'НЕ ГОТОВО','clan-season-claim','small gold','',!reward.can_claim)}</div>`:''}`;
}
function clanScreen(){
 const mine=clans?.list?.find(c=>c.id===me.clan_id);
 const phaseText={bidding:'СТАВКИ ОТКРЫТЫ',formation:'РАССТАНОВКА ВОЙСК',battle:'КЛАНОВАЯ ВОЙНА',waiting:'ОЖИДАНИЕ БОЯ',finished:'ДЕНЬ КВ ЗАВЕРШЁН',rest:'ПЕРЕДЫШКА'};
 const canLead=Boolean(clans?.can_command);
 const showWar=(war,t)=>{
   if(!war)return '';
   const attacker=clans?.list?.find(c=>c.id===war.attacker_clan_id)?.name||'Претендент';
   const defender=clans?.list?.find(c=>c.id===war.defender_clan_id)?.name||'Свободна';
   const assigned=war.fighters||[];
   const side=war.attacker_clan_id===me.clan_id?'attacker':war.defender_clan_id===me.clan_id?'defender':null;
   const myFighter=assigned.find(f=>f.player_id===me.id);
   const canPlace=canLead&&warsData.phase==='formation'&&war.status==='formation'&&!!side;
   const getLine=f=>`<div class="war-fighter ${f.hp<=0?'fallen':''}"><div><b>${esc(f.name)}</b><small>${f.hp}/${f.max_hp} HP · Урон ${f.damage}</small></div>${canPlace&&f.side===side?btn('Снять','war-remove','small ghost',`${war.id}:${f.player_id}`):''}</div>`;
   return `<div class="war-event"><div class="flex-between"><span class="tag">${warBadge(war.status)} · ${esc(war.war_date)}</span><span class="war-gold">🪙 ${money(war.bid)}</span></div><h4>⚔ ${esc(attacker)} <span style="color:var(--muted)">против</span> ${esc(defender)}</h4>${war.status==='resolved'?`<p class="smallnote">Победитель: ${esc(clans?.list?.find(c=>c.id===war.winner_clan_id)?.name|| (war.winner_clan_id?'Клан #'+war.winner_clan_id:'Не определён'))}</p>`:''}
   <div class="war-armies"><div><strong>НАПАДЕНИЕ · ${assigned.filter(f=>f.side==='attacker').length}/25</strong>${assigned.filter(f=>f.side==='attacker').map(getLine).join('')||'<p class="smallnote">Нет бойцов</p>'}</div><div><strong>ЗАЩИТА · ${assigned.filter(f=>f.side==='defender').length}/25</strong>${assigned.filter(f=>f.side==='defender').map(getLine).join('')||'<p class="smallnote">Нет бойцов</p>'}</div></div>
   ${canPlace?`<div class="war-deploy"><label>Выставить участника отряда</label><div class="war-deploy-controls"><select id="roster-${war.id}">${(clans.members||[]).filter(m=>!assigned.some(f=>f.player_id===m.id)).map(m=>`<option value="${m.id}">${esc(m.name)} · LVL ${m.level}</option>`).join('')}</select>${btn('Выставить','war-add','small gold',war.id)}</div></div>`:''}
   ${war.status==='battle'?`<div class="war-current"><div class="tag">РАУНД ${war.round}/30</div>${myFighter?`<div class="bar-label"><span>Ты в бою</span><em>${myFighter.hp}/${myFighter.max_hp} HP</em></div>${bar(myFighter.hp,myFighter.max_hp,'red')}${myFighter.hp>0?`<div class="actions">${btn('⚔ Удар','war-act','red',`${war.id}:attack`,myFighter.last_action_round===war.round)}${btn('🛡 Защита','war-act','soft',`${war.id}:guard`,myFighter.last_action_round===war.round)}${me.class==='medic'?btn('✚ Лечение','war-act','gold',`${war.id}:heal`,myFighter.last_action_round===war.round):''}</div>`:'<p class="smallnote">Твой боец выбыл.</p>'}`:'<p class="smallnote">Ты не назначена в этот отряд.</p>'}</div>`:''}
   ${war.log?.length?`<details class="war-chronicle"><summary>Журнал КВ (${war.log.length})</summary>${war.log.slice(-12).map(x=>`<div>${esc(x)}</div>`).join('')}</details>`:''}</div>`
 }
 return `${section('КЛАНОВЫЕ ВОЙНЫ','ТЕРРИТОРИИ И НАЛОГИ')}
 <div class="war-banner"><span class="eyebrow">// ЦИКЛ КЛАНОВОЙ ВОЙНЫ</span><h2>${phaseText[warsData?.phase]||'ПОДГОТОВКА'}</h2><div class="war-schedule"><span>ПН / СР / ПТ<br><b>СТАВКИ</b></span><span>ВТ / ЧТ / СБ<br><b>10:00–15:00 · СОСТАВ</b></span><span>ВТ / ЧТ / СБ<br><b>16:00–16:30 · КВ</b></span></div><p class="smallnote">Время: ${esc(warsData?.timezone||cfg.war_timezone||'Europe/Moscow')} · Следующее КВ: ${esc(warsData?.next_war_date||'—')}</p><p class="smallnote">Входящий налог: 1% крышек с убийств заражённых. Перевод в казну каждые 5 часов.</p></div>
 ${mine?`<div class="panel"><span class="tag">ТВОЙ КЛАН</span><h2 style="font:600 26px Oswald;margin:8px 0">${esc(mine.name)}</h2><div class="three-stats"><div class="stat-chip"><small>УРОВЕНЬ</small><strong>${mine.level}</strong></div><div class="stat-chip"><small>УЧАСТНИКИ</small><strong>${mine.members}/25</strong></div><div class="stat-chip"><small>КАЗНА</small><strong>${money(mine.treasury)}</strong></div></div><div class="actions">${btn('Внести крышки','clan-donate','gold')}${btn('Покинуть','clan-leave','ghost')}</div></div>`:`<div class="panel"><h3>Найди свой отряд</h3><p class="smallnote">Для участия в торгах и КВ нужно состоять в клане. Создание стоит 250 крышек.</p>${btn('+ СОЗДАТЬ КЛАН','clan-create','gold')}</div>`}
 ${mine?`${section('ЛИЧНЫЙ СОСТАВ',canLead?'УПРАВЛЕНИЕ':'БОЙЦЫ')}<div class="list">${(clans.members||[]).map(m=>`<div class="row"><div class="symbol">${m.leader?'♛':m.warlord?'⚑':'♙'}</div><div class="row-main"><h3>${esc(m.name)}</h3><p>LVL ${m.level} · ${m.leader?'Лидер':m.warlord?'Воевода':'Боец'}</p></div>${clans.leader_id===me.id&&!m.leader&&!m.warlord?btn('Воевода','war-appoint','small ghost',m.id):''}</div>`).join('')}</div>`:''}
 ${clanMissionsBoard()}
 ${section('РЕГИОНАЛЬНАЯ КАРТА','4 ТЕРРИТОРИИ')}
 ${territoryMap(territories||[])}
 <div class="war-territories">${(territories||[]).filter(t=>t.id===selectedTerritory).map(t=>{
    const war=(warsData?.wars||[]).find(w=>w.territory_id===t.id && (w.status!=='resolved'||w.war_date===warsData?.next_war_date));
    return `<div class="war-territory"><div class="flex-between"><span class="tag">${icon('map')} ОБЛАСТЬ ${esc(t.id.toUpperCase())}</span><span class="tag">${t.clan_id?'ЗАНЯТА':'СВОБОДНА'}</span></div><h3>${esc(t.name)}</h3><p class="smallnote">Владелец: <b>${esc(t.owner)}</b></p><p class="smallnote">Зоны: ${esc((t.locations||[]).join(', '))}</p><div class="war-taxes"><span><small>НАЛОГ В РЕЗЕРВЕ</small><b>${icon('coins')} ${money(t.tax_pending)}</b></span><span><small>СОБРАНО ВСЕГО</small><b>${money(t.tax_collected)}</b></span></div><p class="smallnote">Следующий сбор: ${t.tax_next?new Date(t.tax_next).toLocaleString('ru-RU',{timeZone:warsData?.timezone||'Europe/Moscow',day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'—'}</p>
    ${warsData?.phase==='bidding'&&canLead&&t.clan_id!==me.clan_id?btn(`СДЕЛАТЬ СТАВКУ${war?' · ОТ '+money(war.bid+1):''}`,'war-bid','gold full',t.id):''}
    ${war?showWar(war,t):'<p class="smallnote">Нет активных торгов или назначенного КВ.</p>'}</div>`}).join('')}</div>
 ${section('СПИСОК КЛАНОВ')}<div class="list">${(clans?.list||[]).map(c=>`<div class="row"><div class="symbol">♜</div><div class="row-main"><h3>${esc(c.name)}</h3><p>${c.members}/25 игроков · 🪙 ${money(c.treasury)}</p></div>${!me.clan_id?btn('Вступить','clan-join','small ghost',c.id,c.members>=25):''}</div>`).join('')||'<div class="empty">Кланы пока не созданы</div>'}</div>${btn('↻ ОБНОВИТЬ КВ','refresh','ghost full')}`;
}
// ZOMBO 0.8 — Арсенальная биржа
function gearMarketScreen(){
  if(!gearMarket)return `${section('АРСЕНАЛЬНАЯ БИРЖА')}<div class="panel">Загрузка предложений…</div>`;
  const available=(me.gear||[]).filter(g=>!g.equipped);
  const active=(gearMarket.items||[]);
  const mine=(gearMarket.my_sales||[]);
  const itemCard=s=>{
    const g=s.gear;
    return `<article class="gm-card" style="--grade:${esc(g.color)}">
      <div class="gm-card-head"><div class="gm-art">${esc(g.icon)}</div><div class="gm-main">
        <small class="gm-rarity">${esc(g.rarity_name)} · ${esc(g.slot==='weapon'?'ОРУЖИЕ':'БРОНЯ')}</small>
        <h3>${esc(g.name)} <em>+${g.level}</em></h3>
        <p>${g.slot==='weapon'?'⚔ '+money(g.power)+' урона':'⬟ '+money(g.defense)+' брони'} · Продавец: ${esc(s.seller_name)}</p>
      </div></div><div class="gm-card-bottom"><div><small>ЦЕНА</small><strong>🪙 ${money(s.price)}</strong></div>
       ${s.is_mine?btn('СНЯТЬ','gm-cancel','small soft',s.id):btn('КУПИТЬ','gm-buy','small gold',s.id,me.caps<s.price||((me.gear||[]).length>=80))}
      </div><div class="gm-until">⏳ До ${new Date(s.expires_at).toLocaleString('ru-RU',{day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit'})}</div>
    </article>`;
  };
  const status={active:'ПРОДАЁТСЯ',sold:'ПРОДАНО',cancelled:'СНЯТО',expired:'ИСТЁК СРОК'};
  return `${section('АРСЕНАЛЬНАЯ БИРЖА','ПРЕДМЕТЫ ИГРОКОВ')}
    <div class="gm-hero"><div class="eyebrow">// ТОРГОВЫЙ ТЕРМИНАЛ</div><h1>СИЛА ИМЕЕТ<br><span>СВОЮ ЦЕНУ.</span></h1><p>Покупай оружие и броню других выживших. Редкость и улучшения сохраняются при продаже.</p>
      <div class="gm-numbers"><span>🪙 <b>${money(me.caps)}</b> крышек</span><span>⟡ ${gearMarket.commission_percent}% комиссия</span><span>▣ ${mine.filter(x=>x.status==='active').length}/${gearMarket.max_listings} лотов</span></div></div>
    <div class="gm-tabs"><button data-action="gm-tab" data-value="browse" class="${gearMarketTab==='browse'?'active':''}">ОБЪЯВЛЕНИЯ</button><button data-action="gm-tab" data-value="mine" class="${gearMarketTab==='mine'?'active':''}">МОИ ПРОДАЖИ</button></div>
    ${gearMarketTab==='browse'?`
      <div class="gm-tools"><div><strong>Открытые предложения</strong><small>Все расчёты проходят через сервер.</small></div>${btn('+ ПРОДАТЬ','gm-create','small gold','',!available.length||mine.filter(x=>x.status==='active').length>=gearMarket.max_listings)}</div>
      <div class="gm-list">${active.map(itemCard).join('')||'<div class="panel gm-empty">Никто пока не выставил оружие или броню. Ты можешь открыть первую продажу.</div>'}</div>
      ${gearMarket.page>1||gearMarket.has_next?`<div class="gm-page">${btn('← НАЗАД','gm-page','small ghost',String(Math.max(1,gearMarket.page-1)),gearMarket.page<=1)}<span>Страница ${gearMarket.page}</span>${btn('ВПЕРЁД →','gm-page','small gold',String(gearMarket.page+1),!gearMarket.has_next)}</div>`:''}
      `:`<div class="gm-tools"><div><strong>Твои сделки</strong><small>Последние 30 лотов, включая завершённые.</small></div>${btn('+ ВЫСТАВИТЬ','gm-create','small gold','',!available.length||mine.filter(x=>x.status==='active').length>=gearMarket.max_listings)}</div>
      <div class="gm-list">${mine.map(s=>`<article class="gm-my-sale"><div><span class="gm-status ${s.status}">${status[s.status]||esc(s.status)}</span><h3>${esc(s.gear.icon)} ${esc(s.gear.name)} +${s.gear.level}</h3><small>${esc(s.gear.rarity_name)} · Лот #${s.id} · 🪙 ${money(s.price)}</small></div>${s.status==='active'?btn('СНЯТЬ','gm-cancel','small ghost',s.id):''}</article>`).join('')||'<div class="panel gm-empty">Ты ещё ничего не продавала. Можно выставить любую ненадетую уникальную экипировку.</div>'}</div>`}
    <div class="panel gm-help"><strong>Как проходят сделки?</strong><p>После выставления предмет хранится в защищённом торговом резерве. Его нельзя использовать или улучшать. У покупателя списывается полная цена, продавец получает 95%. Непроданный предмет автоматически возвращается через 7 дней. Все операции необратимы после подтверждения покупки.</p></div>
    ${btn('⚔ МОЙ АРСЕНАЛ','nav','ghost full','gear')}
  `;
}
function marketScreen(){return `${section('БАРТЕРНЫЙ РЫНОК','БЕЗ КОМИССИИ')}<div class="panel gm-link"><strong>⚔ Уникальное оружие и броня</strong><p class="smallnote">Отдельная биржа экипировки с характеристиками и оплатой крышками.</p>${btn('НА БИРЖУ СИЛЫ ↗','nav','small gold','gear-market')}</div><div class="panel"><div class="flex-between"><div><strong>Обмен между игроками</strong><p class="smallnote">Создай предложение и дождись покупателя</p></div>${btn('+ ЛОТ','market-create','gold')}</div></div><div class="list">${(lots||[]).map(l=>`<div class="row"><div class="symbol">${cfg.items[l.offer]?.icon||'◈'}</div><div class="row-main"><h3>${l.qty} × ${cfg.items[l.offer]?.name||'Предмет'}</h3><p>Требуется: ${l.want_qty} × ${cfg.items[l.want]?.name||'Предмет'}<br>Автор: ${esc(l.seller)}</p></div>${btn(l.seller_id===me.id?'Снять':'Обмен','market-'+(l.seller_id===me.id?'cancel':'buy'),'small gold',l.id)}</div>`).join('')||'<div class="empty">На рынке пока тихо</div>'}</div>`}
function pvpTimeoutButton(m){return m.state==='active'&&m.current_id!==me.id&&(Date.now()-new Date(m.updated_at).getTime())>(m.turn_seconds||90)*1000?btn('ЗАБРАТЬ ПОБЕДУ ПО ТАЙМЕРУ','pvp-act','gold','claim_timeout'):''}
function pvpScreen(){let m=pvp?.match;return `${section('АРЕНА ВЫЖИВШИХ','РЕЙТИНГ ELO')}<div class="panel"><h2 style="font:600 28px Oswald;margin:0">⚔ ${me.rating} <span style="font-size:13px;color:var(--muted)">ELO</span></h2><p class="smallnote">Лига: ${esc(pvp?.league?.name||'Бронзовая')}. Победа приносит до +35 крышек и +80 XP, рейтинг Elo зависит от соперника. Наградных дуэлей осталось: ${pvp?.remaining_rewarded??5}/${pvp?.daily_cap||5} за день; повтор одного соперника не награждается. На ход — 90 секунд.</p></div>${m?`<div class="card"><span class="tag">${{pending:'ОЖИДАНИЕ СОПЕРНИКА',active:'ДУЭЛЬ ИДЁТ'}[m.state]}</span><h3>${esc(m.challenger.name)} против ${esc(m.defender.name)}</h3><div class="bar-label"><span>${esc(m.challenger.name)}</span><em>${m.challenger.hp} HP</em></div>${bar(m.challenger.hp,Math.max(100,m.challenger.hp),'red')}<div class="bar-label"><span>${esc(m.defender.name)}</span><em>${m.defender.hp} HP</em></div>${bar(m.defender.hp,Math.max(100,m.defender.hp),'red')}<div class="combatlog mt">${m.log.map(t=>`<div>${esc(t)}</div>`).join('')}</div><div class="actions">${m.state==='pending'?(m.defender.id===me.id?btn('ПРИНЯТЬ','pvp-act','gold','accept')+btn('ОТКЛОНИТЬ','pvp-act','ghost','decline'):btn('Отозвать','pvp-act','ghost','cancel')):btn('⚔ АТАКА','pvp-act','red','attack',m.current_id!==me.id)+btn('💥 КРИТ','pvp-act','red','crit',m.current_id!==me.id)+btn('🛡 ЗАЩИТА','pvp-act','soft','defend',m.current_id!==me.id)+btn('🧰 ЛЕЧЕНИЕ','pvp-act','soft','heal',m.current_id!==me.id||!(me.inventory||[]).some(i=>i.key==='medkit'&&i.qty>0))+btn('🪙 КРАЖА','pvp-act','ghost','steal',m.current_id!==me.id)+btn('🗡 ФИНТ','pvp-act','soft','feint',m.current_id!==me.id)+btn('🕊 МИР','pvp-act','ghost','peace',m.current_id!==me.id)+btn('Сдаться','pvp-act','ghost','surrender')+pvpTimeoutButton(m)}</div></div>`:''}${section('БРОСИТЬ ВЫЗОВ','ИГРОКИ')}<div class="list">${(pvp?.players||[]).map(p=>`<div class="row"><div class="symbol">♙</div><div class="row-main"><h3>${esc(p.name)}</h3><p>Уровень ${p.level} · ${p.rating} ELO</p></div>${btn('Вызов','pvp-challenge','small gold',p.id,!!m)}</div>`).join('')||'<div class="empty">Пока нет других выживших. Пригласи друга!</div>'}</div>${m?btn('↻ Обновить бой','refresh','soft full'):''}`}
function casesScreen(){
 const catalog=Object.entries(cfg.cases||{}).sort((a,b)=>a[1].tier-b[1].tier);
 const chests=cfg.chests||[];
 const owned=key=>((me.inventory||[]).find(item=>item.key===key)||{}).qty||0;
 const rarityNames={common:'Обычная',uncommon:'Необычная',rare:'Редкая',epic:'Эпическая',legendary:'Легендарная'};
 return `${section('ПРЕМИУМ-СУНДУКИ','ТРИ УРОВНЯ · 3 / 4 / 5 НАГРАД')}<div class="case-intro"><span class="eyebrow">// ПРЕМИУМ-АРСЕНАЛ ZOMBO</span><h2>ОТКРОЙ НАХОДКУ.<br><b>СОБЕРИ КОЛЛЕКЦИЮ.</b></h2><p>Никаких кейсов за крышки или из обычного фарма. Каждый сундук содержит коллекционную пушку и дополнительные припасы. Деньги списываются только с баланса 💎 Zombo после оплаты Stars.</p><div class="case-stats"><span>💎 ${money(me.zombo)} ZOMBO</span><span>▣ ${catalog.length} КЕЙСОВ</span><span>⚔ 28 ПУШЕК</span></div></div>
 <div class="case-gallery premium-gallery">${chests.map(c=>{const stock=owned(c.key);return `<article class="case-item chest-tier ${c.key}"><div class="case-heading"><div class="case-illustration">${esc(c.icon)}</div><div><span class="eyebrow">ПРЕМИУМ · ${c.drops} НАГРАДЫ</span><h3>${esc(c.name)}</h3><p>${esc(c.desc)}</p></div></div><div class="case-odds">${Object.entries(c.rarity_weights||{}).map(([rarity,pct])=>`<span class="case-odds-cell rarity-${rarity}">${esc(rarityNames[rarity]||rarity)} <b>${pct}%</b></span>`).join('')}</div><p class="smallnote">Гарантия: ${esc(c.guarantee)}</p><div class="case-actions"><span class="case-owned">В наличии: ×${stock}</span>${stock?btn('🔓 ОТКРЫТЬ','chest-open','small gold',c.key):btn('💎 '+c.price,'premium-buy','small gold',c.key,me.zombo<c.price)}</div></article>`}).join('')}</div>
 ${section('КОЛЛЕКЦИИ ОРУЖИЯ','7 КЕЙСОВ · 28 ПУШЕК')}<div class="case-gallery">${catalog.map(([key,c])=>{const stock=owned(key);return `<article class="case-item tier-${Math.min(6,c.tier)}"><div class="case-heading"><div class="case-illustration">${esc(c.icon)}</div><div><span class="eyebrow">ПОКУПКА ЗА ZOMBO</span><h3>${esc(c.name)}</h3><p>${esc(c.desc)}</p></div></div><div class="case-odds">${Object.entries(c.rarity_weights||{}).map(([rarity,pct])=>`<span class="case-odds-cell rarity-${rarity}">${esc(rarityNames[rarity]||rarity)} <b>${pct}%</b></span>`).join('')}</div><div class="case-weapons">${(c.weapons||[]).map(id=>{const item=cfg.items[id]||{};return `<div class="case-weapon"><span>${esc(item.icon||'🔫')} ${esc(item.name||id)}</span><strong>⚔ ${Number(item.power)||0}</strong></div>`}).join('')}</div><div class="case-actions"><span class="case-owned">В наличии: ×${stock}</span>${stock?btn('🔓 ОТКРЫТЬ','case-open','small gold',key):btn('💎 '+c.gem_price,'premium-buy','small gold',key,me.zombo<c.gem_price)}</div></article>`}).join('')}</div>
 <div class="panel mt"><h3>ЧЕСТНЫЕ ШАНСЫ</h3><p class="smallnote">Шансы внутри кейсов и сундуков указаны до оплаты. Обычный сундук гарантирует оружие обычной редкости или выше, редкий — редкой или выше, легендарный — эпической или легендарной. Старые кейсы, уже лежащие в инвентаре, сохраняются и открываются.</p>${btn('💎 ПОПОЛНИТЬ ZOMBO','nav','gold full','stars')}</div>`;
}
function shopScreen(){return `${section('ТОРГОВЕЦ','КРЫШКИ')}<div class="panel"><div class="flex-between"><div><h3>🎁 Кейсы — теперь в премиуме</h3><p class="smallnote">Сундуки и коллекционное оружие доступны за 💎 Zombo, а здесь — полезные припасы за крышки.</p></div>${btn('СУНДУКИ ↗','nav','small gold','cases')}</div></div><div class="list">${(shop||[]).map(item=>`<div class="row"><div class="symbol">${item.icon}</div><div class="row-main"><h3>${item.name}</h3><p>${item.desc||'Полезно в пустоши'}</p></div>${btn(`<span class="merchant-price"><span class="merchant-coin" aria-hidden="true">C</span><span class="merchant-amount">${money(item.price)}</span></span>`,'shop-buy','small gold merchant-buy',item.key,me.caps<item.price)}</div>`).join('')}</div>`}
function starsScreen(){const offers=premium||[];const upgrades=offers.filter(o=>!['case','chest'].includes(o.kind));
 return `${section('ZOMBO PREMIUM','СУНДУКИ И ПОКУПКИ')}<div class="panel"><div class="flex-between"><div><h3>Баланс: 💎 ${money(me.zombo)} Zombo</h3><p class="smallnote">Прозрачные шансы и настоящие награды. Кейсы за крышки больше не продаются.</p></div>${btn('К СУНДУКАМ','nav','small gold','cases')}</div></div>
 ${section('БОЕВЫЕ УЛУЧШЕНИЯ','VIP · УСИЛЕНИЯ')}<div class="list">${upgrades.map(o=>`<div class="row"><div class="symbol">${o.kind==='vip'?'♛':o.kind==='xp'?'✧':'◈'}</div><div class="row-main"><h3>${esc(o.name)}</h3><p>${esc(o.desc)}</p></div>${btn('💎 '+o.price,'premium-buy','small gold',o.key,me.zombo<o.price)}</div>`).join('')}</div>
 ${section('ПОПОЛНИТЬ СЧЁТ','TELEGRAM STARS')}<div class="notice">Оплата проходит внутри Telegram Stars. После подтверждённого платежа валюта начисляется на счёт. Сундуки покупаются за 💎 Zombo, а не за крышки.</div><div class="grid">${(stars||[]).map(o=>`<div class="card"><div class="card-icon">💎</div><h3>${money(o.zombo)} Zombo</h3><p>Для кейсов, сундуков и VIP</p>${btn('⭐ '+o.stars,'stars-buy','gold full',o.key)}</div>`).join('')}</div>`;
}
function leadersScreen(){const metric=p=>leaderboardSort==='kills'?`${money(p.kills)} ☠`:leaderboardSort==='pvp'?`${money(p.rating)} ELO`:`LVL ${p.level}`;return `${section('ТАБЛИЦА ЛИДЕРОВ','ТОП 30')}<div class="tabs">${[['level','УРОВЕНЬ'],['kills','ЗАРАЖЁННЫЕ'],['pvp','АРЕНА']].map(([key,label])=>`<button class="${leaderboardSort===key?'active':''}" data-action="leader-sort" data-value="${key}">${label}</button>`).join('')}</div><div class="list">${(leaderboard||[]).map((p,i)=>`<div class="row"><div class="symbol">${i<3?['🥇','🥈','🥉'][i]:i+1}</div><div class="row-main"><h3>${esc(p.name)}</h3><p>${cfg.classes[p.class]?.name||'Герой'} · ур. ${p.level} · ${p.kills} зомби · ${p.pvp_wins} PvP</p></div><strong class="leader-score">${metric(p)}</strong></div>`).join('')||'<div class="empty">Рейтинг пока пуст.</div>'}</div>`}
function classes(){return `<div class="hero" style="min-height:160px"><div class="hero-text" style="max-width:95%"><div class="eyebrow">// НОВАЯ ИСТОРИЯ</div><h1>КТО ТЫ, ВЫЖИВШИЙ?</h1><p>Выбор класса делается один раз. От него зависит стиль боя и доступные способности.</p></div></div>${section('ВЫБОР КЛАССА','4 АРХЕТИПА')}<div class="class-grid">${Object.entries(cfg.classes).map(([key,c])=>`<button class="class-option ${choice===key?'selected':''}" data-action="choose" data-value="${key}"><div class="art">${art(key)}</div><div class="detail"><div class="tag">${c.subtitle}</div><h3>${c.name}</h3><p>${c.bonus}</p></div></button>`).join('')}</div><div class="panel mt"><p class="smallnote">Решение нельзя будет изменить. Каждый класс имеет три уникальные ветки талантов: 9 способностей, по 3 ранга каждой.</p>${btn('НАЧАТЬ ВЫЖИВАНИЕ ↗','class-confirm','gold full','',!choice)}</div>`}
function modalView(){if(!modal)return '';return `<div class="modal-bg" data-action="close"><div class="modal"><h2>${modal.title}</h2>${modal.body}<div class="actions">${btn(modal.actionLabel||'Подтвердить',modal.action||'close','gold')}${btn('Отмена','close','soft')}</div></div></div>`}
function showModal(title,body,action,actionLabel){modal={title,body,action,actionLabel};render()}
function adminGrantEntries(kind){
 const catalog=adminGrantCatalog||{};
 const group={currency:'currencies',item:'items',gear:'gear',pet:'pets',premium:'premium'}[kind]||'items';
 return Object.entries(catalog[group]||{}).map(([key,v])=>({key,name:v.name||key,icon:v.icon||'',category:v.type||v.slot||''}))
   .sort((a,b)=>(a.category+a.name).localeCompare(b.category+b.name,'ru'));
}
function fillAdminGrantItems(kind,search=''){
 const selector=document.getElementById('admin-gift-key');
 if(!selector)return;
 const query=search.trim().toLocaleLowerCase('ru');
 const old=selector.value;selector.replaceChildren();
 const rows=adminGrantEntries(kind).filter(x=>!query||(x.name+' '+x.key+' '+x.category).toLocaleLowerCase('ru').includes(query));
 for(const option of rows){
   const o=document.createElement('option');o.value=option.key;
   o.textContent=(option.icon?option.icon+' ':'')+option.name+' ['+option.key+']';
   selector.append(o);
 }
 if(rows.some(x=>x.key===old))selector.value=old;
 const count=document.getElementById('admin-gift-count');if(count)count.textContent=rows.length+' доступных позиций';
 const rarity=document.getElementById('admin-gift-rarity-row');
 const level=document.getElementById('admin-gift-level-row');
 const amount=document.getElementById('admin-gift-amount-row');
 if(rarity)rarity.hidden=kind!=='gear';
 if(level)level.hidden=!['gear','pet'].includes(kind);
 if(amount)amount.hidden=['pet','premium'].includes(kind);
}
function adminScreen(){if(!me.admin)return '<div class="empty">Доступ закрыт</div>';const s=adminSummary||{};const stats=[['Игроки',s.players],['Активность 7 дн.',s.active_7d],['Убийства PvE',s.zombie_kills],['Матчи PvP',s.pvp_matches],['Рейды',s.raids],['Клановые войны',s.wars],['Бартер',s.barter_active],['Продажи экипировки',s.gear_sold],['Платежи Stars',s.payments],['На проверку',s.payments_for_review],['Получено Stars',s.stars_received],['Крышки игроков',s.caps_in_wallets],['Zombo игроков',s.zombo_in_wallets]];
let content='';if(adminTab==='economy'){const e=adminEconomy||{};const f=e.wallet_flows||[];
content=`<div class="panel"><h3>Движение игровой экономики</h3><p class="smallnote">${esc(e.warning||'Учёт только после запуска журнала.')}</p><div class="actions">${[1,7,30,90].map(d=>btn(d+' ДН.','admin-economy-days',adminEconomyDays===d?'gold':'soft',d)).join('')}</div></div>
<div class="admin-stats">${[['Крышки игроков',e.wallet_caps_now],['Казна кланов',e.treasury_caps_now],['Крышки игроков + казна',e.combined_caps_now],['Изменение за период',e.net_combined_caps],['Получено XP (нетто)',e.net_xp],['Zombo (изменение)',e.net_wallet_zombo]].map(([label,value])=>`<div class="stat-chip"><small>${esc(label)}</small><strong>${money(value)}</strong></div>`).join('')}</div>
<div class="panel"><h3>Доходы и расходы · ${esc(e.days||7)} дней</h3><div class="list">${f.map(row=>`<div class="row"><div class="row-main"><h3>${esc(row.key)}</h3><p>Поступило: +${money(row.inflow)} · Потрачено: −${money(row.outflow)} · Итого: ${money(row.net)} · операций: ${money(row.operations)}</p></div></div>`).join('')||'<div class="empty">Операций в этом периоде нет.</div>'}</div></div>
<div class="panel"><h3>Казна по кланам</h3><div class="list">${(e.treasury_flows||[]).map(row=>`<div class="row"><div class="row-main"><h3>Клан #${esc(row.key)}</h3><p>+${money(row.inflow)} / −${money(row.outflow)} · итого ${money(row.net)}</p></div></div>`).join('')||'<div class="empty">Движений казны нет.</div>'}</div></div>`;}if(adminTab==='players'){content=`<div class="panel"><label>Поиск по ID, имени или username</label><div class="admin-search"><input id="admin-q" value="${esc(adminQuery)}" maxlength="90" placeholder="ID или имя">${btn('НАЙТИ','admin-search','small gold')}</div><div class="admin-filters"><div><label>Класс</label><select id="admin-class"><option value="">Все классы</option>${Object.entries(cfg.classes).map(([key,c])=>`<option value="${key}" ${adminClass===key?'selected':''}>${esc(c.name)}</option>`).join('')}</select></div><div><label>Уровень от</label><input id="admin-level" type="number" min="1" max="1000" value="${adminMinLevel}"></div></div><p class="smallnote">Результаты по 20 игроков. Управление требует причины и записывается в журнал.</p></div><div class="list">${(adminPlayers?.items||[]).map(p=>`<div class="row"><div class="row-main"><h3>${esc(p.name)} · #${p.id}</h3><p>${esc(p.username||'')} · LVL ${p.level} · ${esc(p.class||'без класса')} · ${p.banned?'БАН':p.frozen?'ЗАМОРОЖЕН':'активен'}</p></div>${btn('ОТКРЫТЬ','admin-open','small ghost',p.id)}</div>`).join('')||'<div class="empty">Игроки не найдены</div>'}</div><div class="actions">${btn('←','admin-page','soft',adminPage-1,adminPage<=1)}<span class="tag">СТР. ${adminPage}</span>${btn('→','admin-page','soft',adminPage+1,!adminPlayers?.has_next)}</div>`;
if(adminDetail){const p=adminDetail;content+=`<div class="panel admin-detail"><div class="flex-between"><h3>${esc(p.name)} · #${p.id}</h3>${btn('ЗАКРЫТЬ','admin-close','small ghost')}</div><p class="smallnote">${esc(p.class||'без класса')} · LVL ${p.level} · XP ${p.xp} · ${esc(p.location)} · клан: ${esc(p.clan||'нет')} · глава ${p.story_chapter}/10</p><p>❤️ ${p.hp} · ⚡ ${p.stamina} · 🪙 ${money(p.caps)} · 💎 ${money(p.zombo)} · ELO ${p.rating}</p><p class="smallnote">🐾 Питомец: ${p.pet?esc(p.pet.name)+' · уровень '+p.pet.level:'нет'} · 👑 VIP: ${p.vip_until?esc(p.vip_until):'не активен'}</p><p class="smallnote">Снаряжение: ${(p.gear||[]).map(g=>esc(g.name)+' +'+g.level).join(', ')||'нет'}<br>Инвентарь: ${(p.inventory||[]).map(i=>esc(cfg.items[i.key]?.name||i.key)+' ×'+i.quantity).join(', ')||'пусто'}</p><div class="actions">${btn(p.banned?'РАЗБАН':'БАН','admin-status',p.banned?'ghost':'red',`banned:${p.banned?0:1}`)}${btn(p.frozen?'РАЗМОРОЗИТЬ':'ЗАМОРОЗИТЬ','admin-status','soft',`frozen:${p.frozen?0:1}`)}${btn('ВЫДАТЬ ЛЮБОЙ ПРЕДМЕТ','admin-grant','gold')}${btn('КРЫШКИ / XP','admin-resource','soft')}</div></div>`}}
if(adminTab==='audit')content=`<div class="panel"><p class="smallnote">Экспорт до 5 000 последних записей журнала CSV.</p>${btn('↓ ЭКСПОРТ CSV','admin-export','gold')}</div><div class="list">${(adminAudit?.items||[]).map(x=>`<div class="row"><div class="row-main"><h3>#${x.id} · ${esc(x.action)} · ${esc(x.field)}</h3><p>${esc(x.created_at)} · ${x.actor_id} → ${x.target_id}<br>${esc(x.before)} → ${esc(x.after)} · ${esc(x.reason)}</p></div></div>`).join('')||'<div class="empty">Записей пока нет</div>'}</div><div class="actions">${btn('←','admin-audit-page','soft',adminAuditPage-1,adminAuditPage<=1)}<span class="tag">СТР. ${adminAuditPage}</span>${btn('→','admin-audit-page','soft',adminAuditPage+1,!adminAudit?.has_next)}</div>`;
if(adminTab==='transactions'){const t=adminTransactions||{};content=`${section('ПРОДАЖИ ЭКИПИРОВКИ')}<div class="list">${(t.sales||[]).map(x=>`<div class="row"><div class="row-main"><h3>Лот #${x.id} · ${esc(x.status)}</h3><p>${x.seller_id} → ${x.buyer_id||'—'} · ${money(x.price)} крышек · комиссия ${x.fee}</p></div></div>`).join('')||'<div class="empty">Нет сделок</div>'}</div>${section('ПЛАТЕЖИ TELEGRAM')}<div class="list">${(t.payments||[]).map(x=>`<div class="row"><div class="row-main"><h3>Игрок #${x.player_id}</h3><p>${x.stars} Stars → ${x.zombo} Zombo · ${esc(x.created_at)}</p></div></div>`).join('')||'<div class="empty">Нет платежей</div>'}</div>${section('РЕЙДОВЫЕ НАГРАДЫ')}<div class="list">${(t.raid_rewards||[]).map(x=>`<div class="row"><div class="row-main"><h3>Рейд #${x.run_id} · игрок #${x.player_id}</h3><p>Вклад: ${x.contribution}</p></div></div>`).join('')||'<div class="empty">Нет выдач</div>'}</div>`}
if(adminTab==='transactions')content=`${section('ПЛАТЕЖИ НА ПРОВЕРКУ',String(adminSummary?.payments_for_review||0))}<div class="list">${(adminTransactions?.payment_reviews||[]).map(x=>`<div class="row"><div class="row-main"><h3>Игрок #${x.player_id} · ${x.amount} ${esc(x.currency)}</h3><p>${esc(x.reason)} · ${esc(x.created_at)}<br>Telegram charge: ${esc(x.charge_id)}</p></div></div>`).join('')||'<div class="empty">Нет платежей, требующих проверки</div>'}</div>`+content;
if(adminTab==='risk'){const r=adminRisk||{};content=`<div class="panel"><h3>КОНТРОЛЬ ЭКОНОМИКИ</h3><p class="smallnote">${esc(r.disclaimer||'Требуется проверка человеком.')} За 7 дней просмотрено ${money(r.transactions_examined)} сделок из 500 последних. Автоматических блокировок нет.</p><p><strong>Сигналов: ${money(r.total_findings)}</strong></p></div><div class="list">${(r.findings||[]).map(f=>`<div class="row"><div class="symbol">${f.severity==='high'?'⚠':'⌕'}</div><div class="row-main"><h3>${esc(f.title)}</h3><p>${esc(f.description)}<br>${esc(f.created_at)} · игрок #${f.player_id}${f.related_player_id?' ↔ #'+f.related_player_id:''}</p></div>${f.player_id?btn('ИГРОК','admin-risk-player','small ghost',f.player_id):''}</div>`).join('')||'<div class="empty">Подозрительных операций по заданным правилам не найдено.</div>'}</div>`}
if(adminTab==='events'){
 const data=adminWorldEvents?.events||[],labels={scheduled:'ЗАПЛАНИРОВАНО',active:'ИДЁТ',finished:'ЗАВЕРШЕНО',stopped:'ОСТАНОВЛЕНО'};
 content=`<div class="panel"><h3>МИРОВЫЕ СОБЫТИЯ</h3><p class="smallnote">Запланируй орду заражённых или военный груз. Эффект применяется к реальным действиям игроков только в выбранной локации. Изменения записываются в административный журнал.</p>${btn('＋ СОЗДАТЬ СОБЫТИЕ','admin-event-create','gold')}</div><div class="list">${data.map(e=>`<div class="row"><div class="row-main"><h3>#${e.id} · ${esc(e.name)} <span class="tag">${esc(labels[e.status]||e.status)}</span></h3><p>${esc(cfg.locations[e.location]?.name||e.location)} · ${esc(new Date(e.starts_at).toLocaleString('ru-RU'))} → ${esc(new Date(e.ends_at).toLocaleString('ru-RU'))}<br>Прогресс: ${money(e.progress)} / ${money(e.goal)}</p></div>${['active','scheduled'].includes(e.status)?btn('СТОП','admin-event-stop','small red',e.id):''}</div>`).join('')||'<div class="empty">События ещё не создавались.</div>'}</div>`;
}
if(adminTab==='ledger'){const rows=adminLedger?.items||[];content=`<div class="panel admin-filters"><div><label>ID игрока</label><input id="admin-ledger-player" type="number" min="1" value="${esc(adminLedgerPlayer)}" placeholder="Все игроки"></div><div><label>Ресурс</label><select id="admin-ledger-kind">${[['','Все'],['currency','Валюта'],['item','Предметы'],['gear','Снаряжение'],['xp','Опыт']].map(([key,label])=>`<option value="${key}" ${adminLedgerKind===key?'selected':''}>${label}</option>`).join('')}</select></div>${btn('ПОКАЗАТЬ','admin-ledger-filter','small gold')}</div><div class="list">${rows.map(row=>`<div class="row"><div class="row-main"><h3>#${row.id} · Игрок #${row.player_id} · ${row.delta>0?'+':''}${money(row.delta)} ${esc(row.resource_key)}</h3><p>${esc(row.kind)} · ${esc(row.created_at)}${row.balance_after!==null?' · после: '+money(row.balance_after):''}<br>${esc(row.source_event)}</p></div></div>`).join('')||'<div class="empty">Записей с такими фильтрами нет.</div>'}</div><div class="actions">${btn('←','admin-ledger-page','soft',adminLedgerPage-1,adminLedgerPage<=1)}<span class="tag">СТР. ${adminLedgerPage}</span>${btn('→','admin-ledger-page','soft',adminLedgerPage+1,!adminLedger?.has_next)}</div>`}
if(adminTab==='diagnostics'){const o=adminOperations||{},n=adminNotifications||{};const metrics=[['Рейды: набор',o.raids_lobby],['Рейды: в бою',o.raids_active],['Рейды: просрочены',o.raids_overdue],['Экспедиции: активны',o.expeditions_active],['Экспедиции: просрочены',o.expeditions_overdue],['Очередь: ожидают',o.notifications_pending],['Очередь: готовы',o.notifications_due],['Отправляются',o.notifications_sending],['Зависшие аренды',o.notifications_stuck],['Ошибки за 24 ч',o.notifications_failed_24h]];content=`<div class="panel"><h3>СОСТОЯНИЕ ОПЕРАЦИЙ</h3><p class="smallnote">Проверено: ${esc(o.checked_at||'—')}. Старейшее ожидающее сообщение: ${esc(o.oldest_due_at||'нет')}.</p><div class="admin-stats">${metrics.map(([label,value])=>`<div class="stat-chip"><small>${esc(label)}</small><strong>${money(value||0)}</strong></div>`).join('')}</div></div>${section('ОЧЕРЕДЬ TELEGRAM','БЕЗ ТЕКСТОВ СООБЩЕНИЙ')}<div class="panel admin-filters"><div><label>Статус</label><select id="admin-notice-status">${[['','Все'],['pending','Ожидает'],['sending','Отправляется'],['sent','Отправлено'],['skipped','Пропущено'],['failed','Ошибка']].map(([key,label])=>`<option value="${key}" ${adminNoticeStatus===key?'selected':''}>${label}</option>`).join('')}</select></div><div><label>Категория</label><select id="admin-notice-category">${[['','Все'],['expeditions','Экспедиции'],['market','Рынок'],['raids','Рейды'],['clans','Кланы']].map(([key,label])=>`<option value="${key}" ${adminNoticeCategory===key?'selected':''}>${label}</option>`).join('')}</select></div>${btn('ПОКАЗАТЬ','admin-notice-filter','small gold')}</div><div class="list">${(n.items||[]).map(row=>`<div class="row"><div class="row-main"><h3>#${row.id} · ${esc(row.category)} · ${esc(row.status)}</h3><p>Игрок #${row.player_id} · ${esc(row.kind)} · попыток ${row.attempts}<br>Запланировано: ${esc(row.scheduled_at)}${row.last_error?' · '+esc(row.last_error):''}</p></div></div>`).join('')||'<div class="empty">Событий с такими фильтрами нет.</div>'}</div><div class="actions">${btn('←','admin-notice-page','soft',adminNoticePage-1,adminNoticePage<=1)}<span class="tag">СТР. ${adminNoticePage}</span>${btn('→','admin-notice-page','soft',adminNoticePage+1,!n.has_next)}</div>`}
if(adminTab==='treasury'){const rows=adminTreasury?.items||[];content=`<div class="panel admin-filters"><div><label>ID клана</label><input id="admin-treasury-clan" type="number" min="1" value="${esc(adminTreasuryClan)}" placeholder="Все кланы"></div>${btn('ПОКАЗАТЬ','admin-treasury-filter','small gold')}</div><div class="list">${rows.map(row=>`<div class="row"><div class="row-main"><h3>#${row.id} · Клан #${row.clan_id} · ${row.delta>0?'+':''}${money(row.delta)} крышек</h3><p>Баланс казны: ${money(row.balance_after)} · ${esc(row.created_at)}<br>${esc(row.source_event)}</p></div></div>`).join('')||'<div class="empty">Операций казны пока нет.</div>'}</div><div class="actions">${btn('←','admin-treasury-page','soft',adminTreasuryPage-1,adminTreasuryPage<=1)}<span class="tag">СТР. ${adminTreasuryPage}</span>${btn('→','admin-treasury-page','soft',adminTreasuryPage+1,!adminTreasury?.has_next)}</div>`}
return `${section('АДМИНСКИЙ ТЕРМИНАЛ','ДОСТУП ПО TELEGRAM ID')}<div class="notice">Выдавай материалы, сундуки, пушки, питомцев, VIP и 💎 Zombo. Все операции фиксируются в журнале. Ручное начисление не является покупкой Stars.</div><div class="admin-stats">${stats.map(([label,value])=>`<div class="stat-chip"><small>${esc(label)}</small><strong>${money(value)}</strong></div>`).join('')}</div><div class="actions">${[['players','ИГРОКИ'],['audit','ЖУРНАЛ'],['transactions','ОПЕРАЦИИ'],['ledger','РЕСУРСЫ'],['treasury','КАЗНА'],['economy','ЭКОНОМИКА'],['risk','РИСКИ'],['events','СОБЫТИЯ'],['diagnostics','ДИАГНОСТИКА']].map(([key,label])=>btn(label,'admin-tab',adminTab===key?'gold':'soft',key)).join('')}</div><div class="mt">${content}</div>`}
function render(){document.title='ZOMBO · AFTER THE FALL';if(!me||!cfg)return;const page=!me.class?classes():({home,map,profile,talents:talentsScreen,more,fight,inventory:inventoryScreen,craft:craftScreen,quests:questsScreen,boss:bossScreen,clan:clanScreen,market:marketScreen,'gear-market':gearMarketScreen,pvp:pvpScreen,raids:raidScreen,expeditions:expeditionScreen,shop:shopScreen,cases:casesScreen,gear:gearScreen,pets:petsScreen,story:storyScreen,stars:starsScreen,leaders:leadersScreen,bestiary:bestiaryScreen,notifications:notificationsScreen,'world-events':worldEventsScreen,encounters:encountersScreen,admin:adminScreen}[screen]||home)();app.innerHTML=`<div class="app-shell">${header()}${screenPath()}<main>${page}</main>${me.class?navBar():''}</div>${modalView()}`;applySearch('inventory');applySearch('craft');applySearch('gear');syncTelegramBack()}
const forms={
 'clan-create':['ОСНОВАТЬ КЛАН','<label>Название (3–30 символов)</label><input id="input-name" maxlength="30" placeholder="Стальные волки" autocomplete="off"><p>Стоимость: 250 крышек</p>','submit-clan','Создать клан'],
 'clan-donate':['КАЗНА КЛАНА','<label>Количество крышек</label><input id="input-qty" type="number" min="1" value="50">','submit-donate','Внести'],

};
async function handle(action,value){
  if(loading&&action!=='close')return;
  if(action==='close'){modal=null;render();return}
   if(action==='loot-to-inventory'){modal=null;inventoryFilter='all';inventoryQuery='';await nav('inventory');render();return}
  if(action==='pet-adopt'){await act('pets/adopt',{key:value});return}
  if(action==='back'){await goBack();return}
  if(action==='nav'){modal=null;await nav(value);return}
  if(action==='leader-sort'){if(navigationBusy)return;const previous=leaderboardSort;leaderboardSort=['level','kills','pvp'].includes(value)?value:'level';navigationBusy=true;try{await fetchScreen();render()}catch(e){leaderboardSort=previous;notice(e.message,true)}finally{navigationBusy=false}return}
  if(action==='gear-filter'){gearSlotFilter=value;render();return}
   if(action==='gear-repair-all'){
     const items=(me.gear||[]).filter(g=>g.equipped&&g.repair_cost);
     if(!items.length){notice('Экипировка уже в порядке');return}
     const caps=items.reduce((n,g)=>n+g.repair_cost.caps,0);
     showModal('ПОЧИНИТЬ ВЕСЬ КОМПЛЕКТ?',`<p>Починить ${items.length} надетых предметов до 100% прочности за ${money(caps)} крышек и материалы?</p><p class="smallnote">Если чего-то не хватит, операция будет отменена целиком.</p>`,'gear-repair-all-confirm','ПОЧИНИТЬ');
     return;
   }
   if(action==='gear-repair-all-confirm'){modal=null;await act('gear/repair-all',null);return}
   if(action==='inventory-filter'){inventoryFilter=value;render();return}
   if(action==='craft-filter'){craftFilter=value;render();return}
   if(action==='craft-available'){craftReadyOnly=!craftReadyOnly;render();return}
   if(action==='refresh'){await sync();return}
  if(action==='choose'){choice=value;render();return}
  if(action==='zone'){zone=value;render();return}
  if(action==='territory-select'){selectedTerritory=value;render();return}
  if(action==='talent-path'){activePath=Math.max(0,Math.min(2,Number(value)||0));render();return}
  if(action==='skill-reset'){showModal('Сбросить таланты?',`<p>Возврат ${me.talent_spent} очков для нового распределения по веткам.</p><p class="smallnote">Стоимость: ${me.talent_reset_cost?money(me.talent_reset_cost)+' крышек':'бесплатно'}. Персонаж и уровень не изменятся.</p>`,'skill-reset-confirm','ПОДТВЕРДИТЬ СБРОС');return}
  if(action==='skill-reset-confirm'){modal=null;await act('skill/reset',null);return}
  if(action==='admin-export'){
    if(loading)return;
    loading=true;
    try{
      const response=await fetch('/api/admin/audit/export?limit=5000',{headers:{Authorization:auth},cache:'no-store'});
      if(!response.ok)throw new Error('Не удалось выгрузить журнал');
      const blob=await response.blob(),filename='zombo-admin-audit.csv';
      const file=new File([blob],filename,{type:'text/csv'});
      if(navigator.share&&navigator.canShare&&navigator.canShare({files:[file]})){
        await navigator.share({files:[file],title:'Журнал ZOMBO'});
      }else{
        const url=URL.createObjectURL(blob),link=document.createElement('a');
        link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();
        setTimeout(()=>URL.revokeObjectURL(url),30000);
      }
      notice('Журнал подготовлен');
    }catch(err){if(err.name!=='AbortError')notice(err.message,true)}finally{loading=false}
    return;
  }
  if(action==='admin-risk-player'){adminTab='players';adminQuery=value;adminDetail=null;adminPage=1;await fetchAdmin();render();return}
  if(action==='notify-toggle'){
    const enabled=!Boolean(notificationData?.settings?.[value]);
    const result=await act('notifications/settings',{category:value,enabled},false);
    if(result){notificationData=await api('notifications');render()}
    return;
  }
  if(action==='encounter-explore'){
    const result=await act('encounters/explore',null,false);
    if(result){
      me=await api('me');
      if(screen!=='encounters')actionScreen('encounters');
      encounterData=await api('encounters');
      render();
    }
    return;
  }
  if(action==='encounter-resolve'){
    const option=encounterData?.encounter?.choices?.[value];
    if(!option||option.locked)return;
    if(value!=='leave'){
      showModal('ПРИНЯТЬ РЕШЕНИЕ?',`<p><b>${esc(option.label)}</b></p><p class="smallnote">${esc(option.hint)}</p><p class="smallnote">После подтверждения изменить выбор нельзя.</p>`,'encounter-resolve-confirm','ПОДТВЕРДИТЬ');
      modal.choice=value;
      return;
    }
  }
  if(action==='encounter-resolve'||action==='encounter-resolve-confirm'){
    const selected=action==='encounter-resolve-confirm'?modal?.choice:value;
    if(!selected)return;
    const result=await act('encounters/resolve',{action:selected},false);
    if(result){
      modal=null;
      me=await api('me');
      encounterData=await api('encounters');
      render();
    }
    return;
  }
  if(action==='world-event-claim'){
    const result=await act('world-events/claim',{id:Number(value)},false);
    if(result){worldEvents=await api('world-events');me=await api('me');render()}
    return;
  }
  if(action==='admin-event-create'){
    const types=[['horde','Орда заражённых'],['supplies','Военный груз']];
    const zones=Object.entries(cfg.locations).filter(([id])=>id!=='base');
    showModal('ЗАПЛАНИРОВАТЬ СОБЫТИЕ',`<label>Тип события</label><select id="event-type">${types.map(([key,name])=>`<option value="${key}">${esc(name)}</option>`).join('')}</select><label>Локация</label><select id="event-zone">${zones.map(([key,z])=>`<option value="${key}">${esc(z.name)}</option>`).join('')}</select><label>Запуск через (минут, 0 = сейчас)</label><input id="event-delay" type="number" min="0" max="10080" value="0"><label>Продолжительность (минут, 30–1440)</label><input id="event-duration" type="number" min="30" max="1440" value="120"><label>Причина</label><textarea id="event-reason" rows="2" maxlength="300" placeholder="Игровое событие для всех выживших"></textarea>`,'admin-event-create-confirm','ЗАПЛАНИРОВАТЬ');
    modal.requestId=crypto.randomUUID();return;
  }
  if(action==='admin-event-create-confirm'){
    const reason=document.getElementById('event-reason')?.value.trim()||'';
    const delay=Number(document.getElementById('event-delay')?.value);
    const duration=Number(document.getElementById('event-duration')?.value);
    if(reason.length<5||!Number.isInteger(delay)||delay<0||delay>10080||!Number.isInteger(duration)||duration<30||duration>1440){notice('Проверь причину, время и длительность',true);return}
    const body={type:document.getElementById('event-type').value,location:document.getElementById('event-zone').value,starts_in_minutes:delay,duration_minutes:duration,reason,request_id:modal.requestId};
    const result=await act('admin/world-events/create',body,false);
    if(result){modal=null;await fetchAdmin();render()}return;
  }
  if(action==='admin-event-stop'){
    const event=(adminWorldEvents?.events||[]).find(e=>String(e.id)===value);
    if(!event){notice('Событие не найдено',true);return}
    showModal('ОСТАНОВИТЬ СОБЫТИЕ?',`<p>${esc(event.name)} · #${event.id}</p><label>Причина остановки</label><textarea id="event-reason" rows="2" maxlength="300"></textarea>`,'admin-event-stop-confirm','ОСТАНОВИТЬ');
    modal.eventId=event.id;modal.requestId=crypto.randomUUID();return;
  }
  if(action==='admin-event-stop-confirm'){
    const reason=document.getElementById('event-reason')?.value.trim()||'';
    if(reason.length<5){notice('Укажи причину (минимум 5 символов)',true);return}
    const result=await act('admin/world-events/'+modal.eventId+'/stop',{reason,request_id:modal.requestId},false);
    if(result){modal=null;await fetchAdmin();render()}return;
  }
  if(action==='admin-tab'){adminTab=value;adminDetail=null;await fetchAdmin();render();return}
  if(action==='admin-economy-days'){adminEconomyDays=[1,7,30,90].includes(Number(value))?Number(value):7;await fetchAdmin();render();return}
  if(action==='admin-search'){adminQuery=document.getElementById('admin-q')?.value?.trim()||'';adminClass=document.getElementById('admin-class')?.value||'';adminMinLevel=Math.max(1,Math.min(1000,Number(document.getElementById('admin-level')?.value)||1));adminPage=1;adminDetail=null;await fetchAdmin();render();return}
  if(action==='admin-page'){adminPage=Math.max(1,Number(value)||1);adminDetail=null;await fetchAdmin();render();return}
  if(action==='admin-audit-page'){adminAuditPage=Math.max(1,Number(value)||1);await fetchAdmin();render();return}
  if(action==='admin-treasury-filter'){adminTreasuryClan=document.getElementById('admin-treasury-clan')?.value||'';adminTreasuryPage=1;await fetchAdmin();render();return}
  if(action==='admin-treasury-page'){adminTreasuryPage=Math.max(1,Number(value)||1);await fetchAdmin();render();return}
  if(action==='admin-ledger-filter'){adminLedgerPlayer=document.getElementById('admin-ledger-player')?.value||'';adminLedgerKind=document.getElementById('admin-ledger-kind')?.value||'';adminLedgerPage=1;await fetchAdmin();render();return}
  if(action==='admin-ledger-page'){adminLedgerPage=Math.max(1,Number(value)||1);await fetchAdmin();render();return}
  if(action==='admin-notice-filter'){adminNoticeStatus=document.getElementById('admin-notice-status')?.value||'';adminNoticeCategory=document.getElementById('admin-notice-category')?.value||'';adminNoticePage=1;await fetchAdmin();render();return}
  if(action==='admin-notice-page'){adminNoticePage=Math.max(1,Number(value)||1);await fetchAdmin();render();return}
  if(action==='admin-open'){adminDetail=await api('admin/players/'+Number(value));render();return}
  if(action==='admin-close'){adminDetail=null;render();return}
  if(action==='admin-status'){if(!adminDetail)return;let [field,v]=value.split(':');showModal('ИЗМЕНИТЬ СТАТУС?',`<p>${esc(adminDetail.name)} · #${adminDetail.id}: ${field==='banned'?'бан':'заморозка'} = ${v==='1'?'да':'нет'}</p><label>Причина (минимум 5 символов)</label><textarea id="admin-reason" maxlength="300" rows="3"></textarea>`,'admin-status-confirm','ПОДТВЕРДИТЬ');modal.payload={field,value:v==='1',request_id:crypto.randomUUID()};return}
  if(action==='admin-grant'){
   if(!adminDetail)return;
   if(!adminGrantCatalog){notice('Каталог ещё загружается',true);return}
   const rarities=Object.entries(adminGrantCatalog.rarities||{});
   showModal('ВЫДАЧА ИГРОВОГО ИМУЩЕСТВА',`<p><strong>${esc(adminDetail.name)} · #${adminDetail.id}</strong></p><p class="smallnote">Материалы, расходники, кейсы, сундуки, редкая экипировка, питомцы, VIP и 💎 Zombo. Все выдачи фиксируются в журнале. Ручное Zombo не является платежом Stars.</p><label>Категория выдачи</label><select id="admin-gift-kind"><option value="item">📦 Все предметы / сундуки / кейсы</option><option value="currency">🪙 Крышки / XP / Zombo</option><option value="gear">⚔ Оружие / броня</option><option value="pet">🐺 Питомец</option><option value="premium">👑 VIP / буст / страховка</option></select><label>Поиск по каталогу</label><input id="admin-gift-search" placeholder="Название или ключ" maxlength="80"><span id="admin-gift-count" class="smallnote"></span><label>Выбери награду</label><select id="admin-gift-key"></select><div id="admin-gift-amount-row"><label>Количество (для валюты — сколько начислить)</label><input id="admin-gift-amount" type="number" min="1" max="1000000" step="1" value="1"></div><div id="admin-gift-rarity-row" hidden><label>Редкость экипировки</label><select id="admin-gift-rarity">${rarities.map(([key,name])=>`<option value="${esc(key)}">${esc(name)}</option>`).join('')}</select></div><div id="admin-gift-level-row" hidden><label>Уровень пушки / питомца</label><input id="admin-gift-level" type="number" min="0" max="10" value="0"></div><label>Причина выдачи (от 5 символов)</label><textarea id="admin-gift-reason" rows="3" maxlength="300" placeholder="Приз, компенсация, тест ..."></textarea>`,'admin-grant-confirm','ВЫДАТЬ');
   modal.payload={request_id:crypto.randomUUID(),pid:adminDetail.id};
   fillAdminGrantItems('item');return;
  }
  if(action==='admin-grant-confirm'){
    const payload=modal?.payload;if(!payload||!adminDetail)return;
    const kind=document.getElementById('admin-gift-kind')?.value;
    const key=document.getElementById('admin-gift-key')?.value;
    const amount=Number(document.getElementById('admin-gift-amount')?.value||1);
    const level=Number(document.getElementById('admin-gift-level')?.value||0);
    const rarity=document.getElementById('admin-gift-rarity')?.value||'common';
    const reason=document.getElementById('admin-gift-reason')?.value?.trim()||'';
    if(!key){notice('Выбери награду из каталога',true);return}
    if(reason.length<5){notice('Укажи причину длиной от 5 символов',true);return}
    if(!Number.isInteger(amount)||amount<1||!Number.isInteger(level)||level<0||level>10){
      notice('Проверь количество и уровень',true);return;
    }
    loading=true;
    try{
      const result=await api('admin/players/'+payload.pid+'/grant','POST',{
        request_id:payload.request_id,kind,key,amount:kind==='pet'||kind==='premium'?1:amount,
        rarity,level,reason
      });
      notice(result.message);
      modal=null;await sync();
    }catch(e){notice(e.message,true)}finally{loading=false}
    return;
  }
  if(action==='admin-resource'){if(!adminDetail)return;showModal('ИЗМЕНИТЬ РЕСУРСЫ?',`<p>${esc(adminDetail.name)} · #${adminDetail.id}. Для выдачи 💎 Zombo, VIP, питомцев и любой экипировки используй кнопку «ВЫДАТЬ ЛЮБОЙ ПРЕДМЕТ».</p><label>Ресурс</label><select id="admin-field"><option value="caps">Крышки</option><option value="xp">XP (только выдача)</option><option value="material">Материал</option></select><label>Ключ материала (для материалов)</label><select id="admin-item">${Object.entries(cfg.items).filter(([,x])=>x.type==='material').map(([k,x])=>`<option value="${k}">${esc(x.name)}</option>`).join('')}</select><label>Количество (минус для списания)</label><input id="admin-amount" type="number" min="-100000" max="100000" step="1"><label>Причина</label><textarea id="admin-reason" maxlength="300" rows="3"></textarea>`,'admin-resource-confirm','ПРИМЕНИТЬ');modal.payload={request_id:crypto.randomUUID()};return}
  if(action==='admin-status-confirm'||action==='admin-resource-confirm'){
    const reason=document.getElementById('admin-reason')?.value?.trim()||'';if(reason.length<5){notice('Укажи причину не короче 5 символов',true);return}
    const body={...modal.payload,reason};let route='status';if(action==='admin-resource-confirm'){route='resources';body.field=document.getElementById('admin-field').value;body.item_key=body.field==='material'?document.getElementById('admin-item').value:null;body.amount=Number(document.getElementById('admin-amount').value);if(!Number.isInteger(body.amount)||body.amount===0){notice('Укажи ненулевое целое количество',true);return}}
    loading=true;try{let result=await api('admin/players/'+adminDetail.id+'/'+route,'POST',body);notice(result.message);modal=null;await sync()}catch(e){notice(e.message,true)}finally{loading=false}return
  }
  if(action==='war-bid'){
    const t=(territories||[]).find(x=>x.id===value);
    const w=(warsData?.wars||[]).find(x=>x.territory_id===value&&x.status==='bidding');
    showModal('СТАВКА ЗА '+(t?.name||'ТЕРРИТОРИЮ'),`<p>Текущая ставка: <b>${money(w?.bid||0)}</b> крышек. Минимум: ${money(warsData?.min_bid||100)}.</p><p class="smallnote">Ставка снимается из казны клана. Перебитая ставка возвращается. При победе в торгах крышки списываются окончательно.</p><label>Твоя ставка</label><input id="input-war-bid" type="number" min="${Math.max(w?.bid+1||0,warsData?.min_bid||100)}" value="${Math.max(w?.bid+100||0,warsData?.min_bid||100)}">`,'war-submit-bid','ОТПРАВИТЬ СТАВКУ');modal.warId=value;return;
  }
  if(action==='war-submit-bid') {let key=modal?.warId,amount=Number(document.getElementById('input-war-bid')?.value);modal=null;await act('territories/bid',{key,amount});return}
  if(action==='war-appoint') {const m=clans?.members?.find(x=>String(x.id)===value);showModal('НАЗНАЧИТЬ ВОЕВОДУ?',`<p>${esc(m?.name||'Боец')} получит доступ к ставкам и расстановке войск. Предыдущий воевода потеряет полномочия.</p>`,'war-confirm-appoint','НАЗНАЧИТЬ');modal.targetId=Number(value);return}
  if(action==='war-confirm-appoint'){let player_id=modal?.targetId;modal=null;await act('clans/warlord',{player_id});return}
  if(action==='war-add'){let player_id=Number(document.getElementById('roster-'+value)?.value);if(!player_id){notice('Нет свободных бойцов',true);return}await act('territories/roster',{war_id:Number(value),player_id,include:true});return}
  if(action==='war-remove'){let [war_id,player_id]=value.split(':').map(Number);await act('territories/roster',{war_id,player_id,include:false});return}
  if(action==='war-act'){let [id,cmd]=value.split(':');await act('territories/act',{war_id:Number(id),action:cmd});return}

  if(action==='gm-tab'){gearMarketTab=value==='mine'?'mine':'browse';render();return}
  if(action==='gm-page'){gearMarketPage=Math.max(1,Math.min(40,Number(value)||1));await fetchScreen();render();return}
  if(action==='gm-create'){const available=(me.gear||[]).filter(x=>!x.equipped);if(!available.length){notice('Сначала сними экипировку или добудь предмет.',true);return}
    showModal('ПРОДАТЬ СНАРЯЖЕНИЕ',`<p>Снаряжение будет временно перемещено на торговый склад до продажи или возврата.</p><label>Выбери предмет</label><select id="gm-gear-id">${available.map(g=>`<option value="${g.id}">${esc(g.rarity_name)} ${esc(g.name)} +${g.level}</option>`).join('')}</select><label>Цена в крышках</label><input id="gm-price" type="number" min="50" max="250000" step="1" value="300"><p class="smallnote">Комиссия биржи 5% после продажи. Срок 7 дней. Не больше 5 лотов одновременно.</p>`,'gm-sell-confirm','ВЫСТАВИТЬ');return}
  if(action==='gm-sell-confirm'){const gear_id=Number(document.getElementById('gm-gear-id')?.value),price=Number(document.getElementById('gm-price')?.value);modal=null;await act('gear-market/list',{gear_id,price});return}
  if(action==='gm-buy'){const item=(gearMarket?.items||[]).find(s=>String(s.id)===String(value));if(!item)return;showModal('КУПИТЬ ПРЕДМЕТ?',`<p>Приобрести <b>${esc(item.gear.rarity_name)} ${esc(item.gear.name)} +${item.gear.level}</b> за <b>🪙 ${money(item.price)}</b> крышек?</p><p class="smallnote">Сумма будет переведена продавцу за вычетом комиссии. Отменить покупку после подтверждения нельзя.</p>`,'gm-buy-confirm','КУПИТЬ');modal.saleId=item.id;return}
  if(action==='gm-buy-confirm'){const id=modal?.saleId;modal=null;await act('gear-market/buy',{id});return}
  if(action==='gm-cancel'){const item=(gearMarket?.my_sales||gearMarket?.items||[]).find(s=>String(s.id)===String(value));showModal('СНЯТЬ ЛОТ?',`<p>Снять лот #${Number(value)}? Снаряжение вернётся в твой арсенал без дополнительных затрат.</p>`,'gm-cancel-confirm','ЗАБРАТЬ');modal.saleId=Number(value);return}
  if(action==='gm-cancel-confirm'){const id=modal?.saleId;modal=null;await act('gear-market/cancel',{id});return}
  if(action==='chest-open'){
    const item=(me.inventory||[]).find(i=>i.key===value&&i.qty>0);if(!item)return;
    const c=(cfg.chests||[]).find(o=>o.key===value);if(!c)return;
    showModal('ОТКРЫТЬ ПРЕМИУМ-СУНДУК?',`<p>${esc(c.name)}: получить ${c.drops} награды, включая одну коллекционную пушку? Сундук будет списан только после успешной выдачи.</p>`,'chest-open-confirm','ОТКРЫТЬ');
    modal.chestKey=value;return;
  }
  if(action==='chest-open-confirm'){
    const key=modal?.chestKey;modal=null;
    if(key){
      const out=await act('chests/open',{key});
      if(out?.rewards){
        const details=out.rewards.map(x=>x.kind==='gear'?(`⚔ ${esc(x.gear.rarity_name)} ${esc(x.name)}`):(`${esc(cfg.items[x.key]?.icon||'▣')} ${esc(cfg.items[x.key]?.name||x.key)} ×${x.qty}`));
        showModal('🎉 НАГРАДЫ СОХРАНЕНЫ',`<p class="smallnote">Все предметы — в рюкзаке. Уникальное оружие теперь тоже видно там и в Арсенале.</p><div class="case-prizes">${details.map(v=>`<div class="case-prize">${v}</div>`).join('')}</div>`,'loot-to-inventory','В ИНВЕНТАРЬ');
      }
    }
    return;
  }
  if(action==='case-open'){
    const item=(me.inventory||[]).find(i=>i.key===value&&i.qty>0);if(!item)return;
    showModal('ВСКРЫТЬ КЕЙС?',`<p>Потратить <b>${esc(item.name)}</b> и получить одну случайную эксклюзивную пушку? Её нельзя скрафтить.</p>`,'case-open-confirm','ОТКРЫТЬ');
    modal.caseKey=value;return;
  }
  if(action==='case-open-confirm'){
    const key=modal?.caseKey;modal=null;
    if(key){
      const result=await act('cases/open',{key});
      if(result?.gear){
        const g=result.gear;
        showModal('🎉 ТВОЯ НОВАЯ ПУШКА',`<div class="case-prizes"><div class="case-prize"><strong>${esc(g.icon)} ${esc(g.rarity_name)} ${esc(g.name)}</strong><p>⚔ Урон: ${Number(g.power)||0} · Прочность: ${Number(g.durability)||100}/100</p><p>Коллекционная серия · Усиление до +10</p></div></div>`,'loot-to-inventory','В ИНВЕНТАРЬ');
      }
    }
    return;
  }
  if(action==='gear-repair'){
    const g=(me.gear||[]).find(x=>String(x.id)===String(value));if(!g||!g.repair_cost)return;
    const c=g.repair_cost;
    showModal('ПОЧИНИТЬ СНАРЯЖЕНИЕ?',`<p>${esc(g.name)}: ${g.durability}/100. Полный ремонт стоит ${money(c.caps)} крышек, ${c.qty} ${esc(cfg.items[c.material]?.name||c.material)}${c.rare?' и '+c.rare+' жетонов':''}.</p>`,'gear-repair-confirm','ПОЧИНИТЬ');
    modal.gearId=g.id;return;
  }
  if(action==='gear-repair-confirm'){const id=modal?.gearId;modal=null;if(id)await act('gear/repair',{id});return}
  if(action==='gear-dismantle'){const g=(me.gear||[]).find(x=>String(x.id)===String(value));if(!g)return;showModal('Разобрать снаряжение?',`<p>Удалить предмет <b>${esc(g.rarity_name)} ${esc(g.name)} +${g.level}</b> и получить материалы? Это действие нельзя отменить.</p>`,'gear-dismantle-confirm','ПОДТВЕРДИТЬ');modal.gearId=g.id;return}
  if(action==='gear-dismantle-confirm'){const id=modal?.gearId;modal=null;await act('gear/dismantle',{id});return}
  if(action==='fight-skill'){let res=await act('combat/turn',{action:'skill',zone:value});if(res?.finished)actionScreen('map',true);if(res){await fetchScreen();render()}return}
  if(action==='fight-tap'){
    if(!me?.battle||me.stamina<2)return;
    const target=document.querySelector('.mob-tap');
    target?.classList.add('is-striking');
    try{tg?.HapticFeedback?.impactOccurred('light')}catch(e){}
    const res=await act('combat/turn',{action:'attack',zone:'body'});
    if(res?.finished){actionScreen('map',true);await fetchScreen();render()}
    else if(res)showTapResult(res.message);
    else target?.classList.remove('is-striking');
    return;
  }
  if(action==='class-confirm'){if(!choice)return;await act('class',{key:choice});return}
  if(action==='market-create'){
   const allowed=(key,meta)=>meta&&meta.type!=='case'&&meta.type!=='chest'&&
     (!['weapon','armor'].includes(meta.type)||['knife','vest','pistol','rifle'].includes(key));
   const owned=(me.inventory||[]).filter(item=>!item.equipped&&item.qty>0&&
     allowed(item.key,cfg.items[item.key]));
   if(!owned.length){notice('Нет обычных предметов для обмена. Кейсы и уникальные пушки не торгуются здесь.',true);return}
   const ownOptions=owned.map(item=>`<option value="${esc(item.key)}">${esc(item.icon)} ${esc(item.name)} ×${item.qty}</option>`).join('');
   const wantOptions=Object.entries(cfg.items).filter(([key,item])=>allowed(key,item))
     .map(([key,item])=>`<option value="${esc(key)}">${esc(item.icon||'▣')} ${esc(item.name)}</option>`).join('');
   showModal('СОЗДАТЬ ЛОТ',`<p class="smallnote">Здесь обмениваются обычными припасами. Уникальные пушки продаются на отдельном рынке снаряжения. Платные кейсы и сундуки нельзя обменять.</p><label>Что отдаёшь (из рюкзака)</label><select id="input-offer">${ownOptions}</select><label>Количество</label><input id="input-qty" type="number" min="1" max="100" value="1"><label>Что хочешь получить</label><select id="input-want">${wantOptions}</select><label>Сколько хочешь</label><input id="input-wqty" type="number" min="1" max="100" value="1"><p class="smallnote">Предметы резервируются после подтверждения сделки.</p>`,'submit-lot','ВЫСТАВИТЬ');
   return;
 }
 if(forms[action]){const [title,body,submit,label]=forms[action];showModal(title,body,submit,label);return}
  if(action==='submit-clan'){
    const field=document.getElementById('input-name');
    const name=(field?.value||'').trim();
    if(name.length<3||name.length>30){notice('Название клана должно содержать от 3 до 30 символов',true);field?.focus();return}
    if((me?.caps||0)<250){notice('Для создания клана нужно 250 крышек',true);return}
    const result=await act('clans/create',{name});
    if(result){modal=null;await nav('clan')}
    return
  }
  if(action==='submit-donate'){
    const amount=Number(document.getElementById('input-qty')?.value);
    if(!Number.isSafeInteger(amount)||amount<=0){notice('Введи положительное целое количество крышек',true);return}
    const result=await act('clans/donate',{amount});
    if(result){modal=null;await nav('clan')}
    return
  }
  if(action==='submit-lot'){
    const offer=document.getElementById('input-offer')?.value,qty=Number(document.getElementById('input-qty')?.value);
    const want=document.getElementById('input-want')?.value,want_qty=Number(document.getElementById('input-wqty')?.value);
    if(!Number.isSafeInteger(qty)||qty<1||qty>100||!Number.isSafeInteger(want_qty)||want_qty<1||want_qty>100||offer===want){notice('Проверь предметы и количество: обменивай разные вещи',true);return}
    const result=await act('market/create',{offer,qty,want,want_qty});
    if(result){modal=null;await nav('market')}
    return
  }
  if(action==='raid-act'){await act('raids/act',{id:raids?.my_raid?.id,action:value});return}
  if(action==='raid-rescue'){await act('raids/act',{id:raids?.my_raid?.id,action:'rescue',target_id:Number(value)});return}
  let route={'story-act':['story/act',{action:value}],'gear-equip':['gear/equip',{id:Number(value)}],'gear-unequip':['gear/unequip',{id:Number(value)}],'gear-upgrade':['gear/upgrade',{id:Number(value)}],'raid-create':['raids/create',{key:value}],'raid-join':['raids/join',{id:Number(value)}],'raid-leave':['raids/leave',{id:Number(value)}],'raid-launch':['raids/launch',{id:Number(value)}],'raid-claim':['raids/claim',{id:Number(value)}],'exp-create':['expeditions/create',{key:value}],'exp-join':['expeditions/join',{id:Number(value)}],'exp-leave':['expeditions/leave',{id:Number(value)}],'exp-prepare':['expeditions/prepare',{id:expeditions?.my_run?.id,role:value}],'exp-launch':['expeditions/launch',{id:Number(value)}],'exp-claim':['expeditions/claim',{id:Number(value)}],'exp-event':['expeditions/event',{id:expeditions?.my_run?.id,choice:value}],stat:['stat',{key:value}],skill:['skill',{key:value}],travel:['travel',{key:value}],scavenge:['scavenge',null],'combat-start':['combat/start',null],
      daily:['daily',null],use:['item/use',{key:value}],equip:['item/equip',{key:value}],craft:['craft',{key:value}],quest:['quest/claim',{key:value}],
      'boss-hit':['boss/hit',null],'clan-mission-claim':['clan-missions/claim',{code:value}],'clan-season-claim':['clan-missions/season-claim',null],'clan-join':['clans/join',{id:Number(value)}],'clan-leave':['clans/leave',null],
'market-buy':['market/buy',{id:Number(value)}], 'market-cancel':['market/cancel',{id:Number(value)}],
      'pvp-challenge':['pvp/challenge',{player_id:Number(value)}], 'pvp-act':['pvp/act',{id:pvp?.match?.id,action:value}],
      'shop-buy':['shop/buy',{key:value}], 'premium-buy':['premium/buy',{key:value}]};
  if(action==='fight-act')route[action]=['combat/turn',{action:value,zone}];
  if(action==='stars-buy'){
    loading=true;try{let out=await api('stars/invoice','POST',{key:value});if(tg?.openInvoice)tg.openInvoice(out.url,status=>{if(status==='paid'){notice('Спасибо! Перезагрузи баланс.');sync()}});else window.open(out.url,'_blank')}catch(e){notice(e.message,true)}finally{loading=false}return;
  }
  if(route[action]){let [url,body]=route[action];let res=await act(url,body);if(res?.battle&&action==='combat-start')actionScreen('fight');if(res?.battle===true&&action==='scavenge')actionScreen('fight');if(res?.finished)actionScreen('map',true);if(res&&action==='travel')actionScreen('map');if(res&&action==='class-confirm'){screen='home';navTrail=[]}if(res){await fetchScreen();render()}return}
}
function applySearch(group){
 const q=(group==='inventory'?inventoryQuery:group==='craft'?craftQuery:gearQuery).trim().toLowerCase();
 const rows=app.querySelectorAll(`[data-search-group="${group}"]`);
 let count=0;rows.forEach(row=>{const found=!q||(row.dataset.search||'').includes(q);row.hidden=!found;if(found)count++});
 const empty=app.querySelector(`[data-filter-empty="${group}"]`);if(empty)empty.hidden=count!==0;
}
app.addEventListener('input',event=>{
 if(event.target?.id==='admin-gift-search'){
   fillAdminGrantItems(document.getElementById('admin-gift-kind')?.value||'item',event.target.value);
   return;
 }

 const group=event.target?.dataset?.listSearch;
 if(!['inventory','craft','gear'].includes(group))return;
 const query=String(event.target.value||'').slice(0,64);
 if(group==='inventory')inventoryQuery=query;else if(group==='craft')craftQuery=query;else gearQuery=query;
 applySearch(group);
});
app.addEventListener('change',e=>{
 if(e.target?.id==='admin-gift-kind'){
   const input=document.getElementById('admin-gift-search');if(input)input.value='';
   fillAdminGrantItems(e.target.value);return;
 }

  if(e.target?.id!=='gear-sort')return;
  gearSort=['equipped','rarity','power','worn'].includes(e.target.value)?e.target.value:'equipped';
  render();
});
app.addEventListener('click',e=>{let b=e.target.closest('[data-action]');if(!b||b.disabled)return;if(b.classList.contains('modal-bg')&&e.target!==b)return;e.preventDefault();handle(b.dataset.action,b.dataset.value||'').catch(err=>notice(err.message,true))});
try{tg?.BackButton?.onClick(()=>goBack())}catch(e){}
setInterval(()=>{if((screen==='clan'||screen==='pvp'||screen==='expeditions') && !loading && !modal){fetchScreen().then(render).catch(()=>{})}},30000);
(async function start(){try{if(!auth){app.innerHTML=`<div class="app-shell"><header class="top"><div class="brand">ZOMBO<span>AFTER THE FALL</span></div></header><div class="hero"><div class="hero-text" style="max-width:100%"><div class="eyebrow">// СИГНАЛ ОТКЛОНЁН</div><h1>ОТКРОЙ ИГРУ<br>В TELEGRAM</h1><p>Для сохранения персонажа и защиты экономики открой приложение через кнопку в Telegram-боте.</p></div></div><div class="panel"><h3>Разработчик / локальная проверка</h3><p class="smallnote">Демо доступно только при включённом DEMO_MODE на сервере. Добавь ?demo=1 к адресу локального стенда.</p></div></div>`;return}cfg=await api('config');me=await api('me');if(me.class&&me.battle)screen='fight';else if(me.class&&me.encounter_pending){screen='encounters';await fetchScreen()}render()}catch(e){app.innerHTML=`<div class="app-shell"><div class="hero"><div class="hero-text" style="max-width:100%"><span class="eyebrow">// СВЯЗЬ ПОТЕРЯНА</span><h1>ОШИБКА ПОДКЛЮЧЕНИЯ</h1><p>${esc(e.message)}</p><button class="btn gold" onclick="location.reload()">ПОВТОРИТЬ</button></div></div></div>`}})();
})();
