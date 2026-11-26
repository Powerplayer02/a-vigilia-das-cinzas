"""Bounded agent input sequences using rendered cues and own-character telemetry.

Rendered weapon orientation distinguishes a held lateral sweep from a narrow
strike. No enemy FSM, attack definition, timers or future decisions are inspected.
This is instrumented agent QA, not a human difficulty assessment.
"""
import math
from vigilia.core.mathx import Transform, Vec3

# Input policy memory survives bounded blocks, but excludes menu/pause time.
if 'observed' not in globals():
    observed = {'elapsed': 0., 'last_call': None, 'wave_at': None, 'ring': False}
if 'counter' not in globals():
    counter = {'gold': False, 'ready_at': 0., 'done': False}


class EncounterInputs:
    reaction_seconds = .2

    def __init__(self):
        self.warning_at = None
        self.defense = None
        self.pulse_until = 0.
        self.recovering = False
        self.last_keys = set()
        self.next_target_cycle = 0.
        self.next_common_pulse = 0.
        self.gold_at = None
        self.parry_tries = set()
        self.pulse_key = 'mouse1'
        self.escape_heading = None
        self.roll_until = 0.
        self.roll_keys = set()

    def choose(self, game, now):
        keys = self.roll_keys if now < self.roll_until else self._choose(game, now)
        self.last_keys = keys
        return keys

    def _roll(self, keys, now):
        # Keep direction and key together through at least one 60 Hz step.
        return self._pulse(keys | {'space'}, now)

    def _pulse(self, keys, now):
        self.roll_until, self.roll_keys = now + .07, keys
        return self.roll_keys

    def _choose(self, game, now):
        previous = observed['last_call']
        if previous is not None and 0 < now - previous < .1:
            observed['elapsed'] += now - previous
        observed['last_call'] = now
        clock = observed['elapsed']
        target = game._target
        if target is None or game._fighter.hp <= 0:
            return set()
        key = game._actor_keys().get(target.id, '')
        if key.startswith('dummy_'):
            if now >= self.next_target_cycle:
                self.next_target_cycle = now + .25
                return {'x'}
            return set()
        pose = game._world.get(target, Transform)
        if pose is None:
            return set()
        position = game._transform.position
        delta = (pose.position - position).flat()
        distance = delta.length()
        own = game._fighter
        attack = own.attack
        remaining = max(0, attack.definition.duration - attack.age) / 60 if attack else 0.
        forward, right = game._camera.axes(position)
        def direction_keys(heading, run=False):
            heading = heading.flat().normalized()
            keys = {'shift'} if run else set()
            x, y = heading.dot(right), heading.dot(forward)
            if abs(x) > .38:keys.add('d' if x > 0 else 'a')
            if abs(y) > .38:keys.add('w' if y > 0 else 's')
            return keys
        def free(direction, length=.8):
            end = position + direction.normalized() * length
            return game._physics.sweep_sphere(position, end, .33) is None
        orbit = {'a'} if free(right * -1) else {'d'}
        def approach():
            run = {'shift'} if own.stamina > 70 and not self.recovering else set()
            if free(forward):return {'w'} | run
            if free(forward - right):return {'w', 'a'} | run
            if free(forward + right):return {'w', 'd'} | run
            if free(right):return {'d'}
            if free(right * -1):return {'a'}
            return {'s'}
        vent = getattr(game._renderer, '_vent_marker', None)
        if key == 'last_ember_custodian' and vent is not None and not vent.is_hidden():
            point = vent.get_pos()
            away = (position - Vec3(point.x, point.y, point.z)).flat()
            if away.length() < 2.9:
                if away.length() < .05:away = right
                return direction_keys(away, own.stamina > 20)
        ring = game._renderer._boss_ring
        warning = not ring.is_hidden()
        if warning:
            fresh_warning = not observed['ring']
            if fresh_warning:
                observed['wave_at'] = clock
            observed['ring'] = True
            if self.warning_at is None:
                self.warning_at = now - (clock - observed['wave_at'])
                # A running escape needs time to get past the growing circle.
                # Committed actions or a nearby arena wall favor normal guard.
                end = position - forward * 7.0
                hit = game._physics.sweep_sphere(position,end,.33)
                room = hit is None or hit.distance > max(0,6.8-distance)
                inward_hit = game._physics.sweep_sphere(position,position + forward * 8.0,.33)
                inward_room = inward_hit is None or inward_hit.distance > 6.4 + distance
                self.defense = ('escape' if room else 'through' if inward_room else 'guard') if own.stamina > 27 else 'guard'
                self.escape_heading = forward * (-1 if self.defense == 'escape' else 1)
                if not fresh_warning and 'escape_heading' in observed:
                    self.defense = observed['defense']
                    self.escape_heading = observed['escape_heading']
                observed.update(defense=self.defense, escape_heading=self.escape_heading)
            if clock - observed['wave_at'] < self.reaction_seconds:
                return self.last_keys
            if self.defense == 'guard':return {'control'}
            return direction_keys(self.escape_heading, True)
        self.warning_at, self.defense = None, None
        if observed['ring']:
            counter.update(gold=False, ready_at=clock + .15, done=False)
        observed['ring'] = False
        root = game._renderer._dummies.get(target.id)
        if root is None and target.id in game._renderer._enemies:
            root = game._renderer._enemies[target.id][0]
        gold = False
        if root is not None:
            tint = root.get_color_scale()
            gold = tint.y > 1.1 and tint.x > 1.5
            neutral = abs(tint.x - 1) < .05 and abs(tint.y - 1) < .05
        else:
            neutral = False
        wide = False
        phase_one = 'Fase 1' in game._renderer._boss_name.getText()
        gear = game._renderer._combat_gear.get(target.id)
        if root is not None and gear is not None:
            axis = gear[0].get_quat(game._renderer.root).get_forward()
            frame = root.get_quat(game._renderer.root)
            wide = axis.dot(frame.get_right()) < -.85 and abs(axis.dot(frame.get_forward())) < .4
            # A drawn damage flash can cover the gold tint while the held
            # weapon still visibly signals the lateral preparation.
            gold |= wide and tint.x > 1.5 and tint.y < 1
        if gold:
            if not counter['gold']:
                counter['gold_at'], counter['rolled'] = clock, False
                counter['parried'] = False
            counter.update(gold=True, done=False)
            counter['wide'] = wide
        elif neutral and counter['gold']:
            counter.update(gold=False, ready_at=clock + .2)
        if key in ('warden_of_the_forge', 'abbess_of_the_tide', 'last_ember_custodian'):
            # Parry at shield contact distance, then use the normal light-key
            # critical selected by the production controller. The only success
            # cue read is the message actually displayed in the HUD.
            message = getattr(game, '_context_feedback', '')
            success = message.startswith('PARRY')
            if success and not counter.get('parry_message', False):
                counter['critical_until'] = clock + (1.1 if phase_one else 3.6)
                counter['last_success'] = clock
            counter['parry_message'] = success
            if game._player.dodging or attack is not None:
                return set()
            ready = game._commands.state.value in ('ready', 'block')
            if clock < counter.get('critical_until', 0):
                if distance > 1.15:return {'w', 'shift'} if own.stamina >= 45 else set()
                reserve = 24 if phase_one else 60
                if ready and own.stamina >= reserve:return self._pulse({'mouse1'}, now)
                return set()
            lateral_active = (gold and wide) or (counter.get('wide', False) and clock < counter['ready_at'])
            desired = 4.55 if lateral_active else 3.75
            threshold = .40 if wide else .67 if key == 'abbess_of_the_tide' else .87
            if (gold and ready and own.stamina >= 70 and not counter.get('parried', False)
                    and clock - counter.get('last_success', -100) > 3.1
                    and clock - counter.get('gold_at', clock) >= threshold and distance >= desired - .25):
                counter['parried'] = True
                return self._pulse({'r'}, now)
            if (gold and ready and own.stamina >= 24 and distance < desired - .8
                    and not counter.get('rolled', False) and clock - counter.get('gold_at', clock) >= .3):
                counter['rolled'] = True
                return self._roll({'s'}, now)
            if distance < desired - .05:return {'s', 'shift'} if own.stamina > 10 else {'s'}
            if distance > desired + .05:return {'w'} if free(forward) else approach()
            return set()
        centers = {'abbess_of_the_tide': Vec3(120, 27), 'last_ember_custodian': Vec3(240, 26)}
        center = centers.get(key)
        lure = center is not None and (pose.position.y < center.y - 4 or
            pose.position.y > center.y + 7 or abs(pose.position.x - center.x) > 8)
        if lure:
            # Walk and strafe at the open arena center to draw a wall-hugging
            # opponent away from scenery. Only observed positions are used.
            goal = center + Vec3(2 * math.sin(clock * 1.7), 0)
            keys = direction_keys(goal - position)
            if (gold and wide and not counter.get('rolled', False) and clock - counter.get('gold_at', clock) >= .35
                    and not game._player.dodging and own.stamina >= 24 and distance < 3
                    and game._commands.state.value in ('ready', 'block')):
                counter['rolled'] = True
                return self._roll(keys, now)
            return keys
        if gold:
            if attack is None:
                if (wide and not phase_one and not counter.get('rolled', False) and clock - counter.get('gold_at', clock) >= .35
                        and not game._player.dodging and own.stamina >= 24
                        and game._commands.state.value in ('ready', 'block') and distance < 3):
                    counter['rolled'] = True
                    return self._roll({'w'} if free(forward, 2.8) else orbit, now)
                return orbit
        if now < self.pulse_until:
            return orbit | {self.pulse_key}
        if game._player.dodging:
            return orbit
        if attack is not None:
            if '.enemy.' in key and now >= self.next_common_pulse:
                self.next_common_pulse = now + .25
                return orbit | {'mouse1'}
            # Separate light strikes leave an opening to respond to a warning.
            return orbit
        if game._commands.state.value not in ('ready', 'block'):
            return orbit
        if own.stamina < 30:
            self.recovering = True
        if self.recovering and own.stamina >= 65:
            self.recovering = False
        if distance > 1.15:
            return approach()
        if distance < .45:
            return {'s'} | orbit
        is_common = '.enemy.' in key
        can_counter = neutral and not counter['gold'] and not counter['done'] and clock >= counter['ready_at']
        first_phase = 'Fase 1' in game._renderer._boss_name.getText()
        idle_opening = neutral and not counter['gold'] and first_phase
        if not self.recovering and not gold and (is_common or can_counter or idle_opening):
            self.pulse_key = 'mouse1' if is_common or not can_counter or own.stamina < 100 else 'mouse3'
            counter['done'] = True
            self.pulse_until = now + .055
            return orbit | {self.pulse_key}
        return orbit
