# ViralSlice — backend

API FastAPI et pipeline vidéo : URL YouTube/Twitch → 3 shorts 9:16 sous-titrés, avec voix off IA si nécessaire.

## Lancer

Prérequis : Python 3.12+, FFmpeg compilé avec libass (filtre `ass`).

```bash
cp .env.example .env          # renseigner GROQ_API_KEY (gratuit) ou OPENAI_API_KEY
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Fournisseurs IA

| | Groq (gratuit, sans carte) | OpenAI (payant) |
|---|---|---|
| Activation | `GROQ_API_KEY` seule, ou `AI_PROVIDER=groq` | `OPENAI_API_KEY` renseignée, ou `AI_PROVIDER=openai` |
| Transcription au mot | `whisper-large-v3-turbo` | `whisper-1` |
| Moments + script (JSON Schema strict) | `openai/gpt-oss-120b` | `gpt-4o` |
| Voix off (si commentaire) | edge-tts, voix `fr-FR-RemyMultilingualNeural`, sans compte | OpenAI TTS `gpt-4o-mini-tts` |

Groq est appelé via son API compatible OpenAI (même SDK `openai`, autre `base_url`). `TTS_PROVIDER` force la voix off (`edge`, `openai` ou `elevenlabs`, qui reste optionnel).

### Test gratuit

1. Créez un compte sur [console.groq.com](https://console.groq.com) (aucune carte demandée), puis une clé dans **API Keys** ([console.groq.com/keys](https://console.groq.com/keys)).
2. Dans `backend/.env`, laissez `OPENAI_API_KEY` vide et renseignez `GROQ_API_KEY=gsk_...`.
3. Lancez le backend puis le frontend (`npm run dev` dans `frontend/`) et collez une URL Twitch (YouTube peut exiger `YTDLP_COOKIES_FILE` depuis un serveur).

Limites de l'offre gratuite Groq (d'après sa documentation ; les valeurs exactes sont sur [console.groq.com/settings/limits](https://console.groq.com/settings/limits)) : environ 2 h d'audio transcrit par heure et 8 h par jour ; 8 000 tokens par minute et 1 000 requêtes par jour pour `gpt-oss-120b`. Au-delà d'environ 14 000 caractères (une quinzaine de minutes de parole), la transcription envoyée au LLM est réduite à des extraits répartis sur toute la vidéo (`GROQ_MAX_TRANSCRIPT_CHARS`). En cas de dépassement, Groq répond 429 et le SDK réessaie automatiquement.

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
| 3 moments viraux de 30 à 60 s + décision de commentaire (GPT-4o ou gpt-oss-120b, JSON Schema strict) | `moments.py` |
| Voix off edge-tts, OpenAI TTS ou ElevenLabs, puis transcription Whisper de la voix off | `tts.py` |
| Choix des mots sous-titrés : voix off tant qu'elle parle, puis audio original | `timeline.py` |
| Sous-titres `.ass` style TikTok : 3 mots max, mot prononcé en jaune | `subtitles.py` |
| Découpe, recadrage 9:16 centré, mixage (original à 22 % sous la voix off), incrustation `ass=` | `editing.py` |
| Orchestration et mise à jour du job | `runner.py` |
| Choix du fournisseur IA et de la voix off | `app/core/providers.py` |

Modes de commentaire : `auto` (le LLM décide clip par clip, uniquement si le clip manque de contexte ou a besoin d'une accroche), `always` (voix off sur chaque clip), `never` (aucune voix off).

## Points d'attention

- **Police** : le style utilise Montserrat en gras. Si elle n'est pas installée, libass prend une police de secours. Placez `Montserrat-Bold.ttf` (Google Fonts) dans un dossier et indiquez-le dans `FONTS_DIR`.
- **YouTube** : depuis une IP de serveur, YouTube demande souvent une vérification anti-bot. Exportez des cookies au format Netscape et renseignez `YTDLP_COOKIES_FILE`.
- **Jobs en mémoire** : les jobs sont perdus au redémarrage et le serveur doit tourner en un seul processus. Le passage à PostgreSQL + Redis/RQ est prévu (PRD, section 5).

## Tests

```bash
pytest
```

Les tests de `tests/test_pipeline_ffmpeg.py` exécutent FFmpeg réellement (pipeline complet sur une vidéo synthétique, avec yt-dlp, OpenAI/Groq et edge-tts simulés) ; ils sont ignorés si FFmpeg est absent.
