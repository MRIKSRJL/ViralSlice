# ViralSlice — backend

API FastAPI et pipeline vidéo : URL YouTube/Twitch → 3 shorts 9:16 sous-titrés, avec voix off IA si nécessaire.

## Lancer

Prérequis : Python 3.12+, FFmpeg compilé avec libass (filtre `ass`).

```bash
cp .env.example .env          # renseigner OPENAI_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## API

| Méthode | Route | Rôle |
|---|---|---|
| `POST` | `/api/process-video` | Body `{"url": "...", "commentary_mode": "auto" \| "always" \| "never"}`. Lance le job en tâche de fond, répond `202` avec `job_id`. |
| `GET` | `/api/status/{job_id}` | Statut (`queued`, `downloading`, `transcribing`, `detecting_moments`, `rendering`, `completed`, `failed`), progression, moments et clips. |
| `GET` | `/api/jobs/{job_id}/clips/{index}` | Téléchargement du MP4 d'un clip terminé. |

Les clips sont écrits dans `MEDIA_ROOT/<job_id>/clip_<n>.mp4` ; les fichiers intermédiaires restent dans un dossier temporaire supprimé à la fin du job.

## Pipeline (`app/pipeline/`)

| Étape | Module |
|---|---|
| Téléchargement yt-dlp, 1080p max | `download.py` |
| Extraction audio (MP3 mono 16 kHz, découpé au-delà de 24 Mo) | `audio.py` |
| Transcription Whisper avec `timestamp_granularities=["word"]` | `transcription.py` |
| 3 moments viraux de 30 à 60 s + décision de commentaire (GPT-4o, JSON Schema strict) | `moments.py` |
| Voix off OpenAI TTS ou ElevenLabs (`TTS_PROVIDER`), puis transcription Whisper de la voix off | `tts.py` |
| Choix des mots sous-titrés : voix off tant qu'elle parle, puis audio original | `timeline.py` |
| Sous-titres `.ass` style TikTok : 3 mots max, mot prononcé en jaune | `subtitles.py` |
| Découpe, recadrage 9:16 centré, mixage (original à 22 % sous la voix off), incrustation `ass=` | `editing.py` |
| Orchestration et mise à jour du job | `runner.py` |

Modes de commentaire : `auto` (GPT-4o décide clip par clip, uniquement si le clip manque de contexte ou a besoin d'une accroche), `always` (voix off sur chaque clip), `never` (aucune voix off).

## Points d'attention

- **Police** : le style utilise Montserrat en gras. Si elle n'est pas installée, libass prend une police de secours. Placez `Montserrat-Bold.ttf` (Google Fonts) dans un dossier et indiquez-le dans `FONTS_DIR`.
- **YouTube** : depuis une IP de serveur, YouTube demande souvent une vérification anti-bot. Exportez des cookies au format Netscape et renseignez `YTDLP_COOKIES_FILE`.
- **Jobs en mémoire** : les jobs sont perdus au redémarrage et le serveur doit tourner en un seul processus. Le passage à PostgreSQL + Redis/RQ est prévu (PRD, section 5).

## Tests

```bash
pytest
```

Les tests de `tests/test_pipeline_ffmpeg.py` exécutent FFmpeg réellement (pipeline complet sur une vidéo synthétique, avec yt-dlp et OpenAI simulés) ; ils sont ignorés si FFmpeg est absent.
