"""Máquina do Vigia da Fornalha, conectada ao mundo por eventos."""

import math
from dataclasses import dataclass
from random import Random

from vigilia.combat.attack import AttackKind
from vigilia.combat.events import HPChangedEvent, EntityDied, StaggerTriggered, ParrySucceeded
from vigilia.combat.fighter import Fighter
from vigilia.combat.hitbox import sphere_radius
from vigilia.core.events import (
    Event, EventBus, BossArenaEnteredEvent, BossDefeatedEvent, MusicChangeRequestedEvent, ItemUseStartedEvent,
)
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.timing import BOSS_RIPOSTE_STEPS
from vigilia.entities.components import AttackIntent, MovementIntent
from vigilia.entities.ecs import Entity, World
from vigilia.model.bosses import BossProfile
from vigilia.model.items import WEAPONS
from vigilia.model.snapshots import BossSnapshot


@dataclass(frozen=True, slots=True)
class PhaseTransitionEvent(Event):
    boss_id: str
    phase: int


class BossSystem:
    """Usa Fighter, intenções e o MovementSystem já compartilhado."""

    def __init__(self, world: World, entity: Entity, player: Entity, profile: BossProfile,
                 bus: EventBus, spawn: Vec3, rng: Random | None = None, *, hazard_sink=None) -> None:
        self.entity, self.player, self.profile = entity, player, profile
        self._world, self._bus, self.spawn = world, bus, spawn
        self._rng = rng if rng is not None else Random()
        self.hazard_step, self.hazard_sink = 0, hazard_sink
        self.phase = 1
        self.active = False
        self.defeated = False
        self.intro_remaining = self.transition_remaining = self.death_remaining = 0
        self.punish_cooldown = self.grab_cooldown = self.aoe_cooldown = self.pause_remaining = 0
        self.blocking_steps = self.close_steps = 0
        self.last_move = ""
        self._previous_player_attack = None
        self._combo_count = 0
        self._reaction = False
        self.fighter.body_scale, self.fighter.backstab_immune = 1.8, True
        self.fighter.status_damage_blocked = True
        bus.subscribe(BossArenaEnteredEvent, self._on_enter)
        bus.subscribe(HPChangedEvent, self._on_hp)
        bus.subscribe(EntityDied, self._on_death)
        bus.subscribe(StaggerTriggered, self._on_stagger)
        bus.subscribe(ParrySucceeded, self._on_parry)
        bus.subscribe(ItemUseStartedEvent, self._on_item)

    @property
    def fighter(self) -> Fighter:
        fighter = self._world.get(self.entity, Fighter)
        assert fighter is not None
        return fighter

    def close(self):
        for kind, handler in ((BossArenaEnteredEvent, self._on_enter), (HPChangedEvent, self._on_hp),
            (EntityDied, self._on_death), (StaggerTriggered, self._on_stagger),
            (ParrySucceeded, self._on_parry), (ItemUseStartedEvent, self._on_item)):
            self._bus.unsubscribe(kind, handler)

    def _on_enter(self, event: BossArenaEnteredEvent) -> None:
        if event.boss_id == self.profile.id:
            self.start()

    def start(self) -> None:
        if self.defeated or self.active:
            return
        self.active = True
        self.intro_remaining = self.profile.intro_steps
        self.fighter.invulnerable = True
        self.fighter.status_damage_blocked = True
        self._bus.publish(MusicChangeRequestedEvent(f"{self.profile.music_prefix}_phase{self.phase}"))

    def _on_hp(self, event: HPChangedEvent) -> None:
        if event.entity_id != self.entity.id or event.new_hp <= 0:
            return
        next_phase = 3 if self.profile.phase3_threshold and event.new_hp < self.profile.max_hp * self.profile.phase3_threshold else (
            2 if event.new_hp < self.profile.max_hp * self.profile.phase2_threshold else 1)
        if next_phase <= self.phase:
            return
        self.phase = next_phase
        self.hazard_step = 0
        self.intro_remaining = 0
        self.transition_remaining = self.profile.transition_steps
        self.fighter.attack = None
        self.fighter.invulnerable = self.fighter.status_damage_blocked = True
        intent = self._world.get(self.entity, AttackIntent)
        if intent is not None:
            intent.definition = None
        self._bus.publish(PhaseTransitionEvent(self.profile.id, next_phase))
        self._bus.publish(MusicChangeRequestedEvent(f"{self.profile.music_prefix}_phase{next_phase}", fade_sec=.5))

    def _on_death(self, event: EntityDied) -> None:
        if event.target == self.entity.id and not self.defeated and not self.death_remaining:
            self.death_remaining = self.profile.death_steps
            self.fighter.attack = None

    def _open_riposte(self) -> None:
        if self.phase >= 2:
            self.fighter.riposte_steps = BOSS_RIPOSTE_STEPS
            self.fighter.riposte_hits_remaining = 4

    def _on_stagger(self, event: StaggerTriggered) -> None:
        if event.target == self.entity.id and not self.fighter.riposte_steps:
            self._open_riposte()

    def _on_parry(self, event: ParrySucceeded) -> None:
        if event.attacker == self.entity.id:
            self._open_riposte()

    def _on_item(self, event: ItemUseStartedEvent) -> None:
        if event.entity_id == self.player.id and event.item_id == "estus":
            self._reaction = True

    def tick(self, world: World) -> None:
        fighter = self.fighter
        movement = world.get(self.entity, MovementIntent)
        intent = world.get(self.entity, AttackIntent)
        pose = world.get(self.entity, Transform)
        target, player = world.get(self.player, Transform), world.get(self.player, Fighter)
        assert movement is not None and intent is not None and pose is not None and target is not None and player is not None
        movement.velocity, intent.definition = Vec3(), None
        if self.defeated:
            return
        overhead, sweep, punish, grasp, nova = (move.kind for move in self.profile.weapon.attacks)
        min_x, min_y, max_x, max_y = self.profile.bounds
        if not fighter.alive:
            if self.death_remaining:
                self.death_remaining -= 1
                if self.death_remaining == 0:
                    self.defeated, self.active = True, False
                    self._bus.publish(BossDefeatedEvent(self.profile.id, self.profile.souls))
            return
        if not self.active:
            fighter.invulnerable = True
            fighter.status_damage_blocked = True
            return
        if self.intro_remaining or self.transition_remaining:
            fighter.invulnerable = True
            fighter.status_damage_blocked = True
            if self.intro_remaining:
                self.intro_remaining -= 1
            else:
                self.transition_remaining -= 1
            return
        if self.phase == 3:
            self.hazard_step = (self.hazard_step + 1) % 720
            if self.hazard_step % 360 in (90, 110, 130) and self.hazard_sink:
                self.hazard_sink(self.entity.id, self.hazard_position, 2.4)
        fighter.invulnerable = False
        fighter.status_damage_blocked = False
        for name in ("punish_cooldown", "grab_cooldown", "aoe_cooldown", "pause_remaining"):
            setattr(self, name, max(0, getattr(self, name) - 1))
        delta = (target.position - pose.position).flat()
        distance = delta.length()
        self.blocking_steps = self.blocking_steps + 1 if player.blocking else 0
        self.close_steps = self.close_steps + 1 if distance < 2 else 0
        self._observe_combo(player)
        if not player.alive or fighter.stagger_steps or fighter.riposte_steps:
            return
        if fighter.attack is not None:
            if fighter.attack.definition.kind == punish and not fighter.attack.definition.ranged and (
                    fighter.attack.age < fighter.attack.definition.windup + fighter.attack.definition.active):
                movement.velocity = pose.forward() * 3.2
            return
        if self.last_move:
            self._finish_recovery()
        if self.pause_remaining:
            direction = Vec3(delta.y, -delta.x).normalized()
            if min_x + 2 < pose.position.x < max_x - 2 and min_y + 1.5 < pose.position.y < max_y - 1:
                movement.velocity = direction * 1.2
            return
        if not (min_x < target.position.x < max_x and min_y < target.position.y < max_y):
            return
        pose.yaw = math.atan2(delta.x, delta.y)
        if (self.profile.weapon.attacks[2].ranged and 4 < distance <= self.profile.weapon.attacks[2].reach
                and not self.punish_cooldown):
            intent.definition, intent.target = self.profile.weapon.attacks[2], self.player.id
            intent.aim = target.position + Vec3(0, 0, .2)
            self.punish_cooldown, self.last_move = self.profile.punish_cooldown, punish.value
            return
        if distance > 4:
            aggression = self.profile.aggression_phase2 if self.phase >= 2 else self.profile.aggression_phase1
            movement.velocity = delta.normalized() * (1.5 * (1 + aggression))
            return
        kind = None
        if self.phase >= 2 and self.close_steps >= self.profile.close_trigger_steps and not self.aoe_cooldown:
            kind = nova
            self.aoe_cooldown = self.profile.aoe_cooldown // (2 if self.phase == 3 else 1)
            self.close_steps = 0
        elif self.phase >= 2 and distance <= 3 and self.blocking_steps >= self.profile.guard_trigger_steps and not self.grab_cooldown:
            kind = grasp
            self.grab_cooldown = self.profile.grab_cooldown // (2 if self.phase == 3 else 1)
            self.blocking_steps = 0
        elif self._reaction and not self.punish_cooldown:
            kind = punish
            self.punish_cooldown = self.profile.punish_cooldown
            self._reaction = False
        else:
            kind = overhead if self._rng.random() < .6 else sweep
        intent.definition = self.profile.weapon.attack(kind)
        intent.target = None if kind == nova else self.player.id
        intent.aim = target.position + Vec3(0, 0, .2) if intent.definition.ranged else None
        self.last_move = kind.value

    def _observe_combo(self, player: Fighter) -> None:
        attack = player.attack
        if attack is not self._previous_player_attack:
            if attack is None:
                if self._combo_count >= 2:
                    self._reaction = True
                self._combo_count = 0
            elif attack.definition.kind == AttackKind.LIGHT_1:
                self._combo_count = 1
            elif attack.definition.kind in (AttackKind.LIGHT_2, AttackKind.LIGHT_3):
                self._combo_count += 1
            else:
                self._combo_count = 0
            self._previous_player_attack = attack

    def _finish_recovery(self) -> None:
        kind = AttackKind(self.last_move)
        self.last_move = ""
        if kind in tuple(move.kind for move in self.profile.weapon.attacks[3:]):
            return
        immediate = .85 if self.phase >= 2 else .4 if kind == self.profile.weapon.attacks[0].kind else (
            .7 if kind == self.profile.weapon.attacks[1].kind else self.profile.aggression_phase1)
        if self._rng.random() >= immediate:
            self.pause_remaining = self.profile.reposition_steps // (2 if self.phase == 3 else 1)

    @property
    def hazard_position(self):
        x0, y0, x1, y1 = self.profile.bounds
        return Vec3((x0+x1)/2 + (-5 if self.hazard_step < 360 else 5), (y0+y1)/2, .06)

    @property
    def hazard_visible(self):
        return (self.phase == 3 and self.active and self.fighter.alive and
                not self.transition_remaining and self.hazard_step % 360 < 150)

    @property
    def visual_radius(self) -> float:
        attack = self.fighter.attack
        if attack is None or attack.definition.hitbox_kind.value != "center_sphere":
            return 0
        definition = attack.definition
        if attack.age < definition.windup:
            return definition.sphere_radius_start * attack.age / definition.windup
        return sphere_radius(definition, attack.age) if attack.active else 0

    def reset_on_rest(self) -> None:
        if self.defeated or not self.fighter.alive:
            return
        self.fighter.restore()
        self.hazard_step = 0
        self.phase, self.active = 1, False
        self.intro_remaining = self.transition_remaining = self.pause_remaining = 0
        self.punish_cooldown = self.grab_cooldown = self.aoe_cooldown = 0
        self.blocking_steps = self.close_steps = 0
        self.last_move = ""
        self._previous_player_attack, self._combo_count, self._reaction = None, 0, False
        self.fighter.invulnerable = True
        self.fighter.status_damage_blocked = True
        pose = self._world.get(self.entity, Transform)
        assert pose is not None
        pose.position, pose.yaw = self.spawn, math.pi

    def reload_profile(self, profile: BossProfile) -> None:
        """Reinicia o encontro ao aplicar números novos pelo atalho de desenvolvimento."""
        if profile.id != self.profile.id or profile.arena != self.profile.arena:
            raise ValueError("Hot-reload mantém os identificadores do chefe e da arena.")
        if self.defeated or not self.fighter.alive:
            raise ValueError("Recarregue o perfil antes de derrotar o chefe.")
        was_active = self.active
        self.profile = profile
        WEAPONS[profile.weapon.id] = profile.weapon
        self.fighter.stats, self.fighter.weapon = profile.stats, profile.weapon.instantiate()
        self.reset_on_rest()
        if was_active:
            self.start()

    def to_snapshot(self, actor_keys: dict[int, str]) -> BossSnapshot:
        pose = self._world.get(self.entity, Transform)
        assert pose is not None
        return BossSnapshot(
            self.profile.id, self.phase, pose.position, pose.yaw,
            None if self.defeated else self.fighter.to_snapshot(actor_keys), self.active,
            self.intro_remaining, self.transition_remaining, self.death_remaining,
            self.punish_cooldown, self.grab_cooldown, self.aoe_cooldown, self.pause_remaining,
            self.blocking_steps, self.close_steps, self.last_move, self.hazard_step,
        )

    def from_snapshot(self, snapshot: BossSnapshot, actor_ids: dict[str, int], defeated: bool) -> None:
        self.defeated, self.active, self.phase = defeated, snapshot.active and not defeated, snapshot.phase
        if snapshot.fighter is not None:
            self.fighter.from_snapshot(snapshot.fighter, actor_ids)
        else:
            self.fighter.hp = 0
            self.fighter.attack = None
        for name in ("intro_remaining", "transition_remaining", "death_remaining", "punish_cooldown",
                     "grab_cooldown", "aoe_cooldown", "pause_remaining", "blocking_steps", "close_steps", "last_move", "hazard_step"):
            setattr(self, name, getattr(snapshot, name))
        pose = self._world.get(self.entity, Transform)
        assert pose is not None
        pose.position, pose.yaw = snapshot.position, snapshot.yaw
        self._previous_player_attack, self._combo_count, self._reaction = None, 0, False
        self.fighter.status_damage_blocked = not self.active or bool(self.intro_remaining or self.transition_remaining)
