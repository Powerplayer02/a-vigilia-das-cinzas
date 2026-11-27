"""Rascunho de criação só vira personagem após validação do domínio."""

import json

from vigilia.core.views import UICommand, UICommandKind as C
from vigilia.ui.main_menu import sheet
from vigilia.ui.widgets import Label, Button, Grid, TextInput, FOCUS
from vigilia.ui.text_render import GOLD, MUTED, SECONDARY


class CharacterCreation:
    def __init__(self, backend, query, actions, *, slot=None):
        self.backend, self.query, self.actions = backend, query, actions
        self.classes, self.slots = query.character_classes(), query.slots()
        self.class_index, self.allocation, self.name = 0, {}, "Vesper"
        self.locked_slot = slot is not None
        self.slot = slot if slot is not None else next((row.slot for row in self.slots if not row.occupied), 1)
        self.root = None
        self.render()

    @property
    def remaining(self):
        return 10 - sum(self.allocation.values())

    def render(self, message="", focus=0):
        if self.root is not None:
            self.name = self.entry.value
            self.root.destroy()
        b = self.backend
        self.root = sheet(b, "character.title")
        Label(b, "front.name.label", b.t("character.name"), (404, 118, 200, 26), parent="front", size=SECONDARY)
        self.entry = TextInput(b, "front.name", self.name, (402, 146, 300, 42), parent="front")
        self.buttons = [Button(b, f"front.class.{profile.id}", profile.name, (164, 146 + i * 66, 208, 54),
            lambda index=i: self.select_class(index), parent="front",
            icon={"knight":"shield","warrior":"axe","assassin":"katana","mage":"staff","cleric":"healing"}.get(profile.id,"helm")) for i, profile in enumerate(self.classes)]
        self.buttons.append(Button(b, "front.name.edit", b.t("character.name_edit"), (744, 146, 352, 42), self.entry.focus, parent="front", size=SECONDARY))
        profile = self.classes[self.class_index]
        Label(b, "front.points", b.t("character.points", points=self.remaining), (404, 202, 690, 30), parent="front", color=GOLD)
        for i, stat in enumerate(profile.attributes):
            value = stat.value + self.allocation.get(stat.id, 0)
            self.buttons.append(Button(b, f"front.stat.{stat.id}", f"{stat.name}    {value}", (404, 246 + i * 39, 300, 34),
                lambda stat=stat.id: self.adjust(stat, 1), parent="front", size=SECONDARY))
            Button(b, f"front.minus.{stat.id}", "-", (710, 246 + i * 39, 32, 34),
                lambda stat=stat.id: self.adjust(stat, -1), parent="front", size=SECONDARY)
            Button(b, f"front.plus.{stat.id}", "+", (748, 246 + i * 39, 32, 34),
                lambda stat=stat.id: self.adjust(stat, 1), parent="front", size=SECONDARY)
        Label(b, "front.class.description", profile.description, (816, 248, 280, 94), parent="front", size=SECONDARY, color=MUTED)
        Label(b, "front.weapon", b.t("character.weapon", weapon=profile.weapon), (816, 350, 280, 52), parent="front", size=SECONDARY, color=GOLD)
        Label(b, "front.gear", b.t("character.gear", gear=profile.gear), (816, 410, 280, 60), parent="front", size=SECONDARY)
        Label(b, "front.spells", b.t("character.spells", spells=profile.spells or b.t("character.no_spells")),
              (816, 484, 280, 58), parent="front", size=SECONDARY, color=GOLD)
        for i, row in enumerate(self.slots):
            button = Button(b, f"front.destination.{row.slot}", b.t("character.slot_short", slot=row.slot,
                occupied=b.t("character.occupied") if row.occupied else ""), (164 + i * 310, 552, 292, 36),
                lambda slot=row.slot: self.select_slot(slot), parent="front", size=SECONDARY)
            button.enable(not row.occupied and (not self.locked_slot or row.slot == self.slot))
            self.buttons.append(button)
        self.message = Label(b, "front.message", message or b.t("character.hint"), (164, 600, 630, 38), parent="front", size=SECONDARY, color=GOLD)
        self.buttons.append(Button(b, "front.start", b.t("character.start"), (816, 600, 280, 38), self.create, parent="front", size=SECONDARY))
        self.grid = Grid(self.buttons)
        self.grid.select(focus)
        self.backend.color("front.class." + profile.id, FOCUS)
        self.backend.color(f"front.destination.{self.slot}", FOCUS)

    def select_class(self, index):
        self.class_index = index % len(self.classes)
        self.allocation = {}
        self.render(focus=self.class_index)

    def select_slot(self, slot):
        if self.locked_slot and slot != self.slot:
            return
        self.slot = slot
        self.render(focus=12 + slot)

    def adjust(self, stat, delta):
        value = self.allocation.get(stat, 0)
        self.allocation[stat] = value + max(-value, min(delta, self.remaining))
        index = next(i for i, item in enumerate(self.classes[self.class_index].attributes) if item.id == stat)
        self.render(focus=6 + index)

    def change_category(self, delta):
        self.select_class(self.class_index + delta)

    def move(self, dx=0, dy=0):
        if dx and 6 <= self.grid.index < 13:
            self.adjust(self.classes[self.class_index].attributes[self.grid.index - 6].id, dx)
        else:
            self.grid.move(dx, dy)

    def confirm(self):
        self.grid.confirm()

    def cancel_text(self):
        self.backend.focus_text(self.entry.key, False)

    def create(self):
        if self.remaining:
            self.message.set(self.backend.t("character.allocate_ten"))
            return
        payload = json.dumps(dict(slot=self.slot, name=self.entry.value, class_id=self.classes[self.class_index].id, allocation=self.allocation))
        message = self.actions.execute(UICommand(C.CREATE_CHARACTER, payload))
        if message:
            self.message.set(message)
