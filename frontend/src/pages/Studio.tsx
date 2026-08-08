import { useEffect, useState } from "react";
import { api, assetUrl } from "../api";
import type { Video, VideoTemplate } from "../types";
import { Badge, Button, Card, EmptyState } from "../components/ui";

interface StudioTrack {
  id: number;
  track_name: string;
  artist_name: string;
  rights_status: string;
}

export default function Studio() {
  const [tracks, setTracks] = useState<StudioTrack[]>([]);
  const [templates, setTemplates] = useState<VideoTemplate[]>([]);
  const [videos, setVideos] = useState<Video[]>([]);
  const [trackId, setTrackId] = useState<number | "">("");
  const [template, setTemplate] = useState("minimal");
  const [asPreview, setAsPreview] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [lastVideo, setLastVideo] = useState<Video | null>(null);

  function load() {
    api
      .get<StudioTrack[]>("/tracks")
      .then((ts) => {
        setTracks(ts);
        if (trackId === "" && ts.length) setTrackId(ts[0].id);
        return api.get<VideoTemplate[]>("/videos/templates");
      })
      .then(setTemplates)
      .catch(() => undefined);
    api
      .get<Video[]>("/videos")
      .then(setVideos)
      .catch(() => undefined);
  }

  useEffect(load, []);

  async function render() {
    if (!trackId) return;
    setBusy(true);
    setError("");
    try {
      const v = await api.post<Video>("/videos/generate", {
        track_id: trackId,
        template,
        preview: asPreview,
      });
      setLastVideo(v);
      const vs = await api.get<Video[]>("/videos");
      setVideos(vs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "render failed");
    } finally {
      setBusy(false);
    }
  }

  const licensed = tracks.filter((t) => t.rights_status === "APPROVED");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-white">Studio</h1>
        <p className="text-sm text-slate-400">
          Render audio-reactive visualizers. Only APPROVED tracks can render — that is the
          legal gate.
        </p>
      </header>

      <Card>
        <div className="grid gap-4 md:grid-cols-3">
          <div>
            <p className="mb-1 block text-xs font-medium text-slate-400">Track</p>
            <select
              value={trackId}
              onChange={(e) => setTrackId(Number(e.target.value) || "")}
              className="w-full rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-accent"
            >
              {licensed.length === 0 && (
                <option value="">No licensed tracks yet</option>
              )}
              {licensed.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.track_name} — {t.artist_name}
                </option>
              ))}
            </select>
            {licensed.length === 0 && (
              <p className="mt-1 text-[11px] text-warn">
                Approve rights on a track in Library to unlock rendering.
              </p>
            )}
          </div>
          <div>
            <p className="mb-1 block text-xs font-medium text-slate-400">Visual style</p>
            <div className="flex flex-wrap gap-2">
              {templates.map((tpl) => (
                <button
                  key={tpl.name}
                  type="button"
                  onClick={() => setTemplate(tpl.name)}
                  className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
                    template === tpl.name
                      ? "bg-accent text-white"
                      : "bg-surface-800 text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {tpl.label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-end justify-between gap-3">
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={asPreview}
                onChange={(e) => setAsPreview(e.target.checked)}
                className="h-4 w-4 accent-[#6d5ef2]"
              />
              Quick preview
            </label>
            <Button onClick={render} loading={busy} disabled={licensed.length === 0}>
              Render
            </Button>
          </div>
        </div>
        {error && (
          <p className="mt-4 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
        )}
      </Card>

      {lastVideo && lastVideo.status === "completed" && (
        <Card>
          <h2 className="mb-3 text-sm font-bold text-slate-200">Latest render</h2>
          <video
            src={assetUrl(lastVideo.file_path)}
            controls
            className="max-h-[420px] w-full rounded-lg border border-surface-700 bg-black"
          />
        </Card>
      )}

      <div>
        <h2 className="mb-3 text-sm font-bold text-slate-200">Render history</h2>
        {videos.length === 0 ? (
          <EmptyState title="Nothing rendered yet" />
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {videos.map((v) => (
              <Card key={v.id} className="p-4">
                <img
                  src={assetUrl(v.thumbnail_path)}
                  alt=""
                  className="mb-3 h-28 w-full rounded-lg object-cover"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                />
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-slate-200">{v.template}</p>
                  <Badge tone={v.status === "completed" ? "green" : v.status === "failed" ? "red" : "amber"}>
                    {v.status}
                  </Badge>
                </div>
                <p className="mt-1 text-xs text-slate-500">
                  {v.preview ? "preview" : "full"} · {v.duration_ms ? `${Math.round(v.duration_ms / 1000)}s` : "—"}
                </p>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}