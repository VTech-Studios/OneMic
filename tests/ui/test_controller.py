from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass, field

import pytest
from pytestqt.qtbot import QtBot

from onemic.domain.levels import LevelThresholds
from onemic.domain.naming import NodeNames
from onemic.domain.profile import InputSettings, MicProfile
from onemic.domain.sources import AudioSource, SourceKind
from onemic.domain.window import WindowState
from onemic.services.library import ProfileLibrary
from onemic.services.metering import Metering
from onemic.services.session import MicSession, SessionStatus
from onemic.services.supervisor import NodeSupervisor, Timing
from onemic.services.worker import LatestJobWorker
from onemic.ui.controller import AppController
from onemic.ui.dialogs import CloseChoice, MicActions
from onemic.ui.dispatch import MainThreadDispatcher
from onemic.ui.main_window import MainWindow
from onemic.ui.meter_pump import MeterPump
from onemic.ui.mic_actions import LIVE_DELETE, LibraryMicActions
from onemic.ui.session_client import SessionClient
from onemic.ui.theme import Palette
from tests.fakes import FakePipeWire, FakeTaps, InMemoryProfileStore, InMemoryWindowStore

LESSON = MicProfile("Lesson", (InputSettings("v1", "mic2", "Voice"),))
STREAM = MicProfile("Stream")
NAMES = NodeNames("lesson")


@dataclass
class ScriptedDialogs:
    close_choice: CloseChoice = CloseChoice.KEEP_LIVE
    pick: AudioSource | None = None
    close_asked: list[str] = field(default_factory=list)
    offered: list[AudioSource] = field(default_factory=list)
    managed: int = 0

    def ask_on_close(self, mic_name: str) -> CloseChoice:
        self.close_asked.append(mic_name)
        return self.close_choice

    def pick_source(self, sources: Sequence[AudioSource], used: Collection[str]) -> AudioSource | None:
        self.offered = list(sources)
        return self.pick

    def manage_mics(self, actions: MicActions) -> None:
        self.managed += 1
        actions.create_mic("Made In Manager")


@dataclass
class Harness:
    controller: AppController
    window: MainWindow
    wire: FakePipeWire
    store: InMemoryProfileStore
    window_store: InMemoryWindowStore
    dialogs: ScriptedDialogs
    taps: FakeTaps
    quits: list[bool]


@pytest.fixture
def harness(qtbot: QtBot) -> Iterator[Harness]:
    wire = FakePipeWire(default_sink="speakers")
    wire.add_node("speakers", "Audio/Sink", inputs=2, outputs=2)
    wire.add_node("mic2", "Audio/Source", outputs=1)
    supervisor = NodeSupervisor(
        graph=wire, mics=wire, stages=wire, launcher=wire, timing=Timing(1, 0), sleep=lambda _: None
    )
    session = MicSession(graph=wire, supervisor=supervisor, volumes=wire, stages=wire)
    window = MainWindow(Palette(), LevelThresholds(), WindowState())
    qtbot.addWidget(window)
    client = SessionClient(session, wire, LatestJobWorker(), MainThreadDispatcher(window))
    taps = FakeTaps()
    store = InMemoryProfileStore([LESSON, STREAM], "lesson")
    window_store = InMemoryWindowStore()
    dialogs = ScriptedDialogs()
    quits: list[bool] = []
    controller = AppController(
        window=window,
        library=ProfileLibrary(store),
        client=client,
        meters=MeterPump(Metering(taps), window.show_levels, window),
        window_store=window_store,
        dialogs=dialogs,
        quit_application=lambda: quits.append(True),
    )
    yield Harness(controller, window, wire, store, window_store, dialogs, taps, quits)
    window.allow_close()
    window.close()


def go_live(qtbot: QtBot, harness: Harness) -> None:
    harness.window.header._live.click()
    qtbot.waitUntil(lambda: harness.controller.status.live)


def test_start_shows_the_selected_mic(harness: Harness) -> None:
    harness.controller.start()

    assert harness.window.header._mics.currentText() == "Lesson"
    assert list(harness.window._rows) == ["v1"]


def test_start_adopts_a_mic_left_live(qtbot: QtBot, harness: Harness) -> None:
    harness.wire.create("onemic.stream", "Stream (OneMic)")

    harness.controller.start()

    qtbot.waitUntil(lambda: harness.controller.status.live_slug == "stream")
    assert harness.window.header._mics.currentText() == "Stream"


def test_going_live_builds_the_mic_and_starts_meters(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()

    go_live(qtbot, harness)

    assert harness.wire.linked("mic2", NAMES.stage_input("v1"))
    assert harness.window.header._live.isChecked()
    assert set(harness.taps.opened) == {NAMES.tap("v1"), NAMES.mix_tap}


def test_stopping_takes_the_mic_down_and_keeps_only_input_meters(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header._live.click()

    qtbot.waitUntil(lambda: not harness.controller.status.live)
    assert not harness.wire.has_node(NAMES.mic)
    assert harness.taps.opened[NAMES.mix_tap].closed
    assert not harness.taps.opened[NAMES.tap("v1")].closed


def test_slider_changes_reach_pipewire_and_are_saved_once(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)
    stage = harness.wire.node(NAMES.stage_input("v1")).id

    for value in (90, 70, 40):
        harness.window._rows["v1"]._slider.setValue(value)

    qtbot.waitUntil(lambda: harness.wire.stage_controls[stage].multiplier == pytest.approx(0.4**3))
    qtbot.waitUntil(lambda: harness.store.saves == 1)
    assert harness.store.profiles[0].inputs[0].gain == 0.4


def test_adding_an_input_from_the_picker(qtbot: QtBot, harness: Harness) -> None:
    harness.wire.add_node("REAPER", "Stream/Output/Audio", outputs=2)
    harness.dialogs.pick = AudioSource("REAPER", "REAPER", SourceKind.APPLICATION)
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header.add_input_requested.emit()

    qtbot.waitUntil(lambda: len(harness.window._rows) == 2)
    assert "REAPER" in [source.name for source in harness.dialogs.offered]
    new_id = list(harness.window._rows)[1]
    qtbot.waitUntil(lambda: harness.wire.has_node(NAMES.stage_output(new_id)))
    qtbot.waitUntil(lambda: harness.wire.linked("REAPER", NAMES.stage_input(new_id)))


def test_removing_an_input(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    harness.window.set_expanded(True)
    go_live(qtbot, harness)

    harness.window._rows["v1"]._remove.click()

    assert harness.window._rows == {}
    qtbot.waitUntil(lambda: not harness.wire.has_node(NAMES.stage_input("v1")))


def test_switching_mics_while_live_moves_the_live_mic(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header._mics.setCurrentIndex(1)

    qtbot.waitUntil(lambda: harness.controller.status.live_slug == "stream")
    assert not harness.wire.has_node(NAMES.mic)


def test_managing_mics_keeps_the_live_mic_selected(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header.manage_requested.emit()

    assert harness.dialogs.managed == 1
    assert harness.window.header._mics.currentText() == "Lesson"
    assert harness.window.header._mics.count() == 3


def test_window_moves_and_expansion_are_remembered(harness: Harness) -> None:
    harness.controller.start()

    harness.window.set_expanded(True)

    assert harness.window_store.saved[-1].expanded


def test_closing_while_not_live_quits_without_asking(harness: Harness) -> None:
    harness.controller.start()

    harness.window.header.close_requested.emit()

    assert harness.dialogs.close_asked == []
    assert harness.quits == [True]


def test_closing_while_live_can_keep_the_mic(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header.close_requested.emit()

    assert harness.dialogs.close_asked == ["Lesson"]
    assert harness.wire.has_node(NAMES.mic)
    assert harness.quits == [True]


def test_closing_while_live_can_stop_the_mic(qtbot: QtBot, harness: Harness) -> None:
    harness.dialogs.close_choice = CloseChoice.STOP
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header.close_requested.emit()

    assert not harness.wire.has_node(NAMES.mic)


def test_cancelling_the_close_keeps_everything_running(qtbot: QtBot, harness: Harness) -> None:
    harness.dialogs.close_choice = CloseChoice.CANCEL
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window.header.close_requested.emit()

    assert harness.quits == []
    assert harness.window.isVisible()


def test_failures_are_shown_in_the_window(qtbot: QtBot, harness: Harness) -> None:
    harness.wire.refuse_mic = True
    harness.controller.start()

    harness.window.header._live.click()

    qtbot.waitUntil(lambda: harness.window._error.text() == "Module initialization failed")
    assert not harness.controller.status.live
    assert not harness.window.header._live.isChecked()


def test_a_mic_still_going_live_cannot_be_deleted(harness: Harness) -> None:
    harness.controller.start()

    harness.window.header._live.click()
    actions = LibraryMicActions(harness.controller._library, harness.controller._protected)

    assert actions.delete_mic("lesson") == LIVE_DELETE


def test_a_status_for_a_deleted_mic_stops_it(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    harness.wire.create("onemic.ghost", "Ghost (OneMic)")

    harness.controller._on_status(SessionStatus("ghost"))

    qtbot.waitUntil(lambda: not harness.wire.has_node("onemic.ghost"))
    assert not harness.controller.status.live


def test_a_repair_that_started_before_a_click_does_not_undo_it(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)
    client = harness.controller._client
    stale = client._generation

    harness.window.header._live.click()
    client._emit_if_current(stale, SessionStatus("lesson"))

    qtbot.waitUntil(lambda: not harness.controller.status.live)
    assert not harness.window.header._live.isChecked()


def test_closing_right_after_going_live_still_asks(harness: Harness) -> None:
    harness.controller.start()

    harness.window.header._live.click()
    harness.window.header.close_requested.emit()

    assert harness.dialogs.close_asked == ["Lesson"]
    assert harness.wire.has_node(NAMES.mic)


def test_inputs_are_metered_before_going_live(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()

    qtbot.waitUntil(lambda: NAMES.tap("v1") in harness.taps.opened)
    assert NAMES.mix_tap not in harness.taps.opened

    go_live(qtbot, harness)

    assert NAMES.mix_tap in harness.taps.opened


def test_solo_is_saved_and_applied(qtbot: QtBot, harness: Harness) -> None:
    harness.controller.start()
    go_live(qtbot, harness)

    harness.window._rows["v1"]._solo.click()

    qtbot.waitUntil(lambda: harness.store.saves >= 1)
    assert harness.store.profiles[0].inputs[0].soloed
