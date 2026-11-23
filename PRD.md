# ViralSlice — Product Requirements Document

## 1. Vision

ViralSlice transforme une vidéo longue (YouTube) ou un clip Twitch en plusieurs shorts verticaux 9:16 prêts à publier sur TikTok, Instagram Reels et YouTube Shorts. Chaque short contient le meilleur moment de la source, une voix off de commentaire générée par IA et des sous-titres incrustés.

**Utilisateurs cibles** : créateurs de contenu, streamers, monteurs et agences qui veulent recycler des contenus longs en formats courts sans passer par un logiciel de montage.

**Proposition de valeur** : coller une URL, choisir un ton de commentaire, récupérer en quelques minutes 3 à 5 shorts montés, sous-titrés et commentés.

## 2. Parcours utilisateur (MVP)

1. L'utilisateur se connecte et colle une URL YouTube ou Twitch (clip ou VOD).
2. Il choisit les options : langue, ton du commentaire (humour, analyse, hype, neutre), voix, nombre de clips (1 à 5), durée cible (15, 30 ou 60 s), style de sous-titres.
3. Il lance la génération. Un job est créé et la page affiche la progression étape par étape.
4. À la fin, il voit la liste des clips générés avec aperçu, titre proposé, score viral, script du commentaire et bouton de téléchargement MP4.
5. Il peut relancer un clip avec un autre ton ou une autre voix (régénère seulement les étapes 4 à 8 du pipeline).

## 3. Architecture

```
┌────────────────────┐   HTTPS/JSON    ┌─────────────────────┐
│ Frontend Next.js   │ ──────────────▶ │ API FastAPI         │
│ App Router, shadcn │ ◀────────────── │ (auth, jobs, clips) │
└────────────────────┘  polling / SSE  └──────────┬──────────┘
                                                  │ enqueue
                                       ┌──────────▼──────────┐
                                       │ Redis (file RQ)     │
                                       └──────────┬──────────┘
                                                  │ consume
                                       ┌──────────▼──────────┐      ┌──────────────────┐
                                       │ Workers Python      │ ───▶ │ OpenAI           │
                                       │ yt-dlp, FFmpeg      │      │ Whisper, GPT-4o, │
                                       │ pipeline vidéo      │      │ TTS / ElevenLabs │
                                       └───┬────────────┬────┘      └──────────────────┘
                                           │            │
                                ┌──────────▼───┐  ┌─────▼───────────────┐
                                │ PostgreSQL   │  │ Stockage médias     │
                                │ (métadonnées)│  │ local (dev) / S3    │
                                └──────────────┘  └─────────────────────┘
```

### 3.1 Répartition frontend / backend

| Responsabilité | Frontend (`/frontend`) | Backend (`/backend`) |
|---|---|---|
| Interface, formulaires, aperçus vidéo | Oui | Non |
| Authentification | Session côté client, appels avec jeton | Vérification du jeton, propriété des ressources |
| Validation des URL | Validation de format | Validation complète (domaine, durée, disponibilité) |
| Création et suivi des jobs | Appelle l'API, affiche la progression | Crée le job, l'empile, met à jour le statut |
| Traitement vidéo et IA | Jamais | Workers uniquement |
| Clés API OpenAI / ElevenLabs | Jamais exposées | Variables d'environnement serveur |
| Fichiers médias | Lit des URL signées | Écrit et signe les URL |

Le frontend ne parle qu'à l'API FastAPI. Il n'appelle jamais OpenAI, ElevenLabs ou yt-dlp directement.

### 3.2 Arborescence cible du backend

```
backend/app/
  main.py          Application FastAPI, CORS, routes
  api/             Routes HTTP : jobs, clips, voix, santé
  models/          Modèles SQLAlchemy + schémas Pydantic
  pipeline/        Une fonction par étape (download, transcribe, detect, script, tts, edit, subtitles, export)
  workers/         Points d'entrée RQ qui enchaînent les étapes
```

## 4. Pipeline de traitement vidéo

Chaque étape lit ses entrées depuis le stockage, écrit ses sorties dans `media/<job_id>/`, met à jour `jobs.current_step` et `jobs.progress`, et peut être rejouée seule (idempotence par fichier de sortie). Les étapes 1 à 3 sont faites une fois par job ; les étapes 4 à 8 une fois par clip.

### Étape 1 — Téléchargement (yt-dlp)

- Entrée : URL YouTube ou Twitch.
- Lecture des métadonnées d'abord (`--dump-json`) pour refuser les vidéos trop longues (`MAX_SOURCE_DURATION_SECONDS`), privées ou en direct.
- Téléchargement au format MP4 1080p maximum : `-f "bv*[height<=1080]+ba/b" --merge-output-format mp4`.
- Extraction de la piste audio en WAV mono 16 kHz pour Whisper : `ffmpeg -i source.mp4 -ac 1 -ar 16000 audio.wav`.
- Sorties : `source.mp4`, `audio.wav`, `metadata.json` (titre, chaîne, durée, miniature).

### Étape 2 — Transcription (Whisper)

- MVP : API OpenAI (`whisper-1`) avec `response_format="verbose_json"` et `timestamp_granularities=["word", "segment"]` pour obtenir des horodatages au mot.
- L'API limite les fichiers à 25 Mo : l'audio est découpé en morceaux d'environ 10 minutes (compressé en MP3/Opus), puis les horodatages sont recalés et fusionnés.
- Option auto-hébergée : `openai-whisper` local sur GPU (désactivée par défaut, voir `requirements.txt`).
- Sortie : `transcript.json` (segments + mots avec `start`, `end`, `text`) et la langue détectée.

### Étape 3 — Détection des moments viraux (GPT-4o)

- Entrée : transcription segmentée avec horodatages, métadonnées, options (nombre de clips, durée cible, langue).
- Prompt GPT-4o en mode sortie structurée (JSON Schema) qui renvoie une liste de candidats : `start`, `end`, `title`, `hook` (accroche des 3 premières secondes), `reason`, `viral_score` (0 à 100).
- Post-traitement côté code : recalage des bornes sur des frontières de phrase, respect de la durée cible (±20 %), suppression des chevauchements, tri par score, conservation des N meilleurs.
- Les longues transcriptions sont traitées par fenêtres glissantes, puis un second appel classe les meilleurs candidats.
- Sortie : `moments.json` et une ligne `clips` par moment retenu (statut `pending`).

### Étape 4 — Écriture du script de commentaire (GPT-4o)

- Entrée : extrait de transcription du moment, ton choisi, langue, durée du clip.
- GPT-4o rédige un commentaire court en sortie structurée : `intro` (accroche avant ou par-dessus le début), `interjections` (liste de `{at, text}` placées dans les silences), `outro` (appel à l'action).
- Contrainte de longueur : environ 2,5 mots par seconde, en limitant la voix off à 40 % de la durée pour laisser entendre l'original.
- Les silences sont détectés à partir des horodatages au mot (trous de plus de 0,8 s) pour positionner les interjections.
- Sortie : `clips/<clip_id>/script.json`.

### Étape 5 — Synthèse vocale (OpenAI TTS ou ElevenLabs)

- Fournisseur choisi par `TTS_PROVIDER` (`openai` par défaut, `elevenlabs` pour les voix premium).
- Une piste audio par bloc du script (intro, chaque interjection, outro), au format MP3 ou WAV.
- La durée réelle de chaque piste est mesurée avec `ffprobe` ; si un bloc dépasse son créneau, il est accéléré (filtre `atempo` jusqu'à 1,15) ou réécrit plus court.
- Sorties : `clips/<clip_id>/tts/*.mp3` et `tts_timeline.json` (bloc, début, durée).

### Étape 6 — Recadrage 9:16 et montage (FFmpeg)

- Découpe précise du moment : `-ss <start> -to <end>` avec réencodage (pas de copie de flux, pour éviter les décalages d'images clés).
- Recadrage vertical 1080×1920 :
  - MVP : recadrage centré `crop=ih*9/16:ih,scale=1080:1920`, ou mode « fond flou » (vidéo d'origine en 16:9 au centre, version agrandie et floutée en fond) pour les contenus où le centre ne suffit pas (gaming, facecam).
  - V2 : suivi du visage ou du locuteur (détection de visages image par image et lissage de la position de recadrage).
- Mixage audio : audio original atténué (ducking via `sidechaincompress` ou `volume` à environ 25 %) pendant la voix off, voix off placée selon `tts_timeline.json` avec `adelay` puis `amix`.
- Normalisation du volume final : `loudnorm` (cible -14 LUFS, standard des plateformes sociales).
- Sortie : `clips/<clip_id>/edit.mp4`.

### Étape 7 — Sous-titres incrustés

- Sous-titres générés à partir des horodatages au mot de Whisper (audio original) et des textes TTS (voix off), recalés sur le début du clip.
- Format ASS pour le style : 2 à 4 mots par ligne, police épaisse, contour noir, mot en cours surligné (effet karaoké), placés au tiers inférieur hors zone d'interface des plateformes.
- Incrustation avec FFmpeg : filtre `subtitles=subs.ass` (libass).
- Sortie : `clips/<clip_id>/subs.ass`, `clips/<clip_id>/subtitled.mp4`.

### Étape 8 — Export

- Encodage final : H.264 (`libx264`, `-crf 20`, `-preset medium`), AAC 192 kb/s, 30 images/s, `-movflags +faststart`, 1080×1920.
- Génération d'une miniature (image du hook) et d'un aperçu basse définition.
- Envoi vers le stockage (local en dev, S3 compatible en prod) et URL signée à durée limitée.
- Mise à jour du clip (`status=ready`, `video_url`, `thumbnail_url`, `duration`), puis du job quand tous les clips sont terminés.
- Nettoyage : suppression de `source.mp4` et des fichiers intermédiaires après 24 h.

## 5. Jobs et file d'attente

- **Outil** : Redis + RQ. Plus simple que Celery pour un MVP, avec retries et timeouts par job. Le passage à Celery ou Dramatiq reste possible si le besoin d'orchestration grandit.
- **Files** : `default` pour les étapes légères et appels API (transcription, GPT-4o, TTS) ; `video` pour yt-dlp et FFmpeg, consommée par des workers dimensionnés en CPU.
- **Orchestration** : un job `process_source(job_id)` exécute les étapes 1 à 3 puis empile un job `render_clip(clip_id)` par moment retenu (traitement en parallèle).
- **Statuts du job** : `queued` → `downloading` → `transcribing` → `detecting` → `rendering` → `completed` | `failed` | `canceled`.
- **Statuts d'un clip** : `pending` → `scripting` → `voicing` → `editing` → `subtitling` → `exporting` → `ready` | `failed`.
- **Progression** : chaque étape écrit `current_step` et `progress` (0 à 100) en base ; le frontend interroge `GET /jobs/{id}` toutes les 2 à 3 s (Server-Sent Events en V2).
- **Fiabilité** : 3 tentatives avec backoff exponentiel sur les appels réseau (yt-dlp, OpenAI, ElevenLabs), timeout par étape, message d'erreur lisible enregistré dans `jobs.error`.
- **Limites** : un job actif à la fois par utilisateur en gratuit, quota mensuel de minutes traitées.

## 6. Modèle de données (esquisse)

```
users
  id              uuid PK
  email           text unique
  plan            text            -- free | pro
  minutes_used    int
  created_at      timestamptz

jobs
  id              uuid PK
  user_id         uuid FK users
  source_url      text
  source_platform text            -- youtube | twitch
  source_title    text
  source_duration int             -- secondes
  options         jsonb           -- langue, ton, voix, nb_clips, durée cible, style sous-titres
  status          text
  current_step    text
  progress        int
  error           text null
  created_at      timestamptz
  updated_at      timestamptz

clips
  id              uuid PK
  job_id          uuid FK jobs
  start_time      float
  end_time        float
  title           text
  hook            text
  viral_score     int
  script          jsonb           -- intro, interjections, outro
  voice_provider  text            -- openai | elevenlabs
  voice_id        text
  status          text
  video_url       text null
  thumbnail_url   text null
  duration        float null
  error           text null
  created_at      timestamptz
  updated_at      timestamptz

assets
  id              uuid PK
  job_id          uuid FK jobs
  clip_id         uuid FK clips null
  kind            text            -- source | audio | transcript | tts | edit | subtitles | final
  storage_key     text
  size_bytes      bigint
  created_at      timestamptz
```

## 7. Endpoints API (esquisse)

| Méthode | Route | Rôle |
|---|---|---|
| `GET` | `/health` | Santé de l'API (déjà en place) |
| `POST` | `/jobs` | Crée un job à partir d'une URL et d'options, l'empile, renvoie `{id, status}` |
| `GET` | `/jobs` | Liste paginée des jobs de l'utilisateur |
| `GET` | `/jobs/{job_id}` | Statut, étape, progression, métadonnées source et clips |
| `POST` | `/jobs/{job_id}/cancel` | Annule un job en cours |
| `DELETE` | `/jobs/{job_id}` | Supprime le job et ses médias |
| `GET` | `/jobs/{job_id}/clips` | Liste des clips du job |
| `GET` | `/clips/{clip_id}` | Détail d'un clip (script, score, URL vidéo) |
| `POST` | `/clips/{clip_id}/regenerate` | Relance les étapes 4 à 8 avec un nouveau ton ou une nouvelle voix |
| `GET` | `/clips/{clip_id}/download` | Redirige vers une URL signée du MP4 final |
| `GET` | `/voices` | Voix disponibles (OpenAI + ElevenLabs) |
| `POST` | `/sources/preview` | Valide une URL et renvoie titre, durée, miniature avant création du job |

Exemple de corps pour `POST /jobs` :

```json
{
  "source_url": "https://www.youtube.com/watch?v=...",
  "options": {
    "language": "fr",
    "tone": "humour",
    "voice_provider": "openai",
    "voice_id": "alloy",
    "clip_count": 3,
    "target_duration": 30,
    "subtitle_style": "karaoke"
  }
}
```

## 8. Variables d'environnement

**Backend** (`backend/.env.example`)

| Variable | Rôle |
|---|---|
| `APP_ENV`, `API_HOST`, `API_PORT` | Environnement et écoute du serveur |
| `CORS_ORIGINS` | Origines autorisées (URL du frontend) |
| `DATABASE_URL` | Connexion PostgreSQL |
| `REDIS_URL` | Connexion Redis pour RQ |
| `OPENAI_API_KEY` | Clé OpenAI (Whisper, GPT-4o, TTS) |
| `OPENAI_LLM_MODEL` | Modèle de détection et d'écriture (`gpt-4o`) |
| `OPENAI_TRANSCRIPTION_MODEL` | Modèle de transcription (`whisper-1`) |
| `OPENAI_TTS_MODEL`, `OPENAI_TTS_VOICE` | Modèle et voix TTS OpenAI |
| `TTS_PROVIDER` | `openai` ou `elevenlabs` |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | Accès et voix ElevenLabs |
| `STORAGE_BACKEND`, `MEDIA_ROOT` | Stockage local ou S3, dossier local |
| `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | Stockage objet compatible S3 |
| `MAX_SOURCE_DURATION_SECONDS`, `MAX_CLIPS_PER_JOB` | Garde-fous du pipeline |
| `FFMPEG_BINARY` | Chemin de l'exécutable FFmpeg |

**Frontend** (`frontend/.env.example`)

| Variable | Rôle |
|---|---|
| `NEXT_PUBLIC_API_URL` | URL de l'API appelée depuis le navigateur |
| `API_URL` | URL de l'API appelée côté serveur Next.js |

## 9. Périmètre MVP

**Inclus**

- Sources : URL YouTube publiques et clips/VOD Twitch publics, 60 minutes maximum.
- Pipeline complet des étapes 1 à 8, 1 à 5 clips par job, durée cible 15, 30 ou 60 s.
- Recadrage centré et mode fond flou.
- Voix off OpenAI TTS (ElevenLabs derrière un flag de configuration).
- Sous-titres incrustés avec un style par défaut et un style karaoké.
- Tableau de bord : création de job, suivi de progression, aperçu et téléchargement des clips.
- Authentification simple (e-mail / magic link) et quota de minutes par utilisateur.

**Hors MVP (V2+)**

- Recadrage intelligent par suivi de visage ou de locuteur.
- Éditeur de clip dans le navigateur (bornes, texte des sous-titres, script).
- Upload direct de fichiers vidéo.
- Publication automatique sur TikTok, Instagram et YouTube.
- Clonage de voix, musique de fond, B-roll généré.
- Paiement Stripe, équipes et espaces de travail.
- Progression en temps réel par Server-Sent Events ou WebSocket.

## 10. Risques et points d'attention

- **Droits d'auteur et CGU** : le téléchargement de contenus YouTube/Twitch doit être limité aux contenus dont l'utilisateur détient les droits ou une autorisation ; prévoir une case d'acceptation et une politique de retrait.
- **Fiabilité de yt-dlp** : les plateformes changent souvent ; mettre à jour la dépendance régulièrement et surveiller le taux d'échec de l'étape 1.
- **Coûts IA** : Whisper est facturé à la minute audio, GPT-4o au token, TTS au caractère ; suivre le coût par job et l'imputer au quota.
- **Temps de traitement** : FFmpeg est l'étape la plus coûteuse en CPU ; dimensionner les workers `video` séparément.
- **Stockage** : vidéos lourdes ; politique de rétention (sources supprimées après 24 h, clips finaux après 30 jours en gratuit).
