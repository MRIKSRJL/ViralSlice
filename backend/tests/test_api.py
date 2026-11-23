import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.jobs.store import InMemoryJobStore, get_job_store
from app.main import app
from app.models.schemas import ClipResult, JobStatus
from app.pipeline import runner


@pytest.fixture
def store():
    return InMemoryJobStore()


@pytest.fixture
def client(store, tmp_path):
    settings = Settings(openai_api_key="test", media_root=tmp_path)
    app.dependency_overrides[get_job_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_process_video_runs_pipeline_in_background(client, store, tmp_path, monkeypatch):
    calls = []

    def fake_pipeline(job_id, url, mode, job_store, settings):
        calls.append((url, mode))
        (tmp_path / job_id).mkdir()
        (tmp_path / job_id / "clip_1.mp4").write_bytes(b"mp4")
        clip = ClipResult(
            index=1, start=0, end=30, title="t", reason="r", needs_commentary=False,
            commentary_script=None, has_voiceover=False, filename="clip_1.mp4",
            download_url=runner.clip_download_url(job_id, 1),
        )  # fmt: skip
        job_store.update(job_id, status=JobStatus.COMPLETED, progress=100, clips=[clip])

    monkeypatch.setattr(runner, "run_pipeline", fake_pipeline)
    response = client.post(
        "/api/process-video",
        json={"url": "https://www.youtube.com/watch?v=abc", "commentary_mode": "never"},
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    assert response.json()["status"] == "queued"
    assert calls == [("https://www.youtube.com/watch?v=abc", "never")]

    status = client.get(f"/api/status/{job_id}").json()
    assert status["status"] == "completed"
    assert status["clips"][0]["download_url"] == f"/api/jobs/{job_id}/clips/1"

    download = client.get(status["clips"][0]["download_url"])
    assert download.status_code == 200 and download.content == b"mp4"
    assert client.get(f"/api/jobs/{job_id}/clips/2").status_code == 404


def test_default_commentary_mode_is_auto(client, monkeypatch):
    seen = []
    monkeypatch.setattr(runner, "run_pipeline", lambda *args: seen.append(args[2]))
    response = client.post("/api/process-video", json={"url": "https://clips.twitch.tv/SomeClip"})
    assert response.status_code == 202
    assert seen == ["auto"]


@pytest.mark.parametrize(
    "body",
    [
        {"url": "https://vimeo.com/123"},
        {"url": "pas une url"},
        {"url": "https://youtu.be/abc", "commentary_mode": "parfois"},
    ],
)
def test_process_video_rejects_invalid_input(client, body):
    assert client.post("/api/process-video", json=body).status_code == 422


def test_process_video_requires_openai_key(store, tmp_path):
    app.dependency_overrides[get_job_store] = lambda: store
    app.dependency_overrides[get_settings] = lambda: Settings(
        openai_api_key="", media_root=tmp_path
    )
    try:
        response = TestClient(app).post("/api/process-video", json={"url": "https://youtu.be/abc"})
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503


def test_unknown_job_returns_404(client):
    assert client.get("/api/status/inconnu").status_code == 404
