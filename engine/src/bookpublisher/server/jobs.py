"""Trabajos en segundo plano (exportar, importar) con eventos para SSE."""
from __future__ import annotations

import itertools
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Job:
    id: str
    kind: str  # export | import
    title: str
    events: list[dict] = field(default_factory=list)
    status: str = "queued"  # queued | running | done | error | cancelled
    result: dict | None = None
    error: dict | None = None
    files: dict[str, str] = field(default_factory=dict)  # nombre lógico → ruta
    cancel: threading.Event = field(default_factory=threading.Event)
    created: float = field(default_factory=time.time)
    cond: threading.Condition = field(default_factory=threading.Condition)

    def emit(self, ev: dict) -> None:
        with self.cond:
            ev = {**ev, "seq": len(self.events)}
            self.events.append(ev)
            self.cond.notify_all()

    def summary(self) -> dict:
        last = next((e for e in reversed(self.events) if e.get("type") in ("chunk", "page")), None)
        return {"id": self.id, "kind": self.kind, "title": self.title, "status": self.status,
                "result": self.result, "error": self.error, "files": sorted(self.files), "last": last,
                "created": self.created}


class JobManager:
    """Ejecuta los trabajos de uno en uno (el grupo de procesos ya paraleliza dentro)."""

    def __init__(self, keep: int = 30):
        self.jobs: dict[str, Job] = {}
        self._run_lock = threading.Lock()
        self._keep = keep
        self._counter = itertools.count()

    def submit(self, kind: str, title: str, fn: Callable[[Job], None]) -> Job:
        job = Job(id=uuid.uuid4().hex[:12], kind=kind, title=title)
        self.jobs[job.id] = job
        self._trim()
        job.emit({"type": "queued"})

        def run():
            with self._run_lock:
                if job.cancel.is_set():
                    job.status = "cancelled"
                    job.emit({"type": "cancelled"})
                    return
                job.status = "running"
                try:
                    fn(job)
                    if job.status == "running":
                        job.status = "done"
                except Exception as e:  # noqa: BLE001 - se informa al cliente
                    from ..render.pipeline import ExportCancelled, RenderError
                    from ..readers.pdf_reader import ImportCancelled
                    if isinstance(e, (ExportCancelled, ImportCancelled)) or job.cancel.is_set():
                        job.status = "cancelled"
                        job.emit({"type": "cancelled"})
                    else:
                        job.status = "error"
                        job.error = {"message": str(e) or e.__class__.__name__,
                                     "chapter": getattr(e, "chapter", None),
                                     "detail": getattr(e, "detail", "")}
                        job.emit({"type": "error", **job.error})

        threading.Thread(target=run, name=f"job-{job.id}", daemon=True).start()
        return job

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

    def _trim(self) -> None:
        if len(self.jobs) <= self._keep:
            return
        for jid in sorted(self.jobs, key=lambda k: self.jobs[k].created)[: len(self.jobs) - self._keep]:
            if self.jobs[jid].status not in ("queued", "running"):
                self.jobs.pop(jid, None)
