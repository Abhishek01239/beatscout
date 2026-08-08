import { useEffect, useState } from "react";
import { api } from "../api";
import type { Automation } from "../types";
import { Badge, Button, Card, EmptyState, Input, Label, Spinner } from "../components/ui";

const JOB_TYPES = [
  { value: "discover", label: "Discovery sweep" },
  { value: "analyze", label: "Audio analysis" },
  { value: "render", label: "Render visualizer" },
  { value: "publish", label: "Publish to YouTube" },
  { value: "collect", label: "Collect metrics" },
];

const EMPTY: Automation = {
  id: 0,
  name: "Nightly indie sweep",
  enabled: true,
  discovery_frequency_hours: 24,
  max_tracks: 12,
  target_platforms: ["spotify"],
};

export default function Automations() {
  const [items, setItems] = useState<Automation[] | null>(null);
  const [draft, setDraft] = useState<Automation>(EMPTY);
  const [jobType, setJobType] = useState("discover");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  function load() {
    api
      .get<Automation[]>("/automation")
      .then(setItems)
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "load failed"));
  }

  useEffect(load, []);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setNotice("");
    setError("");
    try {
      await api.post("/automation/create", {
        name: draft.name,
        enabled: draft.enabled,
        discovery_frequency_hours: draft.discovery_frequency_hours,
        max_tracks: draft.max_tracks,
      });
      setNotice("Automation created — it runs on the worker schedule.");
      setDraft(EMPTY);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "create failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggle(a: Automation) {
    await api.patch(`/automation/${a.id}`, { enabled: !a.enabled });
    load();
  }

  async function runNow(a: Automation) {
    setBusy(true);
    try {
      await api.post(`/automation/${a.id}/run`);
      setNotice(`"${a.name}" queued — check Jobs.`);
    } finally {
      setBusy(false);
    }
  }

  async function enqueueRaw() {
    setBusy(true);
    try {
      await api.post("/jobs", { job_type: jobType, payload: {} });
      setNotice(`Manual ${jobType} job queued.`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-white">Automations</h1>
        <p className="text-sm text-slate-400">
          Scheduled, permission-aware publishing loops. Every run respects the rights funnel.
        </p>
      </header>

      {notice && (
        <p className="rounded-lg bg-mint/10 px-3 py-2 text-xs text-mint">{notice}</p>
      )}
      {error && (
        <p className="rounded-lg bg-danger/10 px-3 py-2 text-xs text-danger">{error}</p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <h2 className="mb-4 text-sm font-bold text-slate-200">New automation</h2>
          <form onSubmit={create} className="space-y-4">
            <div>
              <Label htmlFor="a-name">Name</Label>
              <Input
                id="a-name"
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                required
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="a-freq">Every (hours)</Label>
                <Input
                  id="a-freq"
                  type="number"
                  min={1}
                  max={168}
                  value={draft.discovery_frequency_hours ?? 24}
                  onChange={(e) =>
                    setDraft({ ...draft, discovery_frequency_hours: Number(e.target.value) })
                  }
                />
              </div>
              <div>
                <Label htmlFor="a-max">Max tracks</Label>
                <Input
                  id="a-max"
                  type="number"
                  min={1}
                  max={50}
                  value={draft.max_tracks ?? 12}
                  onChange={(e) => setDraft({ ...draft, max_tracks: Number(e.target.value) })}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300">
              <input
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })}
                className="h-4 w-4 accent-[#6d5ef2]"
              />
              Enabled (runs on schedule)
            </label>
            <Button type="submit" loading={busy}>
              Create automation
            </Button>
          </form>
        </Card>

        <div className="space-y-4">
          <Card>
            <h2 className="mb-3 text-sm font-bold text-slate-200">Existing</h2>
            {items === null ? (
              <Spinner />
            ) : items.length === 0 ? (
              <EmptyState title="No automations yet" hint="Create one on the left." />
            ) : (
              <ul className="divide-y divide-surface-800">
                {items.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-slate-200">{a.name}</p>
                      <p className="text-xs text-slate-500">
                        every {a.discovery_frequency_hours ?? "—"}h · {a.max_tracks ?? "—"} tracks
                        {a.next_run_at && ` · next ${new Date(a.next_run_at).toLocaleString()}`}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Badge tone={a.enabled ? "green" : "neutral"}>
                        {a.enabled ? "enabled" : "paused"}
                      </Badge>
                      <Button size="sm" variant="outline" onClick={() => toggle(a)}>
                        {a.enabled ? "Pause" : "Enable"}
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => runNow(a)}>
                        Run now
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card>
            <h2 className="mb-3 text-sm font-bold text-slate-200">Manual job queue</h2>
            <div className="flex gap-2">
              <select
                value={jobType}
                onChange={(e) => setJobType(e.target.value)}
                className="flex-1 rounded-lg border border-surface-600 bg-surface-800 px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-accent"
              >
                {JOB_TYPES.map((j) => (
                  <option key={j.value} value={j.value}>
                    {j.label}
                  </option>
                ))}
              </select>
              <Button onClick={enqueueRaw} loading={busy} variant="outline">
                Enqueue
              </Button>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}