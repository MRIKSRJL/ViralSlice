import { DownloadIcon, MicIcon, MicOffIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardFooter } from "@/components/ui/card";
import { type ClipResult, clipFileUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

function formatTime(seconds: number) {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function ClipCard({ clip }: { clip: ClipResult }) {
  const src = clipFileUrl(clip);
  return (
    <Card className="gap-0 overflow-hidden py-0">
      <video
        src={src}
        controls
        playsInline
        preload="metadata"
        className="aspect-[9/16] w-full bg-black object-cover"
      />
      <CardContent className="flex flex-1 flex-col gap-2 py-4">
        <div className="flex items-center justify-between gap-2">
          {clip.has_voiceover ? (
            <Badge>
              <MicIcon /> Voix off IA
            </Badge>
          ) : (
            <Badge variant="secondary">
              <MicOffIcon /> Sans voix off
            </Badge>
          )}
          <span className="text-xs text-muted-foreground tabular-nums">
            {formatTime(clip.start)} – {formatTime(clip.end)}
          </span>
        </div>
        <h3 className="font-medium leading-snug">{clip.title}</h3>
        {clip.commentary_script && (
          <p className="line-clamp-3 text-sm text-muted-foreground italic">
            « {clip.commentary_script} »
          </p>
        )}
      </CardContent>
      <CardFooter className="pb-4">
        <a href={src} download={clip.filename} className={cn(buttonVariants(), "w-full")}>
          <DownloadIcon /> Télécharger
        </a>
      </CardFooter>
    </Card>
  );
}
