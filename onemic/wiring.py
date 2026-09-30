from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .config import Config
from .domain.levels import LevelThresholds
from .infrastructure.gain_stage import PwLoopbackStages
from .infrastructure.pipewire import PipeWireGraph
from .infrastructure.process import SubprocessLauncher, SubprocessRunner
from .infrastructure.stores import JsonProfileStore, JsonWindowStateStore
from .infrastructure.taps import PwRecordTaps
from .infrastructure.virtual_mic import PactlVirtualMic
from .infrastructure.volume import WpctlVolume
from .services.library import ProfileLibrary
from .services.metering import Metering
from .services.session import MicSession
from .services.supervisor import NodeSupervisor
from .services.worker import LatestJobWorker
from .ui.controller import AppController
from .ui.dialogs import QtDialogs
from .ui.dispatch import MainThreadDispatcher
from .ui.main_window import MainWindow
from .ui.meter_pump import MeterPump
from .ui.session_client import SessionClient
from .ui.theme import Palette


@dataclass(frozen=True)
class Application:
    window: MainWindow
    controller: AppController


def build_session(graph: PipeWireGraph, runner: SubprocessRunner, launcher: SubprocessLauncher) -> MicSession:
    """Wire the session to the real PipeWire tools.

    @param graph: reads and rewires the audio graph.
    @param runner: runs short commands.
    @param launcher: starts long-running helpers.
    @return: a session with no mic live yet.
    """
    supervisor = NodeSupervisor(
        graph=graph,
        mics=PactlVirtualMic(runner),
        stages=PwLoopbackStages(launcher),
        launcher=launcher,
    )
    return MicSession(graph=graph, supervisor=supervisor, volumes=WpctlVolume(runner))


def build_application(config: Config, quit_application: Callable[[], None]) -> Application:
    """Build the application. This is the composition root, the one place that picks implementations.

    Everything else receives its collaborators through its constructor, so
    this is the only module that knows PipeWire's tools and JSON files are
    involved, and the only one to change to swap any of them.

    @param config: where files live.
    @param quit_application: ends the Qt event loop once the window has closed.
    @return: the window and its controller, not yet shown.
    """
    runner, launcher = SubprocessRunner(), SubprocessLauncher()
    graph = PipeWireGraph(runner)
    palette, thresholds = Palette(), LevelThresholds()
    window_store = JsonWindowStateStore(config.window_path)
    window = MainWindow(palette, thresholds, window_store.load())
    client = SessionClient(
        build_session(graph, runner, launcher), graph, LatestJobWorker(), MainThreadDispatcher(window)
    )
    meters = MeterPump(Metering(PwRecordTaps(launcher)), window.show_levels, window)
    controller = AppController(
        window=window,
        library=ProfileLibrary(JsonProfileStore(config.profiles_path)),
        client=client,
        meters=meters,
        window_store=window_store,
        dialogs=QtDialogs(window),
        quit_application=quit_application,
    )
    return Application(window, controller)
