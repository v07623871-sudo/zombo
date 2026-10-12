"""Territorial clan war engine. All public mutations take place in caller DB transactions."""
from __future__ import annotations
import os, random
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, func
from models import Clan, ClanOfficer, Player, Territory, TerritoryTax, TerritoryWar, WarFighter, now
from game import LOCATIONS, TERRITORIES, attack_power, max_hp, talent_bonus, aware
from notifications import queue_notification

WAR_TIMEZONE = os.getenv('WAR_TIMEZONE', 'Europe/Moscow')
try:
    ZONE = ZoneInfo(WAR_TIMEZONE)
except ZoneInfoNotFoundError:
    ZONE = ZoneInfo('UTC')
    WAR_TIMEZONE = 'UTC'
WAR_DAYS = {1, 3, 5}   # Tuesday / Thursday / Saturday (Python Monday=0)
BID_DAYS = {0, 2, 4}   # Monday / Wednesday / Friday
MIN_BID = 100
MAX_FIGHTERS = 25
TAX_INTERVAL = timedelta(hours=5)
LOCATION_TERRITORY = {'forest': 'bridge', 'city': 'tower', 'factory': 'depot',
                      'hospital': 'clinic', 'wasteland': 'depot'}


def local(at=None):
    return (at or now()).astimezone(ZONE)


def phase(at=None):
    current = local(at)
    weekday, minute = current.weekday(), current.hour * 60 + current.minute
    if weekday in BID_DAYS:
        return 'bidding'
    if weekday in WAR_DAYS:
        if 600 <= minute < 900:
            return 'formation'
        if 960 <= minute < 990:
            return 'battle'
        if minute < 960:
            return 'waiting'
        return 'finished'
    return 'rest'


def war_date_for_bid(at=None):
    d = local(at)
    return (d + timedelta(days=1)).date().isoformat() if d.weekday() in BID_DAYS else None


def next_war_date(at=None):
    d = local(at).date()
    for i in range(8):
        next_date = d + timedelta(days=i)
        if next_date.weekday() in WAR_DAYS:
            return next_date.isoformat()
    raise RuntimeError('No war day found')


def war_clock(at, war):
    d = local(at)
    return d.date().isoformat() == war.war_date, d.hour * 60 + d.minute


def _war_start(war):
    return datetime.combine(datetime.fromisoformat(war.war_date).date(), time(16, 0), tzinfo=ZONE)


def _fighters(db, war):
    return db.scalars(select(WarFighter).where(WarFighter.war_id == war.id)
                      .order_by(WarFighter.player_id)).all()


def _history(war, line):
    war.log = [*(war.log or [])[-69:], line]


def _finish(db, war, winning_id, text):
    if war.status == 'resolved':
        return
    t = db.get(Territory, war.territory_id)
    if winning_id and t and t.clan_id != winning_id:
        collect_tax(db, t.id, force=True)
        t.clan_id = winning_id
        tax = db.get(TerritoryTax, t.id)
        if tax: tax.remainder = 0
    war.winner_clan_id = winning_id
    war.status = 'resolved'
    _history(war, text)
    territory_name = TERRITORIES.get(war.territory_id, war.territory_id)
    for fighter in _fighters(db, war):
        clan_id = war.attacker_clan_id if fighter.side == 'attacker' else war.defender_clan_id
        outcome = 'Победа' if clan_id == winning_id else 'Поражение'
        queue_notification(db, fighter.player_id,
                           f'war:{war.id}:result:{fighter.player_id}', 'clans', 'war_result',
                           f'КВ за {territory_name} завершена. {outcome} твоего клана.')


def _round(db, war, number):
    fighters = _fighters(db, war)
    players = {p.id: p for p in db.scalars(select(Player).where(Player.id.in_([f.player_id for f in fighters])))}
    # Members who left the clan lose their deployment slot.
    for f in fighters:
        expected = war.attacker_clan_id if f.side == 'attacker' else war.defender_clan_id
        if not players.get(f.player_id) or players[f.player_id].clan_id != expected:
            f.hp = 0
    seed = (war.id * 10007 + number * 73471)
    rng = random.Random(seed)
    order = sorted(fighters, key=lambda f: (f.side, f.player_id))
    rng.shuffle(order)
    for f in order:
        if f.hp <= 0: continue
        victims = [x for x in fighters if x.side != f.side and x.hp > 0]
        if not victims: break
        target = rng.choice(victims)
        p = players[f.player_id]
        power = attack_power(db, p)
        damage = max(2, int((6 + power * .44) * rng.uniform(.78, 1.18)))
        if target.guarding_round >= number:
            damage = max(1, damage // 2)
        target.hp = max(0, target.hp - damage)
        f.damage += damage
    alive_a = sum(f.hp > 0 for f in fighters if f.side == 'attacker')
    alive_d = sum(f.hp > 0 for f in fighters if f.side == 'defender')
    war.round = number
    if number == 1 or number % 5 == 0 or alive_a == 0 or alive_d == 0:
        _history(war, f'Раунд {number}: атакующие {alive_a}, защитники {alive_d}')
    return alive_a, alive_d


def settle_war(db, war, at=None):
    at = at or now()
    at_local = local(at)
    today = at_local.date().isoformat()
    if war.status == 'resolved' or today < war.war_date:
        return
    if war.status == 'bidding':
        territory = db.get(Territory, war.territory_id)
        if not territory:
            return
        # No bid is finalized before 00:00 local time on war day.
        war.defender_clan_id = territory.clan_id
        if not war.attacker_clan_id:
            war.status = 'resolved'
            return
        if not territory.clan_id:
            _finish(db, war, war.attacker_clan_id, 'Территория была свободна и перешла победителю торгов.')
            return
        war.status = 'formation'
        _history(war, 'Ставки закрыты. Началась подготовка к клановой войне.')
    if today == war.war_date and war.status == 'formation' and at_local.hour * 60 + at_local.minute < 960:
        return
    start = _war_start(war)
    elapsed = int((at.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds())
    if elapsed < 0: return
    target_round = min(30, elapsed // 60 + 1)
    war.status = 'battle'
    for n in range(war.round + 1, target_round + 1):
        a, d = _round(db, war, n)
        if a == 0 or d == 0:
            winner = war.attacker_clan_id if a > 0 else war.defender_clan_id
            _finish(db, war, winner, 'КВ завершилось досрочно: одна из армий уничтожена.')
            break
    if war.status != 'resolved' and elapsed >= 1800:
        fighters = _fighters(db, war)
        ahp = sum(f.hp for f in fighters if f.side == 'attacker')
        dhp = sum(f.hp for f in fighters if f.side == 'defender')
        # Defender wins when both sides finish at the same HP, including an empty roster.
        winner = war.attacker_clan_id if ahp > dhp else war.defender_clan_id
        _finish(db, war, winner, f'В 16:30 бой завершён. Остаток HP: атака {ahp}, защита {dhp}.')


def collect_tax(db, territory_id, *, at=None, force=False):
    at = at or now()
    tax = db.scalar(select(TerritoryTax).where(TerritoryTax.territory_id == territory_id).with_for_update())
    if not tax:
        tax = TerritoryTax(territory_id=territory_id, last_collection=at)
        db.add(tax)
        db.flush()
    elapsed = at - aware(tax.last_collection)
    if not force and elapsed < TAX_INTERVAL:
        return 0
    amount = tax.pending
    t = db.get(Territory, territory_id)
    if amount and t and t.clan_id:
        c = db.scalar(select(Clan).where(Clan.id == t.clan_id).with_for_update())
        if c: c.treasury += amount
    tax.pending = 0
    tax.collected += amount
    if force:
        tax.last_collection = at
    else:
        # Keep the 5-hour cadence stable, even after process downtime.
        jumps = max(1, int(elapsed.total_seconds() // TAX_INTERVAL.total_seconds()))
        tax.last_collection = aware(tax.last_collection) + TAX_INTERVAL * jumps
    return amount


def zombie_tax(db, player, gross_caps):
    """Deduct 1% of the actual zombie reward (integer carry prevents rounding loss)."""
    tid = LOCATION_TERRITORY.get(player.location)
    if not tid: return 0
    territory = db.get(Territory, tid)
    if not territory or not territory.clan_id: return 0
    tax = db.scalar(select(TerritoryTax).where(TerritoryTax.territory_id == tid).with_for_update())
    if not tax:
        tax = TerritoryTax(territory_id=tid, last_collection=now())
        db.add(tax)
        db.flush()
    total = tax.remainder + gross_caps
    paid, tax.remainder = divmod(total, 100)
    tax.pending += paid
    return paid


def refresh_world(db, at=None):
    at = at or now()
    for tid in TERRITORIES:
        collect_tax(db, tid, at=at)
    wars = db.scalars(select(TerritoryWar).where(TerritoryWar.status != 'resolved',
                        TerritoryWar.war_date <= local(at).date().isoformat())
                      .order_by(TerritoryWar.id).with_for_update()).all()
    for war in wars:
        settle_war(db, war, at)


def bid(db, player, tid, amount, at=None):
    at = at or now()
    date = war_date_for_bid(at)
    if not date: raise ValueError('Ставки принимаются только в понедельник, среду и пятницу.')
    if tid not in TERRITORIES: raise ValueError('Нет такой территории')
    if amount < MIN_BID or amount > 1_000_000: raise ValueError(f'Ставка от {MIN_BID} до 1 000 000 крышек')
    if not player.clan_id: raise ValueError('Сначала вступи в клан')
    # Territory/war first, then all clan treasuries in a stable ID order.
    # Opposing bids on the same lot cannot each hold the other's clan row.
    t = db.scalar(select(Territory).where(Territory.id == tid).with_for_update())
    if t.clan_id == player.clan_id: raise ValueError('Нельзя делать ставку на собственную территорию')
    war = db.scalar(select(TerritoryWar).where(TerritoryWar.territory_id == tid, TerritoryWar.war_date == date).with_for_update())
    if not war:
        war = TerritoryWar(territory_id=tid, war_date=date, status='bidding', bid=0)
        db.add(war)
        db.flush()
    if war.status != 'bidding': raise ValueError('Торги закончены')
    if amount <= war.bid: raise ValueError(f'Новая ставка должна быть выше {war.bid} крышек')
    clan_ids={player.clan_id}
    if war.attacker_clan_id:clan_ids.add(war.attacker_clan_id)
    clans={clan.id:clan for clan in db.scalars(select(Clan).where(Clan.id.in_(clan_ids))
                                           .order_by(Clan.id).with_for_update())}
    c=clans.get(player.clan_id)
    if not can_command(db, player, c): raise ValueError('Ставку делает только лидер или воевода')
    if war.attacker_clan_id == c.id:
        extra = amount - war.bid
        if c.treasury < extra: raise ValueError(f'В казне не хватает {extra} крышек')
        c.treasury -= extra
    else:
        if c.treasury < amount: raise ValueError('В казне недостаточно крышек')
        # Return reserved funds to the outbid clan immediately.
        if war.attacker_clan_id:
            prev=clans.get(war.attacker_clan_id)
            if not prev: raise ValueError('Предыдущий клан не найден; торги остановлены')
            prev.treasury += war.bid
        c.treasury -= amount
        war.attacker_clan_id = c.id
    war.bid = amount
    _history(war, f'Новая ставка: {amount} крышек от клана {c.name}.')
    return war


def can_command(db, player, clan=None):
    if not player.clan_id: return False
    clan = clan or db.get(Clan, player.clan_id)
    if not clan or clan.id != player.clan_id: return False
    if clan.leader_id == player.id: return True
    return db.scalar(select(ClanOfficer).where(ClanOfficer.clan_id == clan.id,
                                             ClanOfficer.player_id == player.id,
                                             ClanOfficer.role == 'warlord')) is not None


def appoint(db, leader, target_id):
    clan = db.scalar(select(Clan).where(Clan.id == leader.clan_id).with_for_update()) if leader.clan_id else None
    if not clan or clan.leader_id != leader.id: raise ValueError('Назначать воеводу может только лидер')
    if target_id == leader.id: raise ValueError('Лидер уже управляет войнами')
    target = db.get(Player, target_id)
    if not target or target.clan_id != clan.id: raise ValueError('Выбери участника своего клана')
    for officer in db.scalars(select(ClanOfficer).where(ClanOfficer.clan_id == clan.id)):
        db.delete(officer)
    db.flush()
    db.add(ClanOfficer(clan_id=clan.id,player_id=target.id,role='warlord'))
    return target


def roster(db, officer, war_id, target_id, include=True, at=None):
    at = at or now()
    current = local(at)
    if current.weekday() not in WAR_DAYS or not (600 <= current.hour*60+current.minute < 900):
        raise ValueError('Расстановка доступна только в дни КВ с 10:00 до 15:00')
    war = db.scalar(select(TerritoryWar).where(TerritoryWar.id == war_id).with_for_update())
    if not war: raise ValueError('Клановая война не найдена')
    if war.war_date != current.date().isoformat(): raise ValueError('Это КВ другого дня')
    settle_war(db, war, at)
    if war.status != 'formation': raise ValueError('Нельзя менять состав в этом КВ')
    if not can_command(db, officer): raise ValueError('Расстановкой управляет лидер или воевода')
    if officer.clan_id == war.attacker_clan_id: side = 'attacker'
    elif officer.clan_id == war.defender_clan_id: side = 'defender'
    else: raise ValueError('Ваш клан не участвует в этом КВ')
    member = db.get(Player, target_id)
    if not member or member.clan_id != officer.clan_id or not member.hero_class: raise ValueError('Игрок не состоит в вашем клане')
    current_slot = db.scalar(select(WarFighter).where(WarFighter.war_id == war_id, WarFighter.player_id == target_id))
    if not include:
        if not current_slot or current_slot.side != side: raise ValueError('Игрок не назначен в этот отряд')
        db.delete(current_slot)
        return
    if current_slot: raise ValueError('Игрок уже записан в этот КВ')
    count = db.scalar(select(func.count()).select_from(WarFighter).where(WarFighter.war_id == war_id, WarFighter.side == side))
    if count >= MAX_FIGHTERS: raise ValueError('В отряде максимум 25 игроков')
    other = db.scalar(select(WarFighter).join(TerritoryWar, TerritoryWar.id == WarFighter.war_id)
                      .where(WarFighter.player_id == target_id, TerritoryWar.war_date == war.war_date,
                             TerritoryWar.status != 'resolved'))
    if other: raise ValueError('Нельзя участвовать сразу в двух КВ в один день')
    hp = min(700, 85 + member.level * 9 + member.stats.get('endurance',0)*4)
    db.add(WarFighter(war_id=war_id,player_id=target_id,side=side,hp=hp,max_hp=hp))
    queue_notification(db,target_id,f'war:{war.id}:start:{target_id}',
                       'clans','war_start',f'Ты назначен в отряд КВ. Бой начнётся в 16:00 ({WAR_TIMEZONE}).',
                       _war_start(war).astimezone(timezone.utc))


def war_action(db, player, war_id, action, at=None):
    at = at or now()
    current = local(at)
    if current.weekday() not in WAR_DAYS or not (960 <= current.hour*60 + current.minute < 990):
        raise ValueError('Бои КВ идут с 16:00 до 16:30')
    war = db.scalar(select(TerritoryWar).where(TerritoryWar.id == war_id).with_for_update())
    if not war or war.war_date != current.date().isoformat(): raise ValueError('КВ не найдено')
    settle_war(db, war, at)
    if war.status != 'battle': raise ValueError('Бой завершён или ещё не начался')
    fighters = _fighters(db, war)
    own = next((f for f in fighters if f.player_id == player.id),None)
    if not own or own.hp <= 0: raise ValueError('Ты не участвуешь или выбыла из боя')
    if player.clan_id != (war.attacker_clan_id if own.side == 'attacker' else war.defender_clan_id):
        raise ValueError('Ты уже не состоишь в участвующем клане')
    if own.last_action_round == war.round: raise ValueError('Ты уже действовала в этом раунде')
    if action not in ('attack','guard','heal'): raise ValueError('Неизвестное действие')
    if action == 'heal':
        if player.hero_class != 'medic': raise ValueError('Лечить в КВ может только врач')
        heal = 24 + player.level * 2 + int(talent_bonus(player,'healing') * 30)
        own.hp = min(own.max_hp,own.hp + heal)
        message = f'Полевое лечение: +{heal} HP'
    elif action == 'guard':
        own.guarding_round = war.round + 1
        message = 'Защитная позиция: следующая атака будет ослаблена'
    else:
        opponents = [f for f in fighters if f.side != own.side and f.hp > 0]
        if not opponents: raise ValueError('Противники уже разгромлены')
        victim = min(opponents,key=lambda f:(f.hp,f.player_id))
        dmg = max(4,int(attack_power(db,player)*.7))
        if victim.guarding_round >= war.round: dmg = max(1,dmg // 2)
        victim.hp=max(0,victim.hp-dmg)
        own.damage+=dmg
        message=f'Удар по противнику: {dmg} урона'
    own.last_action_round=war.round
    _history(war, f'{player.name}: {message}')
    remaining_a = sum(f.hp > 0 for f in fighters if f.side == 'attacker')
    remaining_d = sum(f.hp > 0 for f in fighters if f.side == 'defender')
    if not remaining_a or not remaining_d:
        _finish(db,war,war.attacker_clan_id if remaining_a else war.defender_clan_id,'Один из отрядов уничтожен.')
    return message


def war_view(db, war, user_id=None):
    fighters = _fighters(db,war)
    ids = {x.player_id for x in fighters}
    names = {p.id:p.name for p in db.scalars(select(Player).where(Player.id.in_(ids)))} if ids else {}
    return {'id':war.id,'territory_id':war.territory_id,'war_date':war.war_date,
            'status':war.status,'bid':war.bid,'attacker_clan_id':war.attacker_clan_id,
            'defender_clan_id':war.defender_clan_id,'winner_clan_id':war.winner_clan_id,
            'round':war.round,'log':(war.log or [])[-25:],
            'fighters':[{'player_id':f.player_id,'name':names.get(f.player_id,'Выживший'),
                         'side':f.side,'hp':f.hp,'max_hp':f.max_hp,'damage':f.damage,
                         'last_action_round':f.last_action_round} for f in fighters]}
