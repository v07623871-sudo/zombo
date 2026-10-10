import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from models import Base, Player, ItemStack
from gear import (RARITIES, GearItem, create_gear, roll_rarity, gear_values, gear_stats,
                  equip_gear, unequip_gear, upgrade_gear, dismantle_gear, MAX_UPGRADE, MAX_GEAR)
from game import give_item, item_count

@pytest.fixture
def db():
    engine=create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    with Session(engine,expire_on_commit=False) as session:
        session.add_all([Player(id=101,hero_class='soldier',caps=30000),Player(id=202,hero_class='thief',caps=30000)])
        session.commit()
        yield session
    engine.dispose()

def test_rarity_floor_and_stats(db):
    class FakeRng:
        def choices(self,names,**kwargs):return ['common']
    assert roll_rarity(5,'epic',FakeRng())=='epic'
    common=create_gear(db,101,'rifle','common')
    legend=create_gear(db,101,'rifle','legendary')
    assert gear_values(legend)['power']>gear_values(common)['power']
    assert gear_values(common)['power']==25

def test_equip_switch_legacy_cleanup(db):
    db.add(ItemStack(player_id=101,item_key='pistol',quantity=1,equipped=True))
    db.flush()
    a=create_gear(db,101,'knife','rare')
    b=create_gear(db,101,'rifle','legendary')
    equip_gear(db,101,a.id)
    assert gear_stats(db,101)['power']==gear_values(a)['power']
    assert item_count(db,101,'pistol')==1
    equip_gear(db,101,b.id)
    assert not a.equipped
    assert b.equipped
    assert gear_stats(db,101)['power']==gear_values(b)['power']
    unequip_gear(db,101,b.id)
    assert gear_stats(db,101)['power']==0

def test_only_owner_can_use_gear(db):
    item=create_gear(db,101,'knife')
    with pytest.raises(ValueError):equip_gear(db,202,item.id)
    p=db.get(Player,202)
    with pytest.raises(ValueError):upgrade_gear(db,p,item.id)
    with pytest.raises(ValueError):dismantle_gear(db,202,item.id)

def test_upgrade_cost_materials_and_caps(db):
    p=db.get(Player,101)
    item=create_gear(db,101,'rifle','rare')
    give_item(db,101,'metal',80)
    give_item(db,101,'rare',20)
    initial=p.caps
    upgrade_gear(db,p,item.id)
    assert item.level==1 and p.caps<initial
    assert gear_values(item)['power']>gear_values(create_gear(db,101,'rifle'))['power']
    for i in range(9):upgrade_gear(db,p,item.id)
    assert item.level==MAX_UPGRADE
    with pytest.raises(ValueError):upgrade_gear(db,p,item.id)

def test_dismantle_only_not_equipped(db):
    item=create_gear(db,101,'vest','epic')
    equip_gear(db,101,item.id)
    with pytest.raises(ValueError):dismantle_gear(db,101,item.id)
    unequip_gear(db,101,item.id)
    out=dismantle_gear(db,101,item.id)
    assert out['rare']==1
    assert item_count(db,101,'cloth')>0 and item_count(db,101,'rare')==1
    db.flush()
    assert db.get(GearItem,item.id) is None

def test_storage_capacity(db):
    for _ in range(MAX_GEAR):create_gear(db,101,'vest')
    with pytest.raises(ValueError,match='80'):create_gear(db,101,'vest')