"""Economy diagnostics and reproducible net survival-cycle regressions."""
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.test_game import app
import app as server
from models import Clan, Player, ResourceLedger, ClanTreasuryLedger, SessionLocal
from economy import flow_report
from scripts import simulate_economy as sim


def auth(pid):
    return {'Authorization': f'demo:{pid}'}


def test_economy_report_auth_periods_and_wallet_treasury_conservation():
    admin_id, ordinary_id = 99873111, 99873112
    server.ADMIN_IDS.add(admin_id)
    try:
        with TestClient(app) as c:
            for pid in (admin_id, ordinary_id):
                assert c.post('/api/class', headers=auth(pid),
                              json={'key':'soldier'}).status_code in (200,400)
            assert c.get('/api/admin/economy/flows',headers=auth(ordinary_id)).status_code == 403
            assert c.get('/api/admin/economy/flows',headers=auth(admin_id),
                         params={'days':2}).status_code == 422
            assert c.get('/api/admin/economy/flows',headers=auth(admin_id),
                         params={'days':91}).status_code == 422
            first=c.get('/api/admin/economy/flows',headers=auth(admin_id),
                        params={'days':7})
            assert first.status_code == 200,first.text
            before=first.json()
            with SessionLocal.begin() as db:
                p=db.get(Player,ordinary_id)
                clan=Clan(name='BalanceAudit_'+str(ordinary_id),leader_id=ordinary_id,
                          treasury=0)
                db.add(clan);db.flush()
                p.caps-=60
                clan.treasury+=60
            second=c.get('/api/admin/economy/flows',headers=auth(admin_id))
            assert second.status_code == 200,second.text
            after=second.json()
            assert after['net_wallet_caps']-before['net_wallet_caps']==-60
            assert after['net_clan_caps']-before['net_clan_caps']==60
            assert after['net_combined_caps']==before['net_combined_caps']
            assert after['combined_caps_now']==(
                after['wallet_caps_now']+after['treasury_caps_now'])
            assert after['ledger_first_seen'] is not None
            assert after['warning'] and 'журнал' in after['warning'].lower()
            assert any(x['key']=='currency|caps' for x in after['wallet_flows'])
            assert any(x['key']==str(clan.id) for x in after['treasury_flows'])
    finally:
        server.ADMIN_IDS.discard(admin_id)


def test_economy_report_real_ledger_sums():
    with SessionLocal() as db:
        report=flow_report(db,days=30)
        wallets=db.scalars(select(ResourceLedger)).all()
        clans=db.scalars(select(ClanTreasuryLedger)).all()
        assert report['net_combined_caps'] == (sum(
            row.delta for row in wallets
            if row.kind=='currency' and row.resource_key=='caps')+
            sum(row.delta for row in clans))
        assert report['net_xp'] == sum(row.delta for row in wallets if row.kind=='xp')


def test_economy_cycle_is_deterministic_nonnegative_and_bounded():
    a=sim.simulate('forest','soldier',days=7,actions=12,seed=11,taxed=True)
    b=sim.simulate('forest','soldier',days=7,actions=12,seed=11,taxed=True)
    assert a==b
    assert a['fights']>=a['wins']
    assert a['initial_caps']==150
    assert a['final_caps']>=0
    assert a['medkits_used']>=0
    assert a['level_ups']>=0
    assert a['territory_tax']>=0
    assert a['gross_combat_caps']+a['daily_caps']+a['quest_caps']-a['territory_tax']-a['death_losses']-a['merchant_spend']==a['net_caps']
    taxed=sim.simulate('forest','soldier',days=7,actions=12,seed=11,taxed=False)
    assert taxed['territory_tax']==0
    assert taxed['net_caps']>=a['net_caps']


def test_economy_simulation_uses_many_classes_and_cli_payload():
    for zone,hero in [('city','medic'),('wasteland','assassin'),('factory','thief')]:
        a=sim.aggregate(zone,hero,days=2,actions=8,runs=3,seed=21)
        assert a['runs']==3
        assert a['net_caps_max']>=a['net_caps_min']
        assert 0<=a['death_rate_per_fight']<=1
    assert sim.main(['--runs','2','--days','1','--actions','5'])['scenarios']
