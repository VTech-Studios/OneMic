from pytestqt.qtbot import QtBot

from onemic.domain.profile import MicProfile
from onemic.ui.header import LISTEN_BLOCKED_TIP, LIVE_TEXT, OFF_TEXT, HeaderBar


def make(qtbot: QtBot) -> HeaderBar:
    header = HeaderBar()
    qtbot.addWidget(header)
    return header


def test_profiles_are_listed_without_reporting_a_selection(qtbot: QtBot) -> None:
    header = make(qtbot)

    with qtbot.assertNotEmitted(header.mic_selected):
        header.show_profiles([MicProfile("Lesson"), MicProfile("Stream")], "stream")

    assert header._mics.currentText() == "Stream"


def test_choosing_a_mic_reports_its_slug(qtbot: QtBot) -> None:
    header = make(qtbot)
    header.show_profiles([MicProfile("Lesson"), MicProfile("Stream")], "lesson")

    with qtbot.waitSignal(header.mic_selected) as signal:
        header._mics.setCurrentIndex(1)

    assert signal.args == ["stream"]


def test_the_live_switch_shows_the_real_state(qtbot: QtBot) -> None:
    header = make(qtbot)

    with qtbot.assertNotEmitted(header.live_toggled):
        header.show_status(live=True, listening=False, listen_blocked=False)

    assert header._live.isChecked()
    assert header._live.text() == LIVE_TEXT
    assert header._listen.isEnabled()

    header.show_status(live=False, listening=False, listen_blocked=False)

    assert header._live.text() == OFF_TEXT
    assert not header._listen.isEnabled()


def test_listening_is_disabled_when_it_would_feed_back(qtbot: QtBot) -> None:
    header = make(qtbot)

    header.show_status(live=True, listening=False, listen_blocked=True)

    assert not header._listen.isEnabled()
    assert header._listen.toolTip() == LISTEN_BLOCKED_TIP


def test_clicking_live_reports_the_wish(qtbot: QtBot) -> None:
    header = make(qtbot)

    with qtbot.waitSignal(header.live_toggled) as signal:
        header._live.click()

    assert signal.args == [True]


def test_expand_state_is_shown_without_echo(qtbot: QtBot) -> None:
    header = make(qtbot)

    with qtbot.assertNotEmitted(header.expand_toggled):
        header.set_expanded(True)

    assert header._expand.isChecked()
