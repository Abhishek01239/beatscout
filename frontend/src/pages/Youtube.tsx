import { useEffect, useState } from "react";
import { api } from "../api";
import type { Video } from "../types";
import { Badge, Button, Card, EmptyState, Input, Label, Spinner } from "../components/ui";

interface YtStatus {
  provider?: string;
  connected: boolean;
  channel?: { channel_id?: string; channel_name?: string } | null;
  auth_url?: string | null;
}

interface YtUpload {
  id: number;
  track_id?: number;
  video_id?: number;
  title?: string;
  status: string;
  youtube_video_id?: string | null;
  youtube_url?: string | null;
  error?: string | null;
  created_at?: string | null;
}

export default function Youtube() {
  const [status, setStatus] = useState<YtStatus | null>(null);
  const [videos, setVideos] = useState<Video[]>([]);
  const [uploads, setUploads] = useState<YtUpload[]>([]);
  const [videoId, setVideoId] = useState<number | "">("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function refresh() {
    api.get<YtStatus>("/youtube/status").then(setStatus).catch(() => undefined);
    try {
      const u = await api.get<YtUpload[]>("/youtube/uploads");
      setUploads(u);
    } catch {
      setUploads([]);
    }
  }

  useEffect(() => {
    void refresh();
    api
      .get<Video[]>("/videos")
      .then((vs) => {
        const done = vs.filter((v) => v.status === "completed");
        setVideos(done);
        if (done.length) setVideoId(done[0].id);
      })
      .catch(() => undefined);
  }, []);

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const res = await api.post<{ connected: boolean; url?: string | null }>("/youtube/connect");
      if (res.connected) {
        setNotice("Mock YouTube connected — ready to publish.");
        void refresh();
      } else if (res.url) {
        setNotice("Open the OAuth URL to authorize this channel:");
        window.open(res.url, "_blank");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "connect failed");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!videoId) return;
    setBusy(true);
    setError("");
    try {
      const body: Record<string, unknown> = {
        video_id: videoId,
        title: title || undefined,
        description: description || undefined,
        category: "10",
        privacy: "private",
      };
      await api.post("/youtube/upload", body);
      setNotice("Upload queued — check the Jobs page for progress.");
      await refresh();
      const u = await api.get<YtUpload[]>("/youtube/uploads");
      setUploads(u);
    } catch (e) {
      setError(e instanceof Error ? e.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-white">YouTube publishing</h1>
        <p className="text-sm text-slate-400">Reach the world — with clean rights first.</p>
      </header>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm text-slate-300">
              Status:{" "}
              {status === null ? (
                <Spinner className="inline h-3.5 w-3.5" />
              ) : status.connected ? (
                <Badge tone="green">connected</Badge>
              ) : (
                <Badge tone="amber">not connected</Badge>
              )}
            </p>
            {status?.connected && status.channel && (
              <p className="mt-1 text-xs text-slate-500">
                Channel: {status.channel.channel_name ?? "—"} ·{" "}
                {status.provider === "REAL" ? "real API" : "mock provider"}
              </p>
            )}
          </div>
          {!status?.connected && (
            <Button onClick={connect} loading={busy}>
              Connect YouTube
            </Button>
          )}
        </div>
        {notice && (
          <p className="mt-3 rounded-lg bg-mint/10 px-3 py-2 text-xs text-mint">{notice}</p>
        )}
        {error && (
          <p className="mt-3 rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
        )}
      </Card>

      {status?.connected && (
        <Card>
          <h2 className="mb-3 text-sm font-bold text-slate-200">Publish a rendered video</h2>
          {videos.length === 0 ? (
            <EmptyState title="No completed videos" hint="Render one in the Studio first." />
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-3">
                <div>
                  <Label>Rendered video</Label>
                  <select
                    value={videoId}
                    onChange={(e) => setVideoId(Number(e.target.value) || "")}
                    className="w-full rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-accent"
                  >
                    {videos.map((v) => (
                      <option key={v.id} value={v.id}>
                        #{v.id} · {v.template} ({v.preview ? "preview" : "full"})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="yt-title">Title (blank = auto from metadata)</Label>
                  <Input
                    id="yt-title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Artist — Track | Visualizer"
                  />
                </div>
                <div>
                  <Label htmlFor="yt-desc">Description (blank = auto with license notes)</Label>
                  <textarea
                    id="yt-desc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    rows={3}
                    placeholder="Legal notes and credits are auto-appended."
                    className="w-full rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-accent"
                  />
                </div>
                <Button onClick={publish} loading={busy}>
                  Publish to YouTube (private)
                </Button>
              </div>
              <div className="rounded-lg border border-surface-800 bg-surface-950/60 p-4">
                <p className="text-xs font-semibold text-slate-400">Upload history</p>
                {uploads.length === 0 ? (
                  <p className="mt-2 text-xs text-slate-600">Nothing uploaded yet.</p>
                ) : (
                  <ul className="mt-2 space-y-2">
                    {uploads.map((u) => (
                      <li key={u.id} className="flex items-center justify-between gap-2">
                        <span className="truncate text-xs text-slate-300">
                          {u.title ?? `#${u.id}`}
                        </span>
                        <Badge
                          tone={
                            u.status === "uploaded" || u.status === "published"
                              ? "green"
                              : u.status === "failed"
                                ? "red"
                                : "amber"
                          }
                        >
                          {u.status}
                        </Badge>
                      </li>
                    ))}
                  </ul>
                )}
                {uploads.some((u) => u.youtube_url) && (
                  <a
                    className="mt-3 inline-block text-xs text-accent-soft hover:underline"
                    href={uploads.find((u) => u.youtube_url)?.youtube_url ?? undefined}
                    target="_blank"
                    rel="noreferrer"
                  >
                    View on YouTube →
                  </a>
                )}
              </div>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}