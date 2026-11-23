import { CheckIcon, LoaderCircleIcon } from "lucide-react";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { JobState, JobStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STEPS: { status: JobStatus; label: string }[] = [
  { status: "downloading", label: "Téléchargement de la vidéo" },
  { status: "transcribing", label: "Transcription de l'audio" },
  { status: "detecting_moments", label: "Détection des moments viraux" },
  { status: "rendering", label: "Montage et sous-titrage des clips" },
];

function stepState(job: JobState, index: number): "done" | "current" | "todo" {
  if (job.status === "completed") return "done";
  const current = STEPS.findIndex((step) => step.status === job.status);
  if (current === -1) return "todo";
  if (index < current) return "done";
  return index === current ? "current" : "todo";
}

function headline(job: JobState) {
  if (job.status === "queued") return "En file d'attente…";
  if (job.status === "rendering" && job.moments.length > 0) {
    const n = Math.min(job.clips.length + 1, job.moments.length);
    return `Montage du clip ${n} sur ${job.moments.length}…`;
  }
  return `${STEPS.find((step) => step.status === job.status)?.label ?? "Traitement"}…`;
}

export function JobProgress({ job }: { job: JobState }) {
  return (
    <Card aria-live="polite">
      <CardHeader>
        <CardTitle>{headline(job)}</CardTitle>
        <CardDescription className="truncate">{job.source_title ?? job.url}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-5">
        <Progress value={job.progress} aria-label="Progression" />
        <ol className="grid gap-3 sm:grid-cols-2">
          {STEPS.map((step, index) => {
            const state = stepState(job, index);
            return (
              <li
                key={step.status}
                data-state={state}
                className={cn(
                  "flex items-center gap-2.5 text-sm",
                  state === "todo" ? "text-muted-foreground" : "text-foreground",
                )}
              >
                <span
                  className={cn(
                    "flex size-6 shrink-0 items-center justify-center rounded-full border",
                    state === "done" && "border-primary bg-primary text-primary-foreground",
                    state === "current" && "border-primary text-primary",
                  )}
                >
                  {state === "done" ? (
                    <CheckIcon className="size-3.5" />
                  ) : state === "current" ? (
                    <LoaderCircleIcon className="size-3.5 animate-spin" />
                  ) : (
                    <span className="text-xs">{index + 1}</span>
                  )}
                </span>
                {step.label}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}
