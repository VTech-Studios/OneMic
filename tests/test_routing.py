from onemic.domain.graph import Link
from onemic.domain.naming import NodeNames
from onemic.domain.profile import InputSettings, MicProfile
from onemic.services.routing import InputState, preview, route
from tests.fakes import FakePipeWire

VOICE = InputSettings("v1", "mic2", "Voice")
GUITAR = InputSettings("g1", "REAPER", "REAPER")
PROFILE = MicProfile("Lesson", (VOICE, GUITAR))
NAMES = NodeNames("lesson")


def built(listening_sink: bool = True) -> FakePipeWire:
    wire = FakePipeWire(default_sink="speakers" if listening_sink else None)
    wire.add_node("speakers", "Audio/Sink", inputs=2, outputs=2)
    wire.add_node("mic2", "Audio/Source", outputs=1)
    wire.create(NAMES.mic, "Lesson (OneMic)")
    for settings in PROFILE.inputs:
        wire.start(NAMES.stage_input(settings.id), NAMES.stage_output(settings.id), settings.label)
    return wire


def apply(
    wire: FakePipeWire, listening: bool = False, heard: frozenset[str] = frozenset({"speakers"})
) -> None:
    routing = route(PROFILE, wire.snapshot(), listening, heard)
    for link in routing.to_remove:
        wire.unlink(link)
    for link in routing.to_create:
        wire.link(link)


def test_present_inputs_are_wired_through_their_stages() -> None:
    wire = built()

    apply(wire)

    assert wire.linked("mic2", NAMES.stage_input("v1"))
    assert wire.linked(NAMES.stage_output("v1"), NAMES.mic)
    assert wire.linked(NAMES.stage_output("g1"), NAMES.mic)


def test_input_states_follow_what_exists() -> None:
    wire = built()
    wire.remove_node(NAMES.stage_output("g1"))

    routing = route(PROFILE, wire.snapshot(), listening=False)

    assert routing.inputs == {"v1": InputState.LIVE, "g1": InputState.STARTING}


def test_an_absent_source_waits_and_is_linked_once_it_appears() -> None:
    wire = built()
    wire.start(NAMES.stage_input("g1"), NAMES.stage_output("g1"), "REAPER")

    assert route(PROFILE, wire.snapshot(), False).inputs["g1"] is InputState.WAITING

    wire.add_node("REAPER", "Stream/Output/Audio", outputs=4)
    apply(wire)

    assert route(PROFILE, wire.snapshot(), False).inputs["g1"] is InputState.LIVE
    assert wire.linked("REAPER", NAMES.stage_input("g1"))


def test_listening_links_the_mic_to_the_default_output_and_unlinks_after() -> None:
    wire = built()

    apply(wire, listening=True)
    assert wire.linked(NAMES.mic, "speakers")

    apply(wire, listening=False)
    assert not wire.linked(NAMES.mic, "speakers")


def test_listening_through_a_duplex_device_is_undone_too() -> None:
    wire = built()
    wire.add_node("interface", "Audio/Duplex", inputs=2, outputs=2)
    wire.default_sink = "interface"

    apply(wire, listening=True, heard=frozenset({"interface"}))
    assert wire.linked(NAMES.mic, "interface")

    apply(wire, listening=False, heard=frozenset({"interface"}))
    assert not wire.linked(NAMES.mic, "interface")


def test_a_link_made_by_hand_to_another_output_is_left_alone() -> None:
    wire = built()
    other = wire.add_node("headset", "Audio/Sink", inputs=2)
    by_hand = Link(wire.node(NAMES.mic).outputs[0].id, other.inputs[0].id)
    wire.link(by_hand)

    apply(wire, listening=False)

    assert by_hand in wire.links


def test_listening_is_blocked_when_the_default_output_is_an_input() -> None:
    wire = built()
    profile = PROFILE.with_input(InputSettings("s1", "speakers", "Speakers"))

    routing = route(profile, wire.snapshot(), listening=True)

    assert routing.listen_blocked
    mic_outputs = {port.id for port in wire.node(NAMES.mic).outputs}
    assert not any(link.output_port in mic_outputs for link in routing.desired)


def test_a_call_app_recording_the_mic_is_never_unlinked() -> None:
    wire = built()
    browser = wire.add_node("browser", "Stream/Input/Audio", inputs=2)
    recording = Link(wire.node(NAMES.mic).outputs[0].id, browser.inputs[0].id)
    wire.link(recording)

    apply(wire)

    assert recording in wire.links


def test_foreign_links_into_the_mic_are_removed() -> None:
    wire = built()
    stray = wire.add_node("stray", "Audio/Source", outputs=1)
    wire.link(Link(stray.outputs[0].id, wire.node(NAMES.mic).inputs[0].id))

    apply(wire)

    assert not wire.linked("stray", NAMES.mic)


def test_taps_are_fed_when_they_exist() -> None:
    wire = built()
    wire.add_node(NAMES.tap("v1"), "Stream/Input/Audio", inputs=2)
    wire.add_node(NAMES.mix_tap, "Stream/Input/Audio", inputs=2)

    apply(wire)

    assert wire.linked(NAMES.stage_output("v1"), NAMES.tap("v1"))
    assert wire.linked(NAMES.mic, NAMES.mix_tap)


def test_preview_feeds_each_tap_straight_from_its_source() -> None:
    wire = FakePipeWire()
    wire.add_node("mic2", "Audio/Source", outputs=1)
    wire.add_node(NAMES.tap("v1"), "Stream/Input/Audio", inputs=2)
    wire.add_node(NAMES.tap("g1"), "Stream/Input/Audio", inputs=2)

    routing = preview(PROFILE, wire.snapshot())
    for link in routing.to_create:
        wire.link(link)

    assert wire.linked("mic2", NAMES.tap("v1"))
    assert routing.inputs == {"v1": InputState.OFF, "g1": InputState.OFF}
