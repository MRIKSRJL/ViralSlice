import { Suspense } from "react";

import { ClipGenerator, ClipGeneratorFromUrl } from "@/components/clip-generator";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-1 flex-col gap-10 px-5 py-12 sm:py-16">
      <header className="mx-auto flex max-w-2xl flex-col items-center gap-3 text-center">
        <span className="rounded-full border px-3 py-1 text-xs text-muted-foreground">
          YouTube & Twitch → TikTok, Reels, Shorts
        </span>
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">ViralSlice</h1>
        <p className="text-balance text-muted-foreground">
          Collez une URL : l&apos;IA repère les 3 meilleurs moments, les recadre en 9:16, ajoute des
          sous-titres dynamiques et, si besoin, une voix off.
        </p>
      </header>
      <Suspense fallback={<ClipGenerator />}>
        <ClipGeneratorFromUrl />
      </Suspense>
    </main>
  );
}
