export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export type CommentaryMode = "auto" | "always" | "never";

export type JobStatus =
  | "queued"
  | "downloading"
  | "transcribing"
  | "detecting_moments"
  | "rendering"
  | "completed"
  | "failed";

export interface ViralMoment {
  start: number;
  end: number;
  title: string;
  reason: string;
  needs_commentary: boolean;
  commentary_script: string | null;
}

export interface ClipResult {
  index: number;
  start: number;
  end: number;
  title: string;
  reason: string;
  needs_commentary: boolean;
  commentary_script: string | null;
  has_voiceover: boolean;
  filename: string;
  download_url: string;
}

export interface JobState {
  job_id: string;
  url: string;
  commentary_mode: CommentaryMode;
  status: JobStatus;
  progress: number;
  source_title: string | null;
  source_duration: number | null;
  moments: ViralMoment[];
  clips: ClipResult[];
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProcessVideoResponse {
  job_id: string;
  status: JobStatus;
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
  }
}

function detailMessage(body: unknown): string | null {
  if (!body || typeof body !== "object" || !("detail" in body)) return null;
  const { detail } = body as { detail: unknown };
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: unknown };
    if (typeof first.msg === "string") return first.msg.replace(/^Value error, /, "");
  }
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError("Impossible de joindre l'API. Vérifiez que le backend est démarré.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(
      detailMessage(body) ?? `Erreur inattendue de l'API (${response.status}).`,
      response.status,
    );
  }
  return body as T;
}

export function processVideo(url: string, commentaryMode: CommentaryMode) {
  return request<ProcessVideoResponse>("/api/process-video", {
    method: "POST",
    body: JSON.stringify({ url, commentary_mode: commentaryMode }),
  });
}

export function getJobStatus(jobId: string) {
  return request<JobState>(`/api/status/${encodeURIComponent(jobId)}`);
}

export function clipFileUrl(clip: ClipResult) {
  return `${API_URL}${clip.download_url}`;
}

const SUPPORTED_HOSTS = new Set([
  "youtube.com",
  "www.youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtu.be",
  "twitch.tv",
  "www.twitch.tv",
  "m.twitch.tv",
  "clips.twitch.tv",
]);

export function isSupportedUrl(value: string) {
  try {
    const url = new URL(value);
    return (
      (url.protocol === "https:" || url.protocol === "http:") &&
      SUPPORTED_HOSTS.has(url.hostname.toLowerCase())
    );
  } catch {
    return false;
  }
}

export function isTerminal(status: JobStatus) {
  return status === "completed" || status === "failed";
}
