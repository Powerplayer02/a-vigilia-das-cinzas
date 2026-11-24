"""Dados de campanha, rotas, chefe e regiões dormentes sem abrir janela."""

from dataclasses import replace
from pathlib import Path
from random import Random

import pytest
from test_save import full_snapshot
from ui_fakes import BackendFake, QueryFake
from vigilia.ai.bosses import BossSystem
from vigilia.ai.pathfinding import a_star, line_of_sight
from vigilia.combat.events import EntityDied, HPChangedEvent
from vigilia.combat.fighter import Fighter
from vigilia.core.events import EventBus, BossDefeatedEvent, MusicChangeRequestedEvent
from vigilia.core.mathx import Vec3, Transform
from vigilia.entities.ecs import World
from vigilia.entities.components import AttackIntent, MovementIntent
from vigilia.model.bosses import load_boss_profile
from vigilia.model.enemies import ENEMIES
from vigilia.model.items import LONGSWORD_SPEC
from vigilia.model.snapshots import AreaSnapshot, ActorSnapshot
from vigilia.save.serializers import encode, decode, SaveFormatError
from vigilia.ui.hud import HUD
from vigilia.ui.widgets import Panel
from vigilia.ui.map_view import MapView
from vigilia.world.area import load_area
from vigilia.world.bonfire import BONFIRES
from vigilia.world.map_data import MapDataProvider
from vigilia.model.world_state import WorldState

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("identity", ("catedral_submersa", "pantano_das_cinzas"))
def test_all_regional_spawns_and_passages_have_routes_from_shared_collision_geometry(identity):
    area = load_area(ROOT / "data/areas" / (identity + ".toml"))
    grid = area.navigation(fog_closed=False)
    destinations = [row.position for row in area.enemies] + [row.position for row in area.passages] + list(area.fires)
    assert len({row.profile for row in area.enemies}) >= 2
    for point in destinations:
        assert grid.walkable(grid.to_cell(point)), point
        route = a_star(grid, area.spawn, point)
        assert route, point
        cells = [grid.to_cell(position) for position in route]
        assert all(line_of_sight(grid, start, end) for start, end in zip(cells, cells[1:]))


def test_tide_fog_closes_only_route_to_boss_and_defeat_opens_it():
    area = load_area(ROOT / "data/areas/pantano_das_cinzas.toml")
    boss = Vec3(*area.boss["spawn"])
    assert not a_star(area.navigation(fog_closed=True), area.spawn, boss)
    assert a_star(area.navigation(fog_closed=False), area.spawn, boss)


def tide_encounter():
    profile = load_boss_profile(ROOT / "data/bosses/tide.toml")
    world, bus = World(), EventBus()
    player = world.spawn(Transform(Vec3(120, 27.5, 1)), Fighter(0, LONGSWORD_SPEC.instantiate()))
    entity = world.spawn(Transform(Vec3(120, 29, 1.65)), Fighter(1, profile.weapon.instantiate(), profile.stats),
        AttackIntent(), MovementIntent())
    boss = BossSystem(world, entity, player, profile, bus, Vec3(120, 29, 1.65), Random(7))
    return world, bus, player, boss


def test_tide_threshold_once_cancels_attack_and_expands_moveset_after_transition():
    world, bus, player, boss = tide_encounter()
    music = []
    bus.subscribe(MusicChangeRequestedEvent, music.append)
    boss.start()
    assert boss.profile.max_hp == 3800 and boss.fighter.poise == 160
    assert len(boss.profile.moveset(1)) == 3 and len(boss.profile.moveset(2)) == 5
    boundary = boss.profile.max_hp * boss.profile.phase2_threshold
    bus.publish(HPChangedEvent(boss.entity.id, 3800, boundary, 3800, "player"))
    assert boss.phase == 1
    boss.fighter.hp = boundary - 1
    bus.publish(HPChangedEvent(boss.entity.id, boundary, boundary - 1, 3800, "player"))
    assert boss.phase == 2 and boss.fighter.invulnerable and boss.transition_remaining == 90
    assert music[-1].track_id == "tide_boss_phase2"
    boss.tick(world)
    bus.publish(HPChangedEvent(boss.entity.id, boundary - 1, boundary - 2, 3800, "player"))
    assert boss.transition_remaining == 89
    for _ in range(89):
        boss.tick(world)
    boss.close_steps = boss.profile.close_trigger_steps - 1
    boss.tick(world)
    assert world.get(boss.entity, AttackIntent).definition.kind.value == "tide_nova"
    assert not boss.fighter.invulnerable


def test_tide_ranged_punish_targets_player_and_reward_fires_once_after_death_animation():
    world, bus, player, boss = tide_encounter()
    world.get(player, Transform).position = Vec3(120, 22, 1)
    boss.start()
    boss.intro_remaining = 0
    boss.tick(world)
    intent = world.get(boss.entity, AttackIntent)
    assert intent.definition.ranged and intent.aim == Vec3(120, 22, 1.2)
    rewards = []
    bus.subscribe(BossDefeatedEvent, rewards.append)
    boss.fighter.hp = 0
    bus.publish(EntityDied(boss.entity.id))
    for _ in range(boss.profile.death_steps - 1):
        boss.tick(world)
    assert not rewards
    boss.tick(world)
    for _ in range(300):
        boss.tick(world)
    assert rewards == [BossDefeatedEvent("abbess_of_the_tide", 3600)]


def test_tide_grasp_requires_phase_two_and_sustained_guard():
    world, bus, player, boss = tide_encounter()
    boss.active, boss.phase, boss.aoe_cooldown = True, 2, 120
    boss.blocking_steps = boss.profile.guard_trigger_steps - 1
    world.get(player, Fighter).blocking = True
    boss.tick(world)
    assert world.get(boss.entity, AttackIntent).definition.kind.value == "tide_grasp"


def test_static_batch_keeps_cube_geometry_and_materials_without_per_box_draw_nodes():
    from panda3d.core import NodePath
    from vigilia.engine.render import ArenaRenderer
    renderer = ArenaRenderer.__new__(ArenaRenderer)
    renderer.statics, renderer._static_shapes, renderer.batch_statics = NodePath("statics"), [], True
    renderer.block("a", Vec3(), Vec3(2, 2, 2), (.2, .3, .4, 1))
    renderer.block("b", Vec3(4, 0, 0), Vec3(2, 2, 2), (.2, .3, .4, 1))
    renderer.finish_scene()
    assert renderer.statics.get_num_children() == 1
    assert renderer.statics.get_child(0).node().get_geom(0).get_vertex_data().get_num_rows() == 48
    minimum, maximum = renderer.statics.get_tight_bounds()
    assert tuple(minimum) == (-1, -1, -1) and tuple(maximum) == (5, 1, 1)
    assert not renderer._static_shapes


def test_save_load_in_clean_process_registers_boss_catalog_without_engine(tmp_path):
    import os
    import subprocess
    import sys
    from boss_fakes import encounter
    from vigilia.save.service import SaveService
    boss = encounter().boss
    snapshot = full_snapshot()
    data = boss.to_snapshot({boss.player.id: "player", boss.entity.id: boss.profile.id})
    snapshot = replace(snapshot, world=replace(snapshot.world, bosses=(data,), boss_phases={data.id: data.phase}))
    path = tmp_path / "catalog.sqlite3"
    SaveService(path).save(1, snapshot)
    script = """
from pathlib import Path
import sys
from vigilia.save.service import SaveService
snapshot = SaveService(Path(sys.argv[1])).load(1)
assert snapshot.world.bosses[0].fighter.weapon_id == 'forge_warden_weapon'
assert not any(name.split('.')[0] in ('panda3d', 'direct', 'pygame', 'numpy') for name in sys.modules)
"""
    result = subprocess.run([sys.executable, "-c", script, str(path)],
        env=os.environ | {"PYTHONPATH": str(ROOT / "src")}, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr


def test_dormant_actors_round_trip_keep_resources_and_death_flags():
    snapshot = full_snapshot()
    fighter = Fighter(1, ENEMIES["salt_guard"].weapon.instantiate(), ENEMIES["salt_guard"].stats)
    fighter.hp = 0
    actor = ActorSnapshot("catedral_submersa.enemy.0", Vec3(55, -5, .95), 1., fighter.to_snapshot({0: "player"}))
    world = replace(snapshot.world, dormant_areas={"catedral_submersa": AreaSnapshot((actor,), ())},
        dead_common=(*snapshot.world.dead_common, actor.key))
    snapshot = replace(snapshot, world=world)
    assert decode(snapshot.version, snapshot.timing_version, *encode(snapshot)) == snapshot
    with pytest.raises(SaveFormatError):
        encode(replace(snapshot, world=replace(world, dormant_areas={"patio_da_vigilia": AreaSnapshot()})))
    with pytest.raises(SaveFormatError):
        encode(replace(snapshot, world=replace(world, dead_common=tuple(key for key in world.dead_common if key != actor.key))))


def test_map_provider_and_fake_ui_fit_both_regions_without_world_import_in_ui():
    bus, state, pose = EventBus(), WorldState(), Transform(Vec3(120, -10, 1))
    data = MapDataProvider(state, pose, bus)
    for area in ("patio_da_vigilia", "catedral_submersa", "pantano_das_cinzas"):
        state.discovered_areas.add(area)
    state.visited_bonfires.update(("catedral_nave", "pantano_margem"))
    backend = BackendFake()
    Panel(backend, "menu", (0, 0, 1280, 720))
    view = MapView(backend, data)
    for region in data.regions():
        x, y, width, height = backend.nodes["menu.map.region." + region.id]["rect"]
        assert 0 <= x < x + width <= 672 and 40 <= y < y + height <= 350
    assert "menu.map.bonfire.catedral_nave" in backend.nodes
    assert "menu.map.player" in backend.nodes


def test_spell_and_item_have_independent_hud_slots_and_do_not_recreate_widgets():
    backend, query = BackendFake(), QueryFake()
    query.vitals = replace(query.vitals, spell_name="Estilhaço de brasa", spell_hint="E", spell_kind="arcane",
        spell_stamina=26, spell_ready=True, quick_item="Frasco", quick_count=2)
    hud = HUD(backend, query)
    hud.tick()
    nodes = {key: id(value) for key, value in backend.nodes.items()}
    updates = len(backend.updates)
    hud.tick()
    assert {key: id(value) for key, value in backend.nodes.items()} == nodes
    assert len(backend.updates) == updates
    assert "Estilhaço" in backend.nodes["hud.spell.label"]["text"] and "Frasco" in backend.nodes["hud.quick"]["text"]
    assert backend.nodes["hud.spell.icon"]["rect"] != backend.nodes["hud.quick_icon"]["rect"]
