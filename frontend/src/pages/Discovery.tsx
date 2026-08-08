import { useEffect, useState } from "react";
import { api } from "../api";
import type { DiscoverResult, Track } from "../types";
import { Badge, Button, Card, EmptyState, Input, Label, Spinner } from "../components/ui";
import { cn } from "../components/ui";

export default function Discovery() {
  const [genres, setGenres] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>(["lo-fi", "indie"]);
  const [maxTracks, setMaxTracks] = useState(10);
  const [windowDays, setWindowDays] = useState(365);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [preview, setPreview] = useState<Track[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<string[]>("/spotify/genres")
      .then(setGenres)
      .catch(() => setGenres([]));
  }, []);

  function toggleGenre(g: string) {
    setSelected((s) => (s.includes(g) ? s.filter((x) => x !== g) : [...s, g]));
  }

  async function run() {
    setBusy(true);
    setError("");
    setResult(null);
    setPreview([]);
    try {
      const body = {
        genres: selected,
        max_tracks: maxTracks,
        release_window_days: windowDays,
        min_freshness: 0,
      };
      const res = await api.post<DiscoverResult>("/spotify/discover", body);
      setResult(res);
      const tracks = await api.get<Track[]>("/tracks");
      setPreview(tracks.slice(0, 8));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Discovery failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-white">Discover music</h1>
        <p className="text-sm text-slate-400">
          Metadata-only search for low-exposure indie tracks. No audio is captured.
        </p>
      </header>

      <Card>
        <div className="grid gap-5 md:grid-cols-3">
          <div className="md:col-span-2">
            <Label>Genres</Label>
            <div className="flex flex-wrap gap-2">
              {(genres.length ? genres : ["lo-fi", "indie", "ambient", "electronic"]).map(
                (g) => (
                  <button
                    key={g}
                    type="button"
                    onClick={() => toggleGenre(g)}
                    className={cn(
                      "rounded-full px-3 py-1 text-xs font-semibold transition-colors",
                      selected.includes(g)
                        ? "bg-accent text-white"
                        : "bg-surface-800 text-slate-400 hover:text-slate-200"
                    )}
                  >
                    {g}
                  </button>
                )
              )}
            </div>
          </div>
          <div className="space-y-3">
            <div>
              <Label htmlFor="max">Max tracks</Label>
              <Input
                id="max"
                type="number"
                min={1}
                max={50}
                value={maxTracks}
                onChange={(e) => setMaxTracks(Number(e.target.value))}
              />
            </div>
            <div>
              <Label htmlFor="win">Release window (days)</Label>
              <Input
                id="win"
                type="number"
                min={30}
                max={2000}
                value={windowDays}
                onChange={(e) => setWindowDays(Number(e.target.value))}
              />
            </div>
            <Button onClick={run} loading={busy} className="w-full">
              Run discovery
            </Button>
          </div>
        </div>
        {error && (
          <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">
            {error}
          </p>
        )}
      </Card>

      {busy && (
        <Card className="flex items-center justify-center gap-3 py-10 text-sm text-slate-400">
          <Spinner /> Scanning the (mock) catalog…
        </Card>
      )}

      {result && !busy && (
        <Card>
          <div className="mb-4 grid grid-cols-3 gap-4">
            <div>
              <p className="text-2xl font-extrabold text-accent-soft">{result.discovered}</p>
              <p className="text-xs text-slate-400">candidates found</p>
            </div>
            <div>
              <p className="text-2xl font-extrabold text-mint">{result.new_tracks}</p>
              <p className="text-xs text-slate-400">new tracks saved</p>
            </div>
            <div>
              <p className="text-2xl font-extrabold text-slate-200">
                {result.scoring_summary.provider}
              </p>
              <p className="text-xs text-slate-400">provider</p>
            </div>
          </div>

          {preview.length > 0 && (
                      <div>
                        <h3 className="mb-3 text-sm font-bold text-slate-200">Top picks</h3>
              <ul className="divide-y divide-surface-800">
                {preview.map((t) => (
                  <li key={t.id} className="flex items-center gap-3 py-2.5">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-slate-200">
                        {t.track_name}{" "}
                        <span className="text-slate-500">— {t.artist_name}</span>
                      </p>
                      <p className="text-xs text-slate-500">
                        {t.genre ?? "unknown genre"} · score{" "}
                        {t.discovery_score != null ? t.discovery_score.toFixed(2) : "—"}
                      </p>
                    </div>
                    <Badge tone="violet">{t.exposure_label ?? "new"}</Badge>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}

      {!result && !busy && (
        <EmptyState
          title="Nothing scanned yet"
          hint="Pick genres and run your first discovery pass."
        />
      )}
    </div>
  );
}