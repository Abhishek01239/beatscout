import { useEffect, useState } from "react";
import { api, assetUrl } from "../api";
import type { Dashboard as DashboardData } from "../types";
import type { Track, Video } from "../types";
import { Badge, Card, EmptyState, Spinner } from "../components/ui";

function fmt(n: number | undefined | null): string {
  return (n ?? 0).toLocaleString();
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<DashboardData>("/dashboard")
      .then(setData)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "load failed"));
  }, []);

  if (error)
    return (
      <div className="rounded-xl bg-danger/10 p-4 text-sm text-danger">{error}</div>
    );
  if (!data) return <Spinner />;

  const s = data.stats;
  const cards = [
    { label: "Tracks discovered", value: fmt(s.tracks_discovered), tone: "text-accent-soft" },
    { label: "Awaiting permission", value: fmt(s.awaiting_permission), tone: "text-warn" },
    { label: "Licensed tracks", value: fmt(s.licensed_tracks), tone: "text-mint" },
    { label: "Videos generated", value: fmt(s.videos_generated), tone: "text-sky-400" },
    { label: "Uploaded to YouTube", value: fmt(s.uploaded_to_youtube), tone: "text-danger" },
    { label: "Failed jobs", value: fmt(s.failed_jobs), tone: "text-slate-400" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-extrabold text-white">Dashboard</h1>
          <p className="text-sm text-slate-400">Your funnel at a glance</p>
        </div>
        <Badge tone="violet">provider: {data.provider_mode}</Badge>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        {cards.map((c) => (
          <Card key={c.label} className="p-4">
            <p className={`text-2xl font-extrabold ${c.tone}`}>{c.value}</p>
            <p className="mt-1 text-xs text-slate-400">{c.label}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-3 text-sm font-bold text-slate-200">Recent tracks</h2>
          {data.recent_tracks.length === 0 ? (
            <EmptyState title="No tracks yet" hint="Run Discovery to find music" />
          ) : (
            <ul className="divide-y divide-surface-800">
              {data.recent_tracks.map((t: Track) => (
                <li key={t.id} className="flex items-center gap-3 py-2.5">
                  <img
                    src={assetUrl(t.artwork_path ?? t.album_art_url)}
                    alt=""
                    className="h-10 w-10 rounded-lg object-cover"
                    onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-200">
                      {t.track_name}{" "}
                      <span className="text-slate-500">— {t.artist_name}</span>
                    </p>
                  </div>
                  <RightsBadge status={t.rights_status} />
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card>
          <h2 className="mb-3 text-sm font-bold text-slate-200">Recent videos</h2>
          {data.recent_videos.length === 0 ? (
            <EmptyState title="No videos yet" hint="Render one in the Studio" />
          ) : (
            <ul className="divide-y divide-surface-800">
              {data.recent_videos.map((v: Video) => (
                <li key={v.id} className="flex items-center gap-3 py-2.5">
                  <img
                    src={assetUrl(v.thumbnail_path)}
                    alt=""
                    className="h-10 w-16 rounded-lg object-cover"
                    onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-slate-200">{v.template}</p>
                    <p className="text-xs text-slate-500">
                      {v.preview ? "preview" : "full"} · {v.status}
                    </p>
                  </div>
                  {v.status === "completed" && <Badge tone="green">done</Badge>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card>
        <h2 className="mb-3 text-sm font-bold text-slate-200">Automation</h2>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <p className="text-lg font-bold text-white">{data.automation.automation_count}</p>
            <p className="text-xs text-slate-500">automations</p>
          </div>
          <div>
            <p className="text-lg font-bold text-mint">{data.automation.enabled}</p>
            <p className="text-xs text-slate-500">enabled</p>
          </div>
          <div>
            <p className="text-lg font-bold text-warn">
              {data.automation.next_run_at
                ? new Date(data.automation.next_run_at).toLocaleString()
                : "—"}
            </p>
            <p className="text-xs text-slate-500">next run</p>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function RightsBadge({ status }: { status: string }) {
  const tone =
    status === "APPROVED"
      ? "green"
      : status === "REJECTED"
        ? "red"
        : status === "REQUESTED"
          ? "amber"
          : status === "PENDING"
            ? "violet"
            : "neutral";
  return <Badge tone={tone as "green"}>{status}</Badge>;
}