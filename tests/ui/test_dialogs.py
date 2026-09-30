from collections.abc import Iterator, Sequence

import pytest
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem
from pytestqt.qtbot import QtBot

from onemic.domain.profile import MicProfile
from onemic.domain.sources import AudioSource, SourceKind
from onemic.ui import dialogs
from onemic.ui.dialogs import MicManager, SourcePicker

SOURCES = [
    AudioSource("mic2", "Scarlett Mic 2", SourceKind.MICROPHONE),
    AudioSource("REAPER", "REAPER", SourceKind.APPLICATION),
]


def group(tree: QTreeWidget, index: int) -> QTreeWidgetItem:
    item = tree.topLevelItem(index)
    assert item is not None
    return item


def first_child(item: QTreeWidgetItem) -> QTreeWidgetItem:
    child = item.child(0)
    assert child is not None
    return child


def test_the_picker_groups_sources_and_disables_used_ones(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    qtbot.addWidget(parent)
    picker = SourcePicker(SOURCES, used={"mic2"}, parent=parent)

    tree = picker._tree
    groups = [group(tree, index) for index in range(tree.topLevelItemCount())]
    assert [item.text(0) for item in groups] == [SourceKind.MICROPHONE.value, SourceKind.APPLICATION.value]
    assert first_child(groups[0]).isDisabled()
    assert picker.chosen() is None

    tree.setCurrentItem(first_child(groups[1]))
    assert picker.chosen() == SOURCES[1]


class FakeActions:
    def __init__(self) -> None:
        self.mics = [MicProfile("Lesson"), MicProfile("Stream")]
        self.calls: list[tuple[str, ...]] = []
        self.error: str | None = None

    def list_mics(self) -> Sequence[MicProfile]:
        return self.mics

    def create_mic(self, name: str) -> str | None:
        self.calls.append(("create", name))
        return self.error

    def duplicate_mic(self, slug: str, name: str) -> str | None:
        self.calls.append(("duplicate", slug, name))
        return self.error

    def rename_mic(self, slug: str, name: str) -> str | None:
        self.calls.append(("rename", slug, name))
        return self.error

    def delete_mic(self, slug: str) -> str | None:
        self.calls.append(("delete", slug))
        return self.error


@pytest.fixture
def manager(qtbot: QtBot, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[MicManager, FakeActions]]:
    from PySide6.QtWidgets import QWidget

    monkeypatch.setattr(dialogs, "ask_for_name", lambda parent, title, current="": "Typed")
    parent = QWidget()
    qtbot.addWidget(parent)
    actions = FakeActions()
    yield MicManager(actions, parent), actions
    parent.close()


def test_the_manager_lists_mics_and_selects_the_first(manager: tuple[MicManager, FakeActions]) -> None:
    dialog, _ = manager

    assert dialog._list.count() == 2
    assert dialog._selected_slug() == "lesson"


def test_manager_actions_use_the_selected_mic(manager: tuple[MicManager, FakeActions]) -> None:
    dialog, actions = manager
    dialog._list.setCurrentRow(1)

    dialog._create()
    dialog._duplicate()
    dialog._rename()

    assert actions.calls == [
        ("create", "Typed"),
        ("duplicate", "stream", "Typed"),
        ("rename", "stream", "Typed"),
    ]


def test_deleting_asks_first(
    manager: tuple[MicManager, FakeActions], monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog, actions = manager
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)
    dialog._delete()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.StandardButton.Yes)
    dialog._delete()

    assert actions.calls == [("delete", "lesson")]


def test_errors_from_actions_are_shown(
    manager: tuple[MicManager, FakeActions], monkeypatch: pytest.MonkeyPatch
) -> None:
    from PySide6.QtWidgets import QMessageBox

    dialog, actions = manager
    shown: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda parent, title, text: shown.append(text))
    actions.error = "A mic called Typed already exists."

    dialog._create()

    assert shown == ["A mic called Typed already exists."]
