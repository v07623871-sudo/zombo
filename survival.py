"""Bounded survival pressure shared by the live game and balance simulator.

0–69 hunger/thirst is normal. Poor supplies weaken combat at 70 and 95,
but cannot softlock a player: supplies can still be scavenged or purchased.
There is no passive AFK starvation and no automatic account death.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Survival:
    hunger: int
    thirst: int
    damage_mult: float
    hp_regen_blocked: bool
    status: str


def _level(value):
    if value>=95:return 2
    if value>=70:return 1
    return 0


def survival(hunger,thirst):
    h=max(0,min(100,int(hunger or 0)))
    t=max(0,min(100,int(thirst or 0)))
    penalty=(0,.12,.22)[_level(h)]+(0,.12,.22)[_level(t)]
    tier=max(_level(h),_level(t))
    return Survival(h,t,round(1-penalty,2),tier==2,
                    ('Сытость и вода в норме','Истощение: снижен урон',
                     'Критическое истощение: нет восстановления HP')[tier])


def apply_exertion(player,*,hunger=2,thirst=3):
    """Active play expends food/water; AFK alone does not."""
    player.hunger=min(100,max(0,int(player.hunger or 0)+max(0,hunger)))
    player.thirst=min(100,max(0,int(player.thirst or 0)+max(0,thirst)))
