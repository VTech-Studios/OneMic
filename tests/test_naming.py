from onemic.domain.naming import NodeNames, is_onemic_node, is_tap, mic_slug

NAMES = NodeNames("guitar-lesson")


def test_every_name_derives_from_the_slug() -> None:
    assert NAMES.mic == "onemic.guitar-lesson"
    assert NAMES.stage_input("ab12") == "onemic.guitar-lesson.in.ab12"
    assert NAMES.stage_output("ab12") == "onemic.guitar-lesson.in.ab12.out"
    assert NAMES.tap("ab12") == "onemic.guitar-lesson.tap.ab12"
    assert NAMES.mix_tap == "onemic.guitar-lesson.tap.mix"


def test_a_mic_owns_only_its_own_nodes() -> None:
    assert NAMES.owns("onemic.guitar-lesson")
    assert NAMES.owns("onemic.guitar-lesson.in.ab12.out")
    assert not NAMES.owns("onemic.guitar-lesson-2")
    assert not NAMES.owns("onemic.guitar-lesson-2.in.ab12")
    assert not NAMES.owns("REAPER")


def test_stage_ids_are_recovered_from_either_half_of_a_stage() -> None:
    assert NAMES.stage_id("onemic.guitar-lesson.in.ab12") == "ab12"
    assert NAMES.stage_id("onemic.guitar-lesson.in.ab12.out") == "ab12"
    assert NAMES.stage_id("onemic.guitar-lesson.tap.ab12") is None
    assert NAMES.stage_id("onemic.other.in.ab12") is None


def test_onemic_nodes_are_recognised_by_prefix() -> None:
    assert is_onemic_node("onemic.anything")
    assert not is_onemic_node("onemicrophone")
    assert is_tap("onemic.a.tap.mix")
    assert not is_tap("onemic.a.in.b")


def test_mic_slug_only_matches_mic_nodes() -> None:
    assert mic_slug("onemic.guitar-lesson") == "guitar-lesson"
    assert mic_slug("onemic.guitar-lesson.in.ab12") is None
    assert mic_slug("REAPER") is None
