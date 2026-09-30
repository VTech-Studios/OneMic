import pytest

from onemic.domain.errors import AudioError
from onemic.domain.graph import Graph
from onemic.domain.naming import NodeNames
from onemic.domain.profile import InputSettings, MicProfile
from onemic.services.routing import InputState
from onemic.services.session import MicSession
from onemic.services.supervisor import NodeSupervisor, Timing
from tests.fakes import FakePipeWire

VOICE = InputSettings("v1", "mic2", "Voice", gain=0.8)
GUITAR = InputSettings("g1", "REAPER", "REAPER")
LESSON = MicProfile("Lesson", (VOICE, GUITAR), gain=0.9)
NAMES = NodeNames("lesson")


@pytest.fixture
def wire() -> FakePipeWire:
    pipewire = FakePipeWire(default_sink="speakers")
    pipewire.add_node("speakers", "Audio/Sink", inputs=2, outputs=2)
    pipewire.add_node("mic2", "Audio/Source", outputs=1)
    pipewire.add_node("REAPER", "Stream/Output/Audio", outputs=2)
    return pipewire


def session_for(wire: FakePipeWire, clock: list[float] | None = None) -> MicSession:
    now = clock if clock is not None else [0.0]
    supervisor = NodeSupervisor(
        graph=wire,
        mics=wire,
        stages=wire,
        launcher=wire,
        timing=Timing(attempts=3, interval=0, grace=5.0),
        sleep=lambda _: None,
        clock=lambda: now[0],
    )
    return MicSession(graph=wire, supervisor=supervisor, volumes=wire)


def test_going_live_builds_and_wires_the_mic(wire: FakePipeWire) -> None:
    status = session_for(wire).go_live(LESSON)

    assert status.live_slug == "lesson"
    assert status.inputs == {"v1": InputState.LIVE, "g1": InputState.LIVE}
    assert wire.created_mics == [("onemic.lesson", "Lesson (OneMic)")]
    assert wire.linked("mic2", NAMES.stage_input("v1"))
    assert wire.linked(NAMES.stage_output("g1"), NAMES.mic)


def test_levels_are_applied_to_each_stage_and_the_mic(wire: FakePipeWire) -> None:
    session_for(wire).go_live(LESSON)

    assert wire.volumes[wire.node(NAMES.stage_output("v1")).id] == 0.8
    assert wire.volumes[wire.node(NAMES.mic).id] == 0.9
    assert wire.mutes[wire.node(NAMES.stage_output("g1")).id] is False


def test_unchanged_levels_are_not_sent_again(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)
    calls = wire.volume_calls

    session.reconcile()

    assert wire.volume_calls == calls


def test_level_changes_apply_without_rebuilding(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)

    session.apply_levels(LESSON.with_input_gain("v1", 0.3).with_input_muted("g1", True))

    assert wire.volumes[wire.node(NAMES.stage_output("v1")).id] == 0.3
    assert wire.mutes[wire.node(NAMES.stage_output("g1")).id] is True
    assert len(wire.started_stages) == 2


def test_level_changes_for_another_mic_are_ignored(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)
    calls = wire.volume_calls

    session.apply_levels(MicProfile("Other"))

    assert wire.volume_calls == calls


def test_nodes_published_before_their_ports_are_waited_for(wire: FakePipeWire) -> None:
    wire.hidden_ports_for = 2

    session_for(wire).go_live(LESSON)

    assert wire.linked("mic2", NAMES.stage_input("v1"))


def test_an_application_opened_later_is_linked_on_the_next_pass(wire: FakePipeWire) -> None:
    wire.remove_node("REAPER")
    session = session_for(wire)
    assert session.go_live(LESSON).inputs["g1"] is InputState.WAITING

    wire.add_node("REAPER", "Stream/Output/Audio", outputs=2)
    status = session.reconcile()

    assert status.inputs["g1"] is InputState.LIVE
    assert wire.linked("REAPER", NAMES.stage_input("g1"))


def test_a_crashed_stage_is_restarted_once_its_grace_period_is_over(wire: FakePipeWire) -> None:
    clock = [0.0]
    session = session_for(wire, clock)
    session.go_live(LESSON)
    pid = wire.node(NAMES.stage_output("v1")).process_id
    wire.remove_node(NAMES.stage_output("v1"))

    session.reconcile()
    assert pid not in wire.terminated

    clock[0] = 10.0
    session.reconcile()

    assert pid in wire.terminated
    assert wire.linked(NAMES.stage_output("v1"), NAMES.mic)


def test_removing_an_input_stops_its_stage(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)

    session.update(LESSON.without_input("g1"))

    assert not wire.has_node(NAMES.stage_input("g1"))
    assert wire.has_node(NAMES.stage_input("v1"))


def test_updates_to_a_mic_that_is_not_live_change_nothing(wire: FakePipeWire) -> None:
    status = session_for(wire).update(LESSON)

    assert not status.live
    assert wire.created_mics == []


def test_going_live_with_another_mic_takes_the_first_down(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)

    session.go_live(MicProfile("Stream", (VOICE,)))

    assert not wire.has_node(NAMES.mic)
    assert not wire.has_node(NAMES.stage_input("g1"))
    assert wire.has_node("onemic.stream")


def test_stopping_removes_every_onemic_node_but_never_kills_the_mic_owner(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)

    status = session.stop()

    assert not status.live
    assert not [node.name for node in wire.nodes if node.name.startswith("onemic")]
    assert 1 not in wire.terminated


def test_listening_follows_the_toggle(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)

    assert session.set_listening(True).listening
    assert wire.linked(NAMES.mic, "speakers")
    session.set_listening(False)
    assert not wire.linked(NAMES.mic, "speakers")


def test_listening_before_going_live_only_records_the_wish(wire: FakePipeWire) -> None:
    session = session_for(wire)

    assert not session.set_listening(True).live
    session.go_live(LESSON)

    assert wire.linked(NAMES.mic, "speakers")


def test_a_mic_left_live_is_adopted(wire: FakePipeWire) -> None:
    session_for(wire).go_live(LESSON)

    status = session_for(wire).adopt([MicProfile("Other"), LESSON])

    assert status.live_slug == "lesson"
    assert len(wire.started_stages) == 2


def test_adopting_with_nothing_live(wire: FakePipeWire) -> None:
    assert not session_for(wire).adopt([LESSON]).live


def test_a_failed_link_does_not_abandon_the_pass(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)
    for link in list(wire.links):
        wire.unlink(link)
    wire.refuse_links_into = {NAMES.stage_input("v1")}

    session.reconcile()

    assert not wire.linked("mic2", NAMES.stage_input("v1"))
    assert wire.linked("REAPER", NAMES.stage_input("g1"))


def test_status_without_touching_the_graph(wire: FakePipeWire) -> None:
    session = session_for(wire)
    assert not session.status().live

    session.go_live(LESSON)

    assert session.status().inputs == {"v1": InputState.LIVE, "g1": InputState.LIVE}


def test_graph_failures_reach_the_caller() -> None:
    class Broken(FakePipeWire):
        def snapshot(self) -> Graph:
            raise AudioError("pw-dump is not installed")

    with pytest.raises(AudioError):
        session_for(Broken()).go_live(LESSON)


def test_a_failed_go_live_leaves_nothing_behind(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(MicProfile("Stream", (VOICE,)))
    wire.refuse_mic = True

    with pytest.raises(AudioError):
        session.go_live(LESSON)

    assert not session.status().live
    assert not [node.name for node in wire.nodes if node.name.startswith("onemic")]


def test_a_failed_listen_change_keeps_the_old_setting(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)
    wire.refuse_snapshots = True

    with pytest.raises(AudioError):
        session.set_listening(True)

    assert not session.status().listening


def test_changing_the_default_output_moves_listening(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)
    session.set_listening(True)
    wire.add_node("headphones", "Audio/Sink", inputs=2)
    wire.default_sink = "headphones"

    session.reconcile()

    assert wire.linked(NAMES.mic, "headphones")
    assert not wire.linked(NAMES.mic, "speakers")


def test_level_changes_reach_a_restarted_stage(wire: FakePipeWire) -> None:
    clock = [0.0]
    session = session_for(wire, clock)
    session.go_live(LESSON)
    wire.remove_node(NAMES.stage_output("v1"))
    clock[0] = 10.0
    session.reconcile()

    session.apply_levels(LESSON.with_input_gain("v1", 0.2))

    assert wire.volumes[wire.node(NAMES.stage_output("v1")).id] == 0.2


def test_a_level_change_that_fails_is_retried_on_the_next_pass(wire: FakePipeWire) -> None:
    session = session_for(wire)
    wire.refuse_volumes = True
    session.go_live(LESSON)
    wire.refuse_volumes = False

    session.reconcile()

    assert wire.volumes[wire.node(NAMES.stage_output("v1")).id] == 0.8


def test_adopting_removes_any_other_mic_left_live(wire: FakePipeWire) -> None:
    session_for(wire).go_live(LESSON)
    wire.create("onemic.stream", "Stream (OneMic)")

    session_for(wire).adopt([LESSON, MicProfile("Stream")])

    assert not wire.has_node("onemic.stream")
    assert wire.has_node(NAMES.mic)


def test_preview_links_sources_to_taps_while_nothing_is_live(wire: FakePipeWire) -> None:
    wire.add_node(NAMES.tap("v1"), "Stream/Input/Audio", inputs=2)

    status = session_for(wire).preview(LESSON)

    assert not status.live
    assert wire.linked("mic2", NAMES.tap("v1"))
    assert not wire.has_node(NAMES.mic)


def test_going_live_moves_a_tap_from_the_source_to_its_stage(wire: FakePipeWire) -> None:
    wire.add_node(NAMES.tap("v1"), "Stream/Input/Audio", inputs=2)
    session = session_for(wire)
    session.preview(LESSON)

    session.go_live(LESSON)

    assert wire.linked(NAMES.stage_output("v1"), NAMES.tap("v1"))
    assert not wire.linked("mic2", NAMES.tap("v1"))


def test_preview_changes_nothing_while_live(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)
    links = set(wire.links)

    assert session.preview(LESSON).live
    assert wire.links == links


def test_soloing_an_input_mutes_the_others_on_the_mic(wire: FakePipeWire) -> None:
    session = session_for(wire)
    session.go_live(LESSON)

    session.apply_levels(LESSON.with_input_soloed("g1", True))

    assert wire.mutes[wire.node(NAMES.stage_output("v1")).id] is True
    assert wire.mutes[wire.node(NAMES.stage_output("g1")).id] is False
