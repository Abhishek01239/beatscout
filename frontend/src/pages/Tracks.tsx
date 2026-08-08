import { useEffect, useRef, useState } from "react";
import { api, assetUrl } from "../api";
import type { Track } from "../types";
import { Badge, Button, Card, EmptyState, Input, Spinner } from "../components/ui";
import { RightsBadge } from "./Dashboard";

export default function Tracks() {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const fileRefs = useRef<Record<number, HTMLInputElement | null>>({});

  useEffect(() => {
    api
      .get<Track[]>("/tracks")
      .then(setTracks)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "load failed"));
  }, []);

  async function requestPermission(t: Track) {
    setBusyId(t.id);
    try {
      await api.post(`/tracks/${t.id}/permission`, {
        artist: t.artist_name,
        email: `${t.artist_name.toLowerCase().replace(/[^a-z]/g, "")}@example.com`,
        message: "May we produce a visualizer video for your track?",
      });
      setNotice(`Permission requested for "${t.track_name}"`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "request failed");
    } finally {
      setBusyId(null);
    }
  }

  async function uploadAudio(t: Track, file: File) {
    setBusyId(t.id);
    try {
      await api.upload(`/tracks/${t.id}/audio`, file);
      setNotice(`Audio uploaded for "${t.track_name}"`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "upload failed");
    } finally {
      setBusyId(null);
    }
  }

  async function reject(t: Track) {
    setBusyId(t.id);
    try {
      await api.post(`/tracks/${t.id}/reject`);
      refresh();
    } finally {
      setBusyId(null);
    }
  }

  function refresh() {
    api.get<Track[]>("/tracks").then(setTracks).catch(() => undefined);
  }

  if (error) return <div className="rounded-xl bg-danger/10 p-4 text-sm text-danger">{error}</div>;
  if (!tracks) return <Spinner />;

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-white">Music library</h1>
        <p className="text-sm text-slate-400">
          Every discovered track, its rights status, and where it lives in the funnel.
        </p>
      </header>

      {notice && (
        <p className="rounded-lg bg-mint/10 px-3 py-2 text-xs text-mint">{notice}</p>
      )}

      {tracks.length === 0 ? (
        <EmptyState title="No tracks yet" hint="Run a discovery pass first." />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {tracks.map((t) => (
            <Card key={t.id} className="flex gap-4">
              <img
                src={assetUrl(t.artwork_path ?? t.album_art_url)}
                alt=""
                className="h-20 w-20 shrink-0 rounded-lg object-cover"
                onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-100">
                      {t.track_name}
                    </p>
                    <p className="truncate text-xs text-slate-400">{t.artist_name}</p>
                  </div>
                  <RightsBadge status={t.rights_status} />
                </div>

                <div className="mt-2 flex flex-wrap gap-1.5">
                  <Badge tone="neutral">{t.genre ?? "unknown"}</Badge>
                  <Badge tone="neutral">{t.exposure_label ?? "—"}</Badge>
                  {t.duration_ms != null && (
                    <Badge tone="neutral">{Math.round(t.duration_ms / 1000)}s</Badge>
                  )}
                </div>

                <div className="mt-3 flex flex-wrap items-center gap-2">
                  {t.rights_status !== "APPROVED" && (
                    <Button
                      size="sm"
                      variant="outline"
                      loading={busyId === t.id}
                      onClick={() => requestPermission(t)}
                    >
                      Request permission
                    </Button>
                  )}
                  {t.rights_status === "APPROVED" && (
                    <>
                      <Input
                        ref={(el) => (fileRefs.current[t.id] = el)}
                        type="file"
                        accept=".mp3,.wav,.flac,.m4a"
                        className="hidden"
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) uploadAudio(t, f);
                        }}
                      />
                      <Button
                        size="sm"
                        variant="success"
                        loading={busyId === t.id}
                        onClick={() => fileRefs.current[t.id]?.click()}
                      >
                        Upload audio
                      </Button>
                    </>
                  )}
                  <Button size="sm" variant="ghost" disabled={busyId === t.id} onClick={() => reject(t)}>
                    Reject
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}