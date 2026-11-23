import threading
import uuid
from datetime import UTC, datetime
from typing import Any

from app.models.schemas import CommentaryMode, JobState


class JobNotFoundError(KeyError):
    pass


class InMemoryJobStore:
    """Stockage des jobs en mémoire, partagé entre l'API et les tâches de fond.

    Les jobs sont perdus au redémarrage et ne sont pas partagés entre plusieurs
    processus : à remplacer par PostgreSQL + Redis/RQ (voir PRD.md, section 5).
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobState] = {}
        self._lock = threading.Lock()

    def create(self, url: str, commentary_mode: CommentaryMode) -> JobState:
        job = JobState(job_id=uuid.uuid4().hex, url=url, commentary_mode=commentary_mode)
        with self._lock:
            self._jobs[job.job_id] = job
        return job.model_copy(deep=True)

    def get(self, job_id: str) -> JobState:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            return job.model_copy(deep=True)

    def update(self, job_id: str, **fields: Any) -> JobState:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise JobNotFoundError(job_id)
            fields["updated_at"] = datetime.now(UTC)
            updated = job.model_copy(update=fields, deep=True)
            self._jobs[job_id] = updated
            return updated.model_copy(deep=True)


_store = InMemoryJobStore()


def get_job_store() -> InMemoryJobStore:
    return _store
