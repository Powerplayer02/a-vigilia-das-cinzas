"""Encontro puro com corpos falsos e relógio controlado pelos testes."""

import math
from pathlib import Path
from random import Random
from types import SimpleNamespace

from combat_fakes import PhysicsFake
from vigilia.ai.bosses import BossSystem
from vigilia.combat.fighter import Fighter
from vigilia.core.events import EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.entities.components import AttackIntent, MovementIntent, BodyRef, BossTag
from vigilia.entities.ecs import World
from vigilia.model.bosses import load_boss_profile
from vigilia.model.items import LONGSWORD_SPEC
from vigilia.model.stats import StatsBlock


PROFILE_PATH = Path(__file__).resolve().parents[1] / "data/bosses/warden.toml"


def encounter(distance=3, rng=None):
    world, bus = World(), EventBus()
    hero = Fighter(0, LONGSWORD_SPEC.instantiate(), StatsBlock(vigor=100))
    player = world.spawn(Transform(Vec3(0, 27 - distance, 1), 0), hero)
    profile = load_boss_profile(PROFILE_PATH)
    fighter = Fighter(1, profile.weapon.instantiate(), profile.stats)
    entity = world.spawn(Transform(Vec3(0, 27, 1), math.pi), fighter,
                         AttackIntent(), MovementIntent(), BodyRef(PhysicsFake()), BossTag(profile.id))
    boss = BossSystem(world, entity, player, profile, bus, Vec3(0, 27, 1), rng or Random(4))
    return SimpleNamespace(world=world, bus=bus, player=player, hero=hero, entity=entity,
                           fighter=fighter, boss=boss, profile=profile)
