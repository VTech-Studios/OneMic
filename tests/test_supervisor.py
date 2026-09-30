from onemic.domain.naming import NodeNames
from onemic.domain.profile import InputSettings, MicProfile
from onemic.domain.stage import StageControls
from onemic.services.supervisor import NodeSupervisor, Timing
from tests.fakes import FakePipeWire

LESSON = MicProfile("Lesson", (InputSettings("v1", "mic2", "Voice"),))
NAMES = NodeNames("lesson")


def supervisor(wire: FakePipeWire, clock: list[float]) -> NodeSupervisor:
    return NodeSupervisor(
        graph=wire,
        mics=wire,
        stages=wire,
        launcher=wire,
        timing=Timing(attempts=2, interval=0, grace=5.0),
        sleep=lambda _: None,
        clock=lambda: clock[0],
    )


def test_ensure_starts_the_mic_and_each_stage_once() -> None:
    wire = FakePipeWire()

    graph = supervisor(wire, [0.0]).ensure(LESSON, wire.snapshot())

    assert graph.node(NAMES.mic) is not None
    assert [stage[0] for stage in wire.started_stages] == [NAMES.stage_input("v1")]


def test_a_slow_start_is_not_started_a_second_time() -> None:
    wire = FakePipeWire()
    clock = [0.0]
    subject = supervisor(wire, clock)
    subject.ensure(LESSON, wire.snapshot())
    wire.remove_node(NAMES.stage_input("v1"))
    wire.remove_node(NAMES.stage_output("v1"))
    wire.remove_node(NAMES.mic)

    clock[0] = 2.0
    subject.ensure(LESSON, wire.snapshot())

    assert len(wire.started_stages) == 1
    assert len(wire.created_mics) == 1

    clock[0] = 6.0
    subject.ensure(LESSON, wire.snapshot())

    assert len(wire.started_stages) == 2
    assert len(wire.created_mics) == 2


def test_duplicate_stages_are_stopped_keeping_the_oldest() -> None:
    wire = FakePipeWire()
    subject = supervisor(wire, [0.0])
    subject.ensure(LESSON, wire.snapshot())
    original = wire.node(NAMES.stage_output("v1")).process_id
    wire.start(
        NAMES.stage_input("v1"), NAMES.stage_output("v1"), "duplicate", StageControls(5.0, 1.0, False, 0.01)
    )
    duplicate = [node.process_id for node in wire.nodes if node.name == NAMES.stage_output("v1")][1]

    subject.ensure(LESSON, wire.snapshot())

    assert wire.terminated == [duplicate]
    assert [node.process_id for node in wire.nodes if node.name == NAMES.stage_output("v1")] == [original]


def test_stages_for_removed_inputs_are_stopped() -> None:
    wire = FakePipeWire()
    subject = supervisor(wire, [0.0])
    subject.ensure(LESSON, wire.snapshot())

    subject.ensure(LESSON.without_input("v1"), wire.snapshot())

    assert not wire.has_node(NAMES.stage_input("v1"))


def test_teardown_spares_the_kept_mic_and_every_tap() -> None:
    wire = FakePipeWire()
    subject = supervisor(wire, [0.0])
    subject.ensure(LESSON, wire.snapshot())
    wire.create("onemic.other", "Other (OneMic)")
    wire.add_node(NAMES.mix_tap, "Stream/Input/Audio", inputs=2)

    subject.teardown(wire.snapshot(), keep=NAMES)

    assert not wire.has_node("onemic.other")
    assert wire.has_node(NAMES.mic)
    assert wire.has_node(NAMES.mix_tap)


def test_teardown_forgets_start_times_so_a_new_start_is_immediate() -> None:
    wire = FakePipeWire()
    subject = supervisor(wire, [0.0])
    subject.ensure(LESSON, wire.snapshot())

    subject.teardown(wire.snapshot(), keep=None)
    subject.ensure(LESSON, wire.snapshot())

    assert len(wire.created_mics) == 2
