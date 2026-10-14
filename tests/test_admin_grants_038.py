"""ZOMBO 0.38 admin panel: all live prizes, signed-only access and audited currency."""
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select, func

from tests.test_admin import server, headers
from admin import AdminAudit
from admin_grants import gift_catalog, GIFT_BOOSTS
from models import Player, Payment, ResourceLedger, SessionLocal
from gear import GearItem, MAX_GEAR
from game import ITEMS, PETS, item_count


ADMIN=98380001
USER=98380002


def grant(client,kind,key,amount=1,*,reason='Вознаграждение за событие',uid=None,**kwargs):
    return client.post(f'/api/admin/players/{USER}/grant',headers=headers(ADMIN),
        json={'kind':kind,'key':key,'amount':amount,'reason':reason,
              'request_id':uid or str(uuid4()),**kwargs})


def test_catalog_includes_every_real_category_not_just_a_few_materials():
    server.ADMIN_IDS.add(ADMIN)
    try:
        with TestClient(server.app) as api:
            api.get('/api/me',headers=headers(ADMIN))
            api.get('/api/me',headers=headers(USER))
            assert api.get('/api/admin/grant-catalog',headers=headers(USER)).status_code==403
            rsp=api.get('/api/admin/grant-catalog',headers=headers(ADMIN))
            assert rsp.status_code==200,rsp.text
            catalog=rsp.json()
            assert len(catalog['items'])>=40
            assert len(catalog['gear'])>=50
            assert len(catalog['pets'])==6
            assert len(catalog['premium'])==6
            assert 'zombo' in catalog['currencies']
            assert 'chest_legendary' in catalog['items']
            assert 'shadow_case' in catalog['items']
            assert 'field_dressing' in catalog['items']
            assert 'shadow_apex' in catalog['gear']
            assert catalog['rarities']['legendary']
            assert set(PETS)<=set(catalog['pets'])
            # Exclusive weapons are forged only through uniquely-ID'd gear items.
            assert 'shadow_apex' not in catalog['items']
    finally:server.ADMIN_IDS.discard(ADMIN)


def test_manual_zombo_gift_is_idempotent_audited_not_fake_telegram_payment():
    server.ADMIN_IDS.add(ADMIN)
    try:
        with TestClient(server.app) as api:
            api.get('/api/me',headers=headers(ADMIN));api.get('/api/me',headers=headers(USER))
            with SessionLocal() as db:
                old=db.get(Player,USER).zombo
                payments=db.scalar(select(func.count()).select_from(Payment)) or 0
            uid=str(uuid4())
            unauthorized=api.post(f'/api/admin/players/{USER}/grant',headers=headers(USER),
                json={'kind':'currency','key':'zombo','amount':500,
                      'request_id':str(uuid4()),'reason':'Unauthorized attempt'})
            assert unauthorized.status_code==403
            ok=grant(api,'currency','zombo',500,uid=uid)
            assert ok.status_code==200,ok.text
            assert ok.json()['field'] if 'field' in ok.json() else ok.json()['audit_id']
            replay=grant(api,'currency','zombo',500,uid=uid)
            assert replay.status_code==200 and replay.json()['replayed']
            with SessionLocal() as db:
                assert db.get(Player,USER).zombo==old+500
                assert db.scalar(select(func.count()).select_from(Payment))==payments
                audit=db.scalar(select(AdminAudit).where(AdminAudit.request_id==uid))
                assert audit.actor_id==ADMIN and audit.target_id==USER
                assert audit.field=='currency:zombo' and audit.action=='grant'
                ledger=db.scalars(select(ResourceLedger).where(
                    ResourceLedger.source_event==f'admin-grant:{uid}')).all()
                assert len(ledger)==1
                assert ledger[0].resource_key=='zombo' and ledger[0].delta==500
            denied=grant(api,'currency','zombo',amount=0)
            assert denied.status_code==422
            invalid=grant(api,'currency','ethereum',20)
            assert invalid.status_code==400
    finally:server.ADMIN_IDS.discard(ADMIN)


def test_admin_can_give_all_stackable_types_and_unique_legendary_at_plus_ten():
    server.ADMIN_IDS.add(ADMIN)
    try:
        with TestClient(server.app) as api:
            api.get('/api/me',headers=headers(ADMIN));api.get('/api/me',headers=headers(USER))
            for key,quantity in (
                ('metal',7),('medkit',2),('chest_legendary',1),
                ('shadow_case',2),('energy_cells',4)):
                with SessionLocal() as db:
                    old=item_count(db,USER,key)
                response=grant(api,'item',key,quantity)
                assert response.status_code==200,(key,response.text)
                with SessionLocal() as db:
                    assert item_count(db,USER,key)==old+quantity
            gun=grant(api,'gear','shadow_apex',rarity='legendary',level=10)
            assert gun.status_code==200,gun.text
            ids=gun.json()['gear_ids']
            assert len(ids)==1
            with SessionLocal() as db:
                item=db.get(GearItem,ids[0])
                assert item.player_id==USER and item.base_key=='shadow_apex'
                assert item.rarity=='legendary' and item.level==10
                assert item.source=='admin'
            wrong=grant(api,'gear','unobtainium',rarity='legendary')
            assert wrong.status_code==400
    finally:server.ADMIN_IDS.discard(ADMIN)


def test_admin_can_gift_pet_with_level_and_activate_vip_and_insurance():
    server.ADMIN_IDS.add(ADMIN)
    try:
        with TestClient(server.app) as api:
            api.get('/api/me',headers=headers(ADMIN));api.get('/api/me',headers=headers(USER))
            p=grant(api,'pet','raven',level=8)
            assert p.status_code==200,p.text
            with SessionLocal() as db:
                player=db.get(Player,USER)
                assert player.stats['_pet']=={'key':'raven','level':8,'xp':0}
            for boost in ('vip_7','xp_day','loot_day','insurance_day'):
                r=grant(api,'premium',boost)
                assert r.status_code==200,(boost,r.text)
            with SessionLocal() as db:
                user=db.get(Player,USER)
                assert user.vip_until is not None
                assert user.xp_boost_until is not None
                assert user.loot_boost_until is not None
                assert user.stats['_insurance_until']
            assert grant(api,'pet','not_a_pet').status_code==400
    finally:server.ADMIN_IDS.discard(ADMIN)


def test_admin_gift_invalid_attempts_do_not_create_audit():
    server.ADMIN_IDS.add(ADMIN)
    try:
        with TestClient(server.app) as api:
            api.get('/api/me',headers=headers(ADMIN));api.get('/api/me',headers=headers(USER))
            uid=str(uuid4())
            r=grant(api,'gear','shadow_apex',MAX_GEAR+1,uid=uid)
            assert r.status_code==400
            with SessionLocal() as db:
                assert db.scalar(select(AdminAudit).where(AdminAudit.request_id==uid)) is None
            uid2=str(uuid4())
            r=grant(api,'item','nonexistent',1,uid=uid2)
            assert r.status_code==400
            with SessionLocal() as db:
                assert db.scalar(select(AdminAudit).where(AdminAudit.request_id==uid2)) is None
    finally:server.ADMIN_IDS.discard(ADMIN)


def test_admin_ui_has_search_all_grants_and_no_obsolete_restriction():
    from pathlib import Path
    source=(Path(__file__).resolve().parents[1]/'static'/'app.js').read_text(encoding='utf-8')
    for needle in ('admin/grant-catalog','adminGrantEntries',
                   'fillAdminGrantItems','admin-grant-confirm',
                   "request_id:crypto.randomUUID()",
                   "ВЫДАТЬ ЛЮБОЙ ПРЕДМЕТ",
                   "kind==='pet'||kind==='premium'",
                   "admin-gift-rarity"):
        assert needle in source,needle
    assert 'Zombo через админку не зачисляется.' not in source
