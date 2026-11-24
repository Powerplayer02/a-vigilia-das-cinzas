"""Foco, ativação, limites das barras e atualização incremental."""

from ui_fakes import BackendFake
from vigilia.ui.widgets import Panel, Label, Button, Bar, Grid


def test_bar_clamps_fraction_and_skips_unchanged_native_updates():
    backend = BackendFake()
    bar = Bar(backend, "hp", (0, 0, 200, 10), (1, 0, 0, 1))
    bar.set(500, 140)
    bar.set(140, 140)
    assert backend.nodes["hp.fill"]["fraction"] == 1
    assert len(backend.updates) == 1
    bar.set(-10, 140)
    assert backend.nodes["hp.fill"]["fraction"] == 0
    bar.set(10, 0)
    assert len(backend.updates) == 2


def test_grid_focus_and_disabled_button_prevent_actions():
    backend, calls = BackendFake(), []
    buttons = [Button(backend, str(i), str(i), (0, 0, 10, 10), lambda i=i: calls.append(i)) for i in range(4)]
    grid = Grid(buttons, 2)
    grid.move(dy=1)
    assert grid.index == 2 and buttons[2].focused and not buttons[0].focused
    buttons[2].enable(False)
    grid.confirm()
    assert not calls
    grid.move(dx=1)
    grid.confirm()
    assert calls == [3]


def test_label_only_updates_changed_text_and_parent_destroy_removes_children():
    backend = BackendFake()
    panel = Panel(backend, "parent", (0, 0, 10, 10))
    label = Label(backend, "child", "A", (0, 0, 10, 10), parent=panel.key)
    label.set("A")
    assert not backend.updates
    label.set("B")
    assert len(backend.updates) == 1
    panel.destroy()
    assert not backend.nodes
