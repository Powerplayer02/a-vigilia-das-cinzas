"""Inventário em grid, categorias e comparação com a arma equipada."""

from vigilia.core.protocols import IInventoryQuery, IUIActions
from vigilia.core.views import ItemCategory, UICommand, UICommandKind
from vigilia.ui.widgets import Label, Button, Grid, Tooltip, Panel, Sprite
from vigilia.ui.text_render import TITLE, SECONDARY, GOLD, MUTED


class InventoryUI:
    def __init__(self, backend, query: IInventoryQuery, actions: IUIActions, *, equipment=False):
        self.backend, self.query, self.actions = backend, query, actions
        self.category = ItemCategory.WEAPON if equipment else ItemCategory.ALL
        self.categories = tuple(ItemCategory)
        self.root = Panel(backend, "menu.inventory", (410, 138, 672, 460), parent="menu", color=(0, 0, 0, 0))
        Label(backend, "menu.inventory.title", backend.t("inventory.equipment" if equipment else "inventory.title"),
              (14, 0, 620, 38), parent=self.root.key, size=TITLE, color=GOLD)
        self.category_label = Label(backend, "menu.inventory.category", "", (14, 48, 620, 24), parent=self.root.key, size=SECONDARY)
        self.list_panel = None
        self.detail_panel = None
        self.message = Label(backend, "menu.inventory.message", "", (14, 400, 634, 48), parent=self.root.key, size=SECONDARY, color=GOLD)
        Button(backend, "menu.inventory.prev", "<", (14, 80, 36, 32), lambda: self.change_category(-1), parent=self.root.key, size=SECONDARY)
        Button(backend, "menu.inventory.next", ">", (56, 80, 36, 32), lambda: self.change_category(1), parent=self.root.key, size=SECONDARY)
        Label(backend, "menu.inventory.tabs_hint", backend.t("inventory.tabs"), (110, 84, 500, 24), parent=self.root.key, size=SECONDARY, color=MUTED)
        self.refresh()

    def refresh(self):
        if self.list_panel is not None:
            self.list_panel.destroy()
        self.list_panel = Panel(self.backend, "menu.inventory.list", (14, 128, 332, 264), parent=self.root.key, color=(0, 0, 0, 0))
        self.items = self.query.items_by_category(self.category)
        self.category_label.set(self.backend.t("inventory.category", category=self.backend.t("category." + self.category.value).upper(), count=len(self.items)))
        buttons = []
        for index, item in enumerate(self.items):
            name = item.name + ("  [E]" if item.equipped else f"  ×{item.quantity}")
            buttons.append(Button(self.backend, f"menu.inventory.item.{item.id}", name,
                ((index % 2) * 166, (index // 2) * 82, 156, 72),
                lambda index=index: self.select(index), parent=self.list_panel.key, size=SECONDARY, icon=""))
            Sprite(self.backend, f"menu.inventory.icon.{item.id}", self.icon(item),
                ((index % 2)*166+126, (index//2)*82+44, 24, 24), parent=self.list_panel.key)
        self.grid = Grid(buttons, 2)
        if not self.items:
            Label(self.backend, "menu.inventory.empty", self.backend.t("inventory.empty"), (0, 10, 320, 80), parent=self.list_panel.key, size=SECONDARY, color=MUTED)
        self.select(0)

    def select(self, index):
        self.grid.select(index)
        if self.detail_panel is not None:
            self.detail_panel.destroy()
        self.detail_panel = Panel(self.backend, "menu.inventory.detail", (360, 128, 290, 264), parent=self.root.key)
        if not self.items:
            return
        item = self.items[self.grid.index]
        current = self.query.equipped().weapon
        Sprite(self.backend, "menu.inventory.detail_icon", self.icon(item), (14, 12, 42, 42), parent=self.detail_panel.key)
        Label(self.backend, "menu.inventory.name", item.name, (64, 10, 212, 54), parent=self.detail_panel.key, color=GOLD)
        if item.category == ItemCategory.WEAPON:
            text = self.backend.t("inventory.compare", damage=f"{item.damage:.1f}", delta=f"{item.damage-current.damage:+.1f}",
                current=f"{current.damage:.1f}", scaling=item.scaling, requirements=item.requirements, weight=f"{item.weight:.1f}")
        else:
            text = self.backend.t("inventory.quantity", quantity=item.quantity, weight=f"{item.weight:.1f}") + ("\n" + self.backend.t("inventory.gear_equipped") if item.equipped else "")
        Label(self.backend, "menu.inventory.compare", text, (14, 70, 262, 108), parent=self.detail_panel.key, size=SECONDARY)
        Tooltip(self.backend, "menu.inventory.description", item.description, (14, 180, 262, 44), parent=self.detail_panel.key, size=SECONDARY, color=MUTED)
        if item.category == ItemCategory.WEAPON:
            button = Button(self.backend, "menu.inventory.equip", self.backend.t("inventory.equipped" if item.equipped else "inventory.equip"),
                            (14, 220, 262, 34), self.confirm, parent=self.detail_panel.key, size=SECONDARY)
            button.enable(item.equippable and not item.equipped)

    def move(self, dx=0, dy=0):
        self.select(self.grid.index + dx + dy * 2)

    @staticmethod
    def icon(item):
        weapons = {"longsword":"sword", "axe":"axe", "katana":"katana", "staff":"staff", "mace":"mace"}
        if item.category == ItemCategory.WEAPON:
            return weapons.get(item.id, "sword")
        if item.category == ItemCategory.GEAR:
            return "shield" if "shield" in item.id else "ring" if "ring" in item.id else "armor"
        return {"consumable":"flask", "material":"shard", "magic":"spell"}.get(item.category.value, "shard")

    def change_category(self, delta):
        self.category = self.categories[(self.categories.index(self.category) + delta) % len(self.categories)]
        self.refresh()

    def confirm(self):
        if not self.items:
            return
        item = self.items[self.grid.index]
        if item.category != ItemCategory.WEAPON:
            self.message.set(item.description)
            return
        index = self.grid.index
        self.message.set(self.actions.execute(UICommand(UICommandKind.EQUIP, item.id)))
        self.refresh()
        self.select(index)
