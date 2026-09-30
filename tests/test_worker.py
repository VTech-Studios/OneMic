import threading
from collections.abc import Callable
from typing import Any

from onemic.services.worker import LatestJobWorker


class Recorder:
    def __init__(self) -> None:
        self.results: list[Any] = []
        self.errors: list[Exception] = []
        self.finished = threading.Event()

    def done(self, result: Any) -> None:
        self.results.append(result)
        self.finished.set()

    def failed(self, error: Exception) -> None:
        self.errors.append(error)
        self.finished.set()


def constant(value: int) -> Callable[[], int]:
    return lambda: value


def test_jobs_run_in_the_background_and_report_their_results() -> None:
    worker, recorder = LatestJobWorker(), Recorder()

    worker.submit("a", lambda: 42, recorder.done, recorder.failed)

    assert recorder.finished.wait(2)
    assert recorder.results == [42]
    worker.shutdown()


def test_only_the_newest_queued_job_of_a_kind_runs() -> None:
    worker, recorder = LatestJobWorker(), Recorder()
    gate = threading.Event()
    worker.submit("block", gate.wait, lambda _: None, recorder.failed)
    for value in range(5):
        worker.submit("levels", constant(value), recorder.done, recorder.failed)

    assert worker.is_pending("levels")
    gate.set()

    assert recorder.finished.wait(2)
    worker.shutdown()
    assert recorder.results == [4]


def test_failures_are_reported_and_the_worker_carries_on() -> None:
    worker, recorder = LatestJobWorker(), Recorder()

    def explode() -> None:
        raise RuntimeError("no")

    worker.submit("a", explode, recorder.done, recorder.failed)
    assert recorder.finished.wait(2)
    recorder.finished.clear()
    worker.submit("b", lambda: "ok", recorder.done, recorder.failed)

    assert recorder.finished.wait(2)
    assert [str(error) for error in recorder.errors] == ["no"]
    assert recorder.results == ["ok"]
    worker.shutdown()


def test_shutdown_finishes_queued_jobs_first() -> None:
    worker, recorder = LatestJobWorker(), Recorder()
    gate = threading.Event()
    worker.submit("block", gate.wait, lambda _: None, recorder.failed)
    worker.submit("later", lambda: "made", recorder.done, recorder.failed)

    gate.set()
    worker.shutdown()

    assert recorder.results == ["made"]


def test_a_failing_callback_does_not_stop_the_worker() -> None:
    worker, recorder = LatestJobWorker(), Recorder()

    def broken(_: Any) -> None:
        raise RuntimeError("callback bug")

    worker.submit("a", lambda: 1, broken, recorder.failed)
    worker.submit("b", lambda: 2, recorder.done, recorder.failed)

    assert recorder.finished.wait(2)
    assert recorder.results == [2]
    worker.shutdown()
