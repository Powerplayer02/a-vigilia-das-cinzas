"""Resolução de contatos, guarda, críticos, stagger e morte."""

from vigilia.combat.attack import AttackKind, HitboxKind
from vigilia.combat.damage import resolve_damage
from vigilia.combat.events import DamageDealt, EntityDied, ParrySucceeded, StaggerTriggered, ShotFired, HPChangedEvent, HealingApplied
from vigilia.combat.fighter import Fighter
from vigilia.combat.hitbox import HURT_BONES, WEAPON_BONES
from vigilia.combat.parry import ParryOutcome, parry_outcome
from vigilia.core.events import EventBus
from vigilia.core.mathx import Transform, Vec3
from vigilia.core.protocols import IContactVolumes, IPhysicsWorld
from vigilia.core.timing import STAGGER_STEPS_HEAVY, STAGGER_STEPS_LIGHT, RIPOSTE_STEPS, HIT_REACT_STEPS
from vigilia.entities.ecs import World, Entity
from vigilia.entities.components import AttackIntent, BodyRef


def behind(attacker: Transform, defender: Transform) -> bool:
    """Exige uma posição a mais de 120 graus da direção frontal do defensor."""
    toward = (attacker.position - defender.position).flat().normalized()
    return toward.dot(defender.forward()) < -.5


class CombatSystem:
    """Consome os volumes sincronizados e publica os resultados do passo."""

    def __init__(self, contacts: IContactVolumes, physics: IPhysicsWorld, bus: EventBus) -> None:
        self._contacts = contacts
        self._physics = physics
        self._bus = bus

    def consume_intents(self, world: World) -> None:
        """Inicia ataques do ECS usando a mesma entrada de combate do jogador."""
        for _, (fighter, intent) in world.query(Fighter, AttackIntent):
            if intent.definition is not None:
                fighter.start(intent.definition, intent.target, intent.aim)
                intent.definition = None

    def queue_hazard(self, source, position, radius):
        if not hasattr(self, "_hazards"):
            self._hazards = []
        self._hazards.append((source, position, radius))

    def resolve(self, world: World) -> None:
        self._resolve_hazards(world)
        """Resolve contatos uma vez por alvo e execução de ataque."""
        actors = list(world.query(Transform, Fighter))
        for source, (source_transform, attacker) in actors:
            attack = attacker.attack
            if not attacker.alive or attack is None or not attack.active:
                continue
            if attack.definition.healing > 0:
                if source.id not in attack.hit_targets:
                    attack.hit_targets.add(source.id)
                    old_hp = attacker.hp
                    attacker.hp = min(attacker.max_hp, old_hp + attack.definition.healing + 2 * attacker.stats.faith)
                    self._bus.publish(HPChangedEvent(source.id, old_hp, attacker.hp, attacker.max_hp, "healing"))
                    self._bus.publish(HealingApplied(source.id, attacker.hp - old_hp))
                continue
            if attack.definition.ranged:
                self._shot(source.id, source_transform, attacker, actors)
                continue
            for target, (target_transform, defender) in actors:
                if attacker.attack is None:
                    break
                if (not defender.alive or defender.team == attacker.team or
                        target.id in attack.hit_targets or
                        (attack.victim is not None and target.id != attack.victim)):
                    continue
                delta = target_transform.position - source_transform.position
                area = attack.definition.hitbox_kind == HitboxKind.CENTER_SPHERE
                reach = attack.definition.sphere_radius_end if area else attack.definition.reach
                if delta.length() > reach + 1.2:
                    continue
                if self._physics.raycast(source_transform.position, target_transform.position) is not None:
                    continue
                if defender.invulnerable:
                    continue
                frontal = defender_front(target_transform, source_transform)
                shield_contact = not area and frontal and self._touches(source.id, target.id, ("shield",))
                outcome = parry_outcome(defender.parry_step)
                if shield_contact and attack.definition.parryable and outcome == ParryOutcome.SUCCESS:
                    attack.hit_targets.add(target.id)
                    attacker.interrupt(RIPOSTE_STEPS)
                    attacker.riposte_steps = RIPOSTE_STEPS
                    attacker.riposte_hits_remaining = 1
                    self._bus.publish(ParrySucceeded(target.id, source.id))
                    continue
                body_contact = (self._contacts.overlaps((source.id, "area"), ((target.id, "body_center"),))
                                if area else self._touches(source.id, target.id, HURT_BONES))
                blocked = attack.definition.blockable and frontal and (defender.blocking or
                                       (shield_contact and outcome == ParryOutcome.LATE_BLOCK))
                if not body_contact and not (shield_contact and blocked):
                    continue
                attack.hit_targets.add(target.id)
                self._hit(source.id, target.id, attacker, defender, source_transform,
                          target_transform, blocked)

    def _shot(self, source: int, transform: Transform, attacker: Fighter, actors: list) -> None:
        attack = attacker.attack
        assert attack is not None
        if attack.fired:
            return
        attack.fired = True
        damage_type = "magic" if attack.definition.packet.magic > 0 else "physical"
        origin = transform.position + Vec3(0, 0, .25)
        aim = attack.aim or (origin + transform.forward() * attack.definition.reach)
        end = origin + (aim - origin).normalized() * attack.definition.reach
        wall = self._physics.raycast(origin, end)
        eligible = {entity.id: (pose, fighter) for entity, (pose, fighter) in actors
                    if fighter.alive and fighter.team != attacker.team}
        hit = self._contacts.raycast(origin, end,
                                     tuple((key, bone) for key in eligible for bone in HURT_BONES))
        if wall is not None and (hit is None or wall.distance <= hit.distance):
            self._bus.publish(ShotFired(source, origin, wall.point, damage_type))
            return
        if hit is None:
            self._bus.publish(ShotFired(source, origin, end, damage_type))
            return
        target = hit.target[0]
        target_transform, defender = eligible[target]
        self._bus.publish(ShotFired(source, origin, hit.point, damage_type))
        if defender.invulnerable:
            return
        shield = self._contacts.raycast(origin, end, ((target, "shield"),))
        frontal = defender_front(target_transform, transform)
        shield_contact = frontal and shield is not None and shield.distance <= hit.distance
        outcome = parry_outcome(defender.parry_step)
        if shield_contact and attack.definition.parryable and outcome == ParryOutcome.SUCCESS:
            attacker.interrupt(RIPOSTE_STEPS)
            attacker.riposte_steps = RIPOSTE_STEPS
            attacker.riposte_hits_remaining = 1
            self._bus.publish(ParrySucceeded(target, source))
            return
        blocked = attack.definition.blockable and frontal and (
            defender.blocking or (shield_contact and outcome == ParryOutcome.LATE_BLOCK))
        self._hit(source, target, attacker, defender, transform, target_transform, blocked)

    def _resolve_hazards(self, world):
        from vigilia.model.attacks import DamagePacket
        pending, self._hazards = getattr(self, "_hazards", []), []
        for source, point, radius in pending:
            attacker = world.get(Entity(source), Fighter)
            if attacker is None or not attacker.alive:
                continue
            for entity, (pose, defender) in world.query(Transform, Fighter):
                if defender.team == attacker.team or not defender.alive or defender.invulnerable:
                    continue
                if (pose.position - point).flat().length() > radius:
                    continue
                amount = resolve_damage(DamagePacket(fire=28), attacker.stats, attacker.weapon,
                                        defender.stats, defender.resist).hp
                old_hp = defender.hp
                defender.hp = max(0, old_hp - amount)
                self._bus.publish(DamageDealt(source, entity.id, amount, defender.hp, False, "", "fire", "ember_vent"))
                self._bus.publish(HPChangedEvent(entity.id, old_hp, defender.hp, defender.max_hp, "enemy"))
                if not defender.alive:
                    defender.attack, defender.blocking = None, False
                    self._bus.publish(EntityDied(entity.id))

    def _touches(self, source: int, target: int, bones: tuple[str, ...]) -> bool:
        targets = tuple((target, bone) for bone in bones)
        return any(self._contacts.overlaps((source, bone), targets) for bone in WEAPON_BONES)

    def _hit(self, source: int, target: int, attacker: Fighter, defender: Fighter,
             source_transform: Transform, target_transform: Transform, blocked: bool) -> None:
        attack = attacker.attack
        assert attack is not None
        kind = attack.definition.kind
        backstab = kind == AttackKind.BACKSTAB and not defender.backstab_immune and behind(source_transform, target_transform)
        riposte = kind == AttackKind.RIPOSTE and defender.riposte_steps > 0
        blocked = blocked and not (backstab or riposte)
        result = resolve_damage(
            attack.definition.packet, attacker.stats, attacker.weapon, defender.stats, defender.resist,
            is_blocked=blocked, is_backstab=backstab, is_riposte=riposte,
        )
        if result.guard_cost > defender.stamina:
            blocked = False
            defender.stamina = 0
            defender.interrupt(STAGGER_STEPS_HEAVY)
            self._bus.publish(StaggerTriggered(target, True))
            result = resolve_damage(attack.definition.packet, attacker.stats, attacker.weapon,
                                    defender.stats, defender.resist)
        elif blocked:
            defender.spend(result.guard_cost)
        damage = result.hp
        if blocked:
            damage = damage / .22 * attack.definition.block_damage_fraction
        old_hp = defender.hp
        defender.hp = max(0.0, defender.hp - damage)
        defender.hit_steps = HIT_REACT_STEPS
        defender.poise -= result.poise
        if defender.poise <= 0 and defender.alive and not defender.stagger_cooldown_steps:
            steps = STAGGER_STEPS_HEAVY if kind == AttackKind.HEAVY else STAGGER_STEPS_LIGHT
            defender.interrupt(steps)
            self._bus.publish(StaggerTriggered(target, False))
        if riposte:
            defender.riposte_hits_remaining = max(0, defender.riposte_hits_remaining - 1)
            if defender.riposte_hits_remaining == 0:
                defender.riposte_steps = 0
        elif backstab:
            defender.riposte_steps = 0
        if attack.definition.knockdown_steps and defender.alive:
            defender.interrupt(attack.definition.knockdown_steps)
            defender.knockdown_steps = attack.definition.knockdown_steps
            self._bus.publish(StaggerTriggered(target, False))
        if attack.definition.status is not None and not blocked:
            effect, amount = attack.definition.status
            defender.hp = max(0, defender.hp - defender.status.apply(effect, amount, defender.max_hp))
        self._bus.publish(DamageDealt(source, target, damage, defender.hp, blocked,
                                     "riposte" if riposte else "backstab" if backstab else "",
                                     "fire" if attack.definition.packet.fire > 0 else "magic" if attack.definition.packet.magic > 0 else "physical",
                                     attack.definition.kind.value))
        self._bus.publish(HPChangedEvent(target, old_hp, defender.hp, defender.max_hp,
                                         "player" if attacker.team == 0 else "enemy"))
        if not defender.alive:
            defender.attack = None
            defender.blocking = False
            self._bus.publish(EntityDied(target))


def defender_front(defender: Transform, attacker: Transform) -> bool:
    toward = (attacker.position - defender.position).flat().normalized()
    return toward.dot(defender.forward()) > .1


class DeathSystem:
    """Retira corpos mortos do mundo físico após a resolução do combate."""

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._hp: dict[int, float] = {}
        if bus is not None:
            bus.subscribe(HPChangedEvent, self._track_hp)

    def _track_hp(self, event: HPChangedEvent) -> None:
        self._hp[event.entity_id] = event.new_hp

    def reset_health(self, world: World) -> None:
        self._hp = {entity.id: fighter.hp for entity, (fighter,) in world.query(Fighter)}

    def tick(self, world: World) -> None:
        for entity, (fighter,) in world.query(Fighter):
            previous = self._hp.get(entity.id, fighter.hp)
            if self._bus is not None and previous != fighter.hp:
                self._bus.publish(HPChangedEvent(entity.id, previous, fighter.hp, fighter.max_hp,
                                                 "self" if fighter.hp > previous else "dot"))
            self._hp[entity.id] = fighter.hp
        for _, (fighter, body) in world.query(Fighter, BodyRef):
            body.body.set_active(fighter.alive)
