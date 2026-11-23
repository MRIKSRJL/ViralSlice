from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.core.config import Settings, get_settings
from app.core.providers import ProviderConfigError, resolve_ai_profile
from app.jobs.store import InMemoryJobStore, JobNotFoundError, get_job_store
from app.models.schemas import JobState, ProcessVideoRequest, ProcessVideoResponse
from app.pipeline import runner

router = APIRouter(prefix="/api", tags=["pipeline"])

StoreDep = Annotated[InMemoryJobStore, Depends(get_job_store)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _get_job(store: InMemoryJobStore, job_id: str) -> JobState:
    try:
        return store.get(job_id)
    except JobNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job introuvable.") from None


@router.post(
    "/process-video",
    response_model=ProcessVideoResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def process_video(
    request: ProcessVideoRequest,
    background_tasks: BackgroundTasks,
    store: StoreDep,
    settings: SettingsDep,
) -> ProcessVideoResponse:
    try:
        resolve_ai_profile(settings)
    except ProviderConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    job = store.create(str(request.url), request.commentary_mode)
    background_tasks.add_task(
        runner.run_pipeline, job.job_id, job.url, job.commentary_mode, store, settings
    )
    return ProcessVideoResponse(job_id=job.job_id, status=job.status)


@router.get("/status/{job_id}", response_model=JobState)
def get_status(job_id: str, store: StoreDep) -> JobState:
    return _get_job(store, job_id)


@router.get("/jobs/{job_id}/clips/{index}", response_class=FileResponse)
def download_clip(
    job_id: str,
    index: int,
    store: StoreDep,
    settings: SettingsDep,
) -> FileResponse:
    job = _get_job(store, job_id)
    clip = next((c for c in job.clips if c.index == index), None)
    if clip is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Clip introuvable.")
    path = settings.media_root / job_id / clip.filename
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Fichier du clip introuvable.")
    return FileResponse(path, media_type="video/mp4", filename=clip.filename)
