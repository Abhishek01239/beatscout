import { useEffect, useState } from "react";
import { api } from "../api";
import type { Job } from "../types";
import { Badge, Button, Card, EmptyState, Spinner } from "../components/ui";

function tone(status: string): "green" | "red" | "amber" | "neutral" | "violet" {
  if (status === "COMPLETED") return "green";
  if (status === "FAILED") return "red";
  if (status === "PROCESSING") return "amber";
  if (status === "QUEUED") return "violet";
  return "neutral";
}

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const list = await api.get<Job[]>("/jobs");
      setJobs(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : "load failed");
    }
  }

  useEffect(() => {
    load();
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, []);

  async function retry(j: Job) {
    await api.post(`/jobs/${j.id}/retry`).catch(() => undefined);
    load();
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-xl font-extrabold text-white">Jobs</h1>
        <p className="text-sm text-slate-400">
          The run-to-completion worker queue — discover → analyze → render → publish.
        </p>
      </header>

      {error && (
        <div className="rounded-xl bg-danger/10 p-4 text-sm text-danger">{error}</div>
      )}

      {jobs === null ? (
        <Spinner />
      ) : jobs.length === 0 ? (
        <EmptyState title="No jobs yet" hint="Run a discovery or render to see them here." />
      ) : (
        <Card className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-surface-800 text-left text-xs text-slate-500">
                  <th className="px-5 py-3 font-semibold">#</th>
                  <th className="px-5 py-3 font-semibold">Type</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Progress</th>
                  <th className="px-5 py-3 font-semibold">Result / error</th>
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3 font-semibold"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-800">
                {jobs.map((j) => (
                  <tr key={j.id} className="hover:bg-surface-900/60">
                    <td className="px-5 py-3 text-slate-400">{j.id}</td>
                    <td className="px-5 py-3 font-medium text-slate-200">{j.job_type}</td>
                    <td className="px-5 py-3">
                      <Badge tone={tone(j.status)}>{j.status}</Badge>
                    </td>
                    <td className="px-5 py-3">
                      <div className="flex items-center gap-2">
                        <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-700">
                          <div
                            className="h-full rounded-full bg-accent"
                            style={{ width: `${Math.max(2, Math.min(100, j.progress))}%` }}
                          />
                        </div>
                        <span className="text-xs text-slate-500">{Math.round(j.progress)}%</span>
                      </div>
                    </td>
                    <td className="max-w-[220px] truncate px-5 py-3 text-xs text-slate-500">
                      {j.status === "FAILED"
                        ? j.error
                        : j.result
                          ? JSON.stringify(j.result).slice(0, 60)
                          : "—"}
                    </td>
                    <td className="px-5 py-3 text-xs text-slate-500">
                      {j.created_at ? new Date(j.created_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-5 py-3">
                      {j.status === "FAILED" && (
                        <Button size="sm" variant="outline" onClick={() => retry(j)}>
                          Retry
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}