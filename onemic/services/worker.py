from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

log = logging.getLogger(__name__)

Job = Callable[[], Any]
Done = Callable[[Any], None]
Failed = Callable[[Exception], None]


class JobQueue(Protocol):
    def submit(self, key: str, job: Job, done: Done, failed: Failed) -> None:
        """Queue a job, replacing any queued job with the same key.

        @param key: what the job does, such as "levels" or "reconcile".
        @param job: the work, run in the background.
        @param done: called in the background with the job's result.
        @param failed: called in the background with the job's exception.
        """
        ...

    def is_pending(self, key: str) -> bool:
        """Tell whether a job with this key is queued and not yet started."""
        ...

    def shutdown(self) -> None:
        """Finish every queued job, then stop."""
        ...


@dataclass(frozen=True)
class _Task:
    job: Job
    done: Done
    failed: Failed


class LatestJobWorker:
    """Runs jobs one at a time on a background thread, keeping only the newest of each kind.

    Every change to the audio graph goes through this one thread, so two
    changes can never race each other. Jobs share a key when a newer one
    makes an older one pointless, such as two volume changes from the same
    slider drag, so a backlog can never build up behind the interface.
    """

    def __init__(self) -> None:
        self._pending: OrderedDict[str, _Task] = OrderedDict()
        self._condition = threading.Condition()
        self._running = True
        self._thread = threading.Thread(target=self._loop, name="onemic-worker", daemon=True)
        self._thread.start()

    def submit(self, key: str, job: Job, done: Done, failed: Failed) -> None:
        """Queue a job, replacing any queued job with the same key.

        @param key: what the job does, such as "levels" or "reconcile".
        @param job: the work, run on the background thread.
        @param done: called on the background thread with the job's result.
        @param failed: called on the background thread with the job's exception.
        """
        with self._condition:
            self._pending.pop(key, None)
            self._pending[key] = _Task(job, done, failed)
            self._condition.notify()

    def is_pending(self, key: str) -> bool:
        """Tell whether a job with this key is queued and not yet started.

        @param key: the job kind.
        @return: True if one is waiting.
        """
        with self._condition:
            return key in self._pending

    def shutdown(self) -> None:
        """Finish every queued job, then stop the thread.

        Queued jobs are run rather than dropped, so a mic the user asked for
        just before closing is really made before the close prompt's choice
        is applied. Every command has its own timeout, so this cannot hang.
        """
        with self._condition:
            self._running = False
            self._condition.notify()
        self._thread.join()

    def _next(self) -> _Task | None:
        with self._condition:
            while self._running and not self._pending:
                self._condition.wait()
            if not self._pending:
                return None
            return self._pending.popitem(last=False)[1]

    def _loop(self) -> None:
        while (task := self._next()) is not None:
            self._run(task)

    @staticmethod
    def _run(task: _Task) -> None:
        """Run one job and report its outcome, whatever goes wrong.

        Nothing may escape, including an exception from a callback, or the
        thread would die and every later job would silently never run.

        @param task: the job and its callbacks.
        """
        try:
            try:
                result = task.job()
            except Exception as error:
                log.warning("Background job failed: %s", error)
                task.failed(error)
            else:
                task.done(result)
        except Exception:
            log.exception("A background job's callback failed")
