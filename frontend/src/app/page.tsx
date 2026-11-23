import { Button } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="flex flex-1 flex-col items-center justify-center gap-6 px-6 text-center">
      <h1 className="text-4xl font-semibold tracking-tight">ViralSlice</h1>
      <p className="max-w-md text-muted-foreground">
        Transformez vos vidéos YouTube et clips Twitch en shorts 9:16 commentés
        par IA.
      </p>
      <Button disabled>Bientôt disponible</Button>
    </main>
  );
}
