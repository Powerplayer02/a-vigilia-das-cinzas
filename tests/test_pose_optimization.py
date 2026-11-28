"""Prior pose fixtures and native alignment guard contact geometry during optimization."""
import json
from pathlib import Path

import pytest
from panda3d.core import NodePath,Point3
from vigilia.combat.attack import Attack
from vigilia.combat.fighter import Fighter
from vigilia.combat.hitbox import evaluate_pose
from vigilia.core.mathx import Transform,Vec3
from vigilia.engine.render import ArenaRenderer
from vigilia.model.bosses import load_boss_profile

ROOT=Path(__file__).resolve().parents[1]


def test_poses_match_coordinates_and_contact_radii_from_before_optimization():
    rows=json.loads((ROOT/'tests/fixtures/combat_pose_before_optimization.json').read_text())
    for row in rows:
        profile=load_boss_profile(ROOT/f"data/bosses/{row['profile']}.toml",register=False)
        definition=next(a for a in profile.weapon.attacks if a.kind.value==row['attack'])
        fighter=Fighter(1,profile.weapon.instantiate(),profile.stats)
        fighter.body_scale=row['scale'];fighter.blocking=row['blocking'];fighter.knockdown_steps=row['knockdown']
        fighter.attack=Attack(definition,row['age'])
        pose=evaluate_pose(Transform(Vec3(*row['position']),row['yaw']),fighter,
            dodge=row['dodge'],rolling=row['rolling'])
        assert pose.bones.keys()==row['bones'].keys()
        assert pose.volumes.keys()==row['volumes'].keys()
        for name,expected in row['bones'].items():
            value=pose.bones[name]
            assert (value.x,value.y,value.z)==pytest.approx(expected,abs=1e-12)
        for name,(expected,radius) in row['volumes'].items():
            value,actual_radius=pose.volumes[name]
            assert (value.x,value.y,value.z)==pytest.approx(expected,abs=1e-12)
            assert actual_radius==radius


def test_cached_local_points_cannot_share_mutable_world_pose_mappings():
    profile=load_boss_profile(ROOT/'data/bosses/warden.toml',register=False)
    fighter=Fighter(1,profile.weapon.instantiate(),profile.stats)
    first=evaluate_pose(Transform(),fighter);expected=first.bones.copy()
    first.bones.clear();first.volumes.clear()
    assert evaluate_pose(Transform(),fighter).bones==expected
    fighter.blocking=True
    assert evaluate_pose(Transform(),fighter).bones['shield']!=expected['shield']


def test_arm_alignment_cache_invalidates_after_parent_motion():
    renderer=ArenaRenderer.__new__(ArenaRenderer);renderer.root=NodePath('root')
    rig=renderer.root.attach_new_node('rig');limb=rig.attach_new_node('arm')
    limb.set_pos(.3,0,.5);target=Vec3(.7,.8,.4)
    renderer._align_arm(limb,target)
    first=limb.get_transform(renderer.root)
    renderer._align_arm(limb,target)
    assert first==limb.get_transform(renderer.root)
    rig.set_h(35);rig.set_pos(3,2,1)
    renderer._align_arm(limb,target)
    local=limb.get_relative_point(renderer.root,Point3(target.x,target.y,target.z))
    assert abs(local.x)<2e-5 and abs(local.y)<2e-5 and local.z<0
