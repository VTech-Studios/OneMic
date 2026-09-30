from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from collections.abc import Callable, Sequence

from PySide6.QtCore import QLockFile
from PySide6.QtWidgets import QApplication, QMessageBox

from . import __version__
from .config import REQUIRED_TOOLS, Config
from .infrastructure.lv2 import find_lsp_gate
from .ui.theme import Palette, stylesheet
from .wiring import build_application


def missing_tools(which: Callable[[str], str | None] = shutil.which) -> list[str]:
    """Find PipeWire tools that are not installed.

    Checking up front gives one clear message, instead of a confusing error
    the first time the user presses Go live.

    @param which: looks a program up on PATH.
    @return: the names of missing tools, empty if all are present.
    """
    return [tool for tool in REQUIRED_TOOLS if which(tool) is None]


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    """Read the command line.

    @param argv: the arguments after the program name.
    @return: the parsed options.
    """
    parser = argparse.ArgumentParser(prog="onemic", description="Blend audio signals into one virtual mic.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", action="store_true", help="log every PipeWire change")
    return parser.parse_args(argv)


def create_qt_application() -> QApplication:
    """Create the Qt application with OneMic's identity and styling.

    @return: the application, not yet running.
    """
    application = QApplication(sys.argv[:1])
    application.setApplicationName("OneMic")
    application.setDesktopFileName("onemic")
    application.setStyleSheet(stylesheet(Palette()))
    return application


def acquire_lock(config: Config) -> QLockFile | None:
    """Make sure only one OneMic runs at a time.

    Two copies would each try to converge the graph on their own idea of
    the mic, undoing each other's links every second.

    @param config: where the lock file lives.
    @return: the held lock, which must stay referenced while running, or None if another copy holds it.
    """
    config.runtime_dir.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(config.lock_path))
    return lock if lock.tryLock(100) else None


def main(argv: Sequence[str] | None = None) -> int:
    """Start the window.

    @param argv: command line arguments, defaulting to the process's own.
    @return: the exit status.
    """
    options = parse_arguments(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(level=logging.INFO if options.verbose else logging.WARNING)
    application = create_qt_application()
    missing = missing_tools()
    if missing:
        QMessageBox.critical(None, "OneMic", f"OneMic needs these PipeWire tools: {', '.join(missing)}")
        return 1
    config = Config.from_environment(os.environ)
    lock = acquire_lock(config)
    if lock is None:
        QMessageBox.information(None, "OneMic", "OneMic is already open.")
        return 1
    built = build_application(config, application.quit, find_lsp_gate(os.environ))
    built.controller.start()
    return application.exec()
