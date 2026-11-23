"use client";

import {
  AlertCircleIcon,
  LoaderCircleIcon,
  RotateCcwIcon,
  SparklesIcon,
  WifiOffIcon,
} from "lucide-react";
import { useSearchParams } from "next/navigation";
import { type FormEvent, useCallback, useEffect, useState } from "react";

import { ClipCard } from "@/components/clip-card";
import { JobProgress } from "@/components/job-progress";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ApiError,
  type CommentaryMode,
  type JobState,
  getJobStatus,
  isSupportedUrl,
  isTerminal,
  processVideo,
} from "@/lib/api";

const POLL_INTERVAL_MS = 3000;

const COMMENTARY_OPTIONS: Record<CommentaryMode, string> = {
  auto: "Auto (l'IA décide si nécessaire)",
  never: "Jamais (clip brut sous-titré)",
  always: "Toujours commenter",
};

function setJobInUrl(jobId: string | null) {
  const url = new URL(window.location.href);
  if (jobId) url.searchParams.set("job", jobId);
  else url.searchParams.delete("job");
  window.history.replaceState(null, "", url);
}

export function ClipGeneratorFromUrl() {
  const jobId = useSearchParams().get("job");
  return <ClipGenerator initialJobId={jobId} />;
}

export function ClipGenerator({ initialJobId = null }: { initialJobId?: string | null }) {
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<CommentaryMode>("auto");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(initialJobId);
  const [job, setJob] = useState<JobState | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const [fatalError, setFatalError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const state = await getJobStatus(jobId);
        if (cancelled) return;
        setJob(state);
        setPollError(null);
        if (isTerminal(state.status)) return;
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 404) {
          setFatalError(
            "Ce job est introuvable. Le serveur a peut-être redémarré : relancez la génération.",
          );
          return;
        }
        setPollError(error instanceof Error ? error.message : "Erreur réseau.");
      }
      timer = setTimeout(poll, POLL_INTERVAL_MS);
    };

    poll();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [jobId]);

  const reset = useCallback(() => {
    setJobId(null);
    setJob(null);
    setPollError(null);
    setFatalError(null);
    setJobInUrl(null);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = url.trim();
    if (!isSupportedUrl(trimmed)) {
      setFormError("Collez une URL YouTube ou Twitch valide.");
      return;
    }
    setFormError(null);
    setSubmitting(true);
    try {
      const created = await processVideo(trimmed, mode);
      setJob(null);
      setFatalError(null);
      setJobId(created.job_id);
      setJobInUrl(created.job_id);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : "Erreur inattendue.");
    } finally {
      setSubmitting(false);
    }
  }

  const running = jobId !== null && !fatalError && (!job || !isTerminal(job.status));

  return (
    <div className="flex flex-col gap-8">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <Card>
          <CardContent>
            <form onSubmit={onSubmit} className="flex flex-col gap-5" noValidate>
              <div className="flex flex-col gap-2">
                <Label htmlFor="video-url">URL de la vidéo</Label>
                <Input
                  id="video-url"
                  type="url"
                  inputMode="url"
                  placeholder="https://www.youtube.com/watch?v=… ou https://www.twitch.tv/…"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  aria-invalid={formError ? true : undefined}
                  disabled={running || submitting}
                  className="h-10"
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="commentary-mode">Voix off IA</Label>
                <Select
                  items={COMMENTARY_OPTIONS}
                  value={mode}
                  onValueChange={(value) => value && setMode(value as CommentaryMode)}
                  disabled={running || submitting}
                >
                  <SelectTrigger id="commentary-mode" className="h-10 w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(Object.keys(COMMENTARY_OPTIONS) as CommentaryMode[]).map((value) => (
                      <SelectItem key={value} value={value}>
                        {COMMENTARY_OPTIONS[value]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {formError && (
                <p role="alert" className="text-sm text-destructive">
                  {formError}
                </p>
              )}
              <Button type="submit" size="lg" className="h-10" disabled={running || submitting}>
                {submitting || running ? (
                  <LoaderCircleIcon className="animate-spin" />
                ) : (
                  <SparklesIcon />
                )}
                {running ? "Génération en cours…" : "Générer les clips"}
              </Button>
            </form>
          </CardContent>
        </Card>

        {pollError && running && (
          <Alert>
            <WifiOffIcon />
            <AlertTitle>Connexion à l&apos;API perdue</AlertTitle>
            <AlertDescription>
              {pollError} Nouvelle tentative dans quelques secondes…
            </AlertDescription>
          </Alert>
        )}

        {fatalError && (
          <Alert variant="destructive">
            <AlertCircleIcon />
            <AlertTitle>Suivi impossible</AlertTitle>
            <AlertDescription>{fatalError}</AlertDescription>
          </Alert>
        )}

        {jobId && !job && !fatalError && (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <LoaderCircleIcon className="size-4 animate-spin" /> Récupération du statut…
          </p>
        )}

        {job && !isTerminal(job.status) && <JobProgress job={job} />}

        {job?.status === "failed" && (
          <Alert variant="destructive">
            <AlertCircleIcon />
            <AlertTitle>La génération a échoué</AlertTitle>
            <AlertDescription>{job.error ?? "Erreur inconnue."}</AlertDescription>
          </Alert>
        )}
      </div>

      {job && job.clips.length > 0 && (
        <section className="flex flex-col gap-4">
          <div className="flex items-baseline justify-between gap-4">
            <h2 className="text-lg font-semibold">
              {job.status === "completed" ? "Vos clips" : "Premiers clips prêts"}
            </h2>
            {job.source_title && (
              <p className="truncate text-sm text-muted-foreground">{job.source_title}</p>
            )}
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {job.clips.map((clip) => (
              <ClipCard key={clip.index} clip={clip} />
            ))}
          </div>
        </section>
      )}

      {(fatalError || (job && isTerminal(job.status))) && (
        <Button variant="outline" className="self-center" onClick={reset}>
          <RotateCcwIcon /> Nouvelle vidéo
        </Button>
      )}
    </div>
  );
}
