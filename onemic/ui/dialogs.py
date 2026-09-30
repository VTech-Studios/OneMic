from __future__ import annotations

from collections.abc import Collection, Sequence
from enum import Enum
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..domain.profile import MicProfile
from ..domain.sources import AudioSource, SourceKind


class CloseChoice(Enum):
    KEEP_LIVE = "keep"
    STOP = "stop"
    CANCEL = "cancel"


def ask_on_close(parent: QWidget, mic_name: str) -> CloseChoice:
    """Ask what should happen to a live mic when the window closes.

    Closing by accident mid-call should never silence the call, so the
    question is asked every time rather than assumed.

    @param parent: the window being closed.
    @param mic_name: the live mic's name.
    @return: the user's choice, CANCEL if the prompt was dismissed.
    """
    box = QMessageBox(parent)
    box.setWindowTitle("Close OneMic")
    box.setIcon(QMessageBox.Icon.Question)
    box.setText(f"{mic_name} is live.")
    box.setInformativeText(
        "Keep it live to leave it running for your call. Its levels stay as they are, and "
        "anything that appears later is linked next time you open OneMic."
    )
    keep = box.addButton("Keep live", QMessageBox.ButtonRole.AcceptRole)
    stop = box.addButton("Stop mic", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton(QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(keep)
    box.exec()
    clicked = box.clickedButton()
    if clicked is keep:
        return CloseChoice.KEEP_LIVE
    return CloseChoice.STOP if clicked is stop else CloseChoice.CANCEL


def ask_for_name(parent: QWidget, title: str, current: str = "") -> str | None:
    """Ask for a mic name.

    @param parent: the dialog's owner, which keeps it above the window.
    @param title: what the name is for.
    @param current: text to start with.
    @return: the text entered, or None if cancelled.
    """
    text, accepted = QInputDialog.getText(parent, title, "Name, as call apps will list it:", text=current)
    return text if accepted else None


class SourcePicker(QDialog):
    """Lets the user choose a signal to add, grouped by kind.

    Sources already on the mic are shown but disabled, so the list always
    matches the patchbay, while adding one twice is impossible.
    """

    def __init__(self, sources: Sequence[AudioSource], used: Collection[str], parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add input")
        self.resize(420, 420)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._fill(sources, used)
        self._build_layout()

    def chosen(self) -> AudioSource | None:
        """Report the selected source once the dialog is accepted.

        @return: the source, or None if a group heading or nothing is selected.
        """
        item = self._tree.currentItem()
        data = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, AudioSource) else None

    def _fill(self, sources: Sequence[AudioSource], used: Collection[str]) -> None:
        groups: dict[SourceKind, QTreeWidgetItem] = {}
        for source in sources:
            if source.kind not in groups:
                groups[source.kind] = QTreeWidgetItem(self._tree, [source.kind.value])
                groups[source.kind].setFlags(Qt.ItemFlag.ItemIsEnabled)
            item = QTreeWidgetItem(groups[source.kind], [source.description])
            item.setData(0, Qt.ItemDataRole.UserRole, source)
            item.setToolTip(0, source.name)
            if source.name in used:
                item.setDisabled(True)
        self._tree.expandAll()

    def _build_layout(self) -> None:
        column = QVBoxLayout(self)
        column.addWidget(self._tree)
        column.addWidget(self._buttons)
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        self._tree.itemDoubleClicked.connect(lambda *_: self.accept() if self.chosen() else None)


class MicActions(Protocol):
    """What the mic manager asks for. Each returns an error message, or None on success."""

    def create_mic(self, name: str) -> str | None: ...

    def duplicate_mic(self, slug: str, name: str) -> str | None: ...

    def rename_mic(self, slug: str, name: str) -> str | None: ...

    def delete_mic(self, slug: str) -> str | None: ...

    def list_mics(self) -> Sequence[MicProfile]: ...


class MicManager(QDialog):
    """Create, copy, rename and delete saved mics.

    The dialog only gathers names and confirmations. Every change goes
    through MicActions, so the rules live in one place.
    """

    def __init__(self, actions: MicActions, parent: QWidget) -> None:
        super().__init__(parent)
        self._actions = actions
        self.setWindowTitle("Manage mics")
        self.resize(360, 300)
        self._list = QListWidget()
        self._build_layout()
        self._refresh()

    def _selected_slug(self) -> str | None:
        item = self._list.currentItem()
        return str(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def _selected_name(self) -> str:
        item = self._list.currentItem()
        return item.text() if item else ""

    def _refresh(self) -> None:
        """Reload the list, keeping the selected row.

        Renaming keeps a mic's position, so holding the row keeps the same
        mic selected, and after a deletion the neighbouring mic is selected.
        """
        row = max(self._list.currentRow(), 0)
        self._list.clear()
        for profile in self._actions.list_mics():
            item = QListWidgetItem(profile.name)
            item.setData(Qt.ItemDataRole.UserRole, profile.slug)
            self._list.addItem(item)
        self._list.setCurrentRow(min(row, self._list.count() - 1))

    def _report(self, error: str | None) -> bool:
        if error:
            QMessageBox.warning(self, "OneMic", error)
        return error is None

    def _create(self) -> None:
        name = ask_for_name(self, "New mic")
        if name is not None and self._report(self._actions.create_mic(name)):
            self._refresh()

    def _duplicate(self) -> None:
        slug = self._selected_slug()
        name = ask_for_name(self, "Copy mic", f"{self._selected_name()} copy")
        if slug and name is not None and self._report(self._actions.duplicate_mic(slug, name)):
            self._refresh()

    def _rename(self) -> None:
        slug = self._selected_slug()
        name = ask_for_name(self, "Rename mic", self._selected_name())
        if slug and name is not None and self._report(self._actions.rename_mic(slug, name)):
            self._refresh()

    def _delete(self) -> None:
        slug = self._selected_slug()
        if not slug:
            return
        answer = QMessageBox.question(self, "Delete mic", f"Delete {self._selected_name()}?")
        if answer == QMessageBox.StandardButton.Yes and self._report(self._actions.delete_mic(slug)):
            self._refresh()

    def _build_layout(self) -> None:
        buttons = QVBoxLayout()
        for text, handler in (
            ("New…", self._create),
            ("Copy…", self._duplicate),
            ("Rename…", self._rename),
            ("Delete", self._delete),
        ):
            button = QPushButton(text)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        buttons.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        row = QHBoxLayout(self)
        row.addWidget(self._list, 1)
        row.addLayout(buttons)


class Dialogs(Protocol):
    """The questions the controller asks, so tests can answer them without real dialogs."""

    def ask_on_close(self, mic_name: str) -> CloseChoice: ...

    def pick_source(self, sources: Sequence[AudioSource], used: Collection[str]) -> AudioSource | None: ...

    def manage_mics(self, actions: MicActions) -> None: ...


class QtDialogs:
    """Real dialogs, owned by the main window so they open above it."""

    def __init__(self, parent: QWidget) -> None:
        self._parent = parent

    def ask_on_close(self, mic_name: str) -> CloseChoice:
        """Ask what should happen to a live mic when the window closes.

        @param mic_name: the live mic's name.
        @return: the user's choice.
        """
        return ask_on_close(self._parent, mic_name)

    def pick_source(self, sources: Sequence[AudioSource], used: Collection[str]) -> AudioSource | None:
        """Let the user choose a signal to add.

        @param sources: every source in the graph.
        @param used: names of sources already on the mic.
        @return: the chosen source, or None if cancelled.
        """
        picker = SourcePicker(sources, used, self._parent)
        return picker.chosen() if picker.exec() == QDialog.DialogCode.Accepted else None

    def manage_mics(self, actions: MicActions) -> None:
        """Open the mic manager until the user closes it.

        @param actions: what the manager may do.
        """
        MicManager(actions, self._parent).exec()
