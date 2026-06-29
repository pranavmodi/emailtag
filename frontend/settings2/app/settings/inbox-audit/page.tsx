"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ExternalLink,
  Loader2,
  Play,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
} from "lucide-react";

import {
  ApiError,
  InboxAuditApi,
  type InboxAuditMissResponse,
  type InboxAuditQueueStatusResponse,
  type InboxAuditQueueStatusTask,
  type InboxAuditRunResponse,
  type InboxAuditSummary,
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Header, getCurrentPageInfo } from "@/components/layout/Header";

const STATE_LABELS: Record<string, { label: string; className: string }> = {
  never_received: {
    label: "Never received",
    className: "bg-rose-100 text-rose-700",
  },
  received_but_failed: {
    label: "Received but failed",
    className: "bg-amber-100 text-amber-700",
  },
};

const RUN_STATUS_STYLE: Record<string, string> = {
  success: "bg-emerald-100 text-emerald-700",
  partial: "bg-amber-100 text-amber-700",
  failed: "bg-rose-100 text-rose-700",
};

type QueueBatch = {
  startedAt: string;
  tasks: InboxAuditQueueStatusTask[];
};

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleDateString();
  } catch {
    return value;
  }
}

export default function InboxAuditPage() {
  const [summary, setSummary] = useState<InboxAuditSummary | null>(null);
  const [openMisses, setOpenMisses] = useState<InboxAuditMissResponse[]>([]);
  const [runs, setRuns] = useState<InboxAuditRunResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [queueingId, setQueueingId] = useState<string | null>(null);
  const [queueingAll, setQueueingAll] = useState(false);
  const [queueBatch, setQueueBatch] = useState<QueueBatch | null>(null);
  const [queueDashboard, setQueueDashboard] =
    useState<InboxAuditQueueStatusResponse | null>(null);
  const [queueDashboardCollapsed, setQueueDashboardCollapsed] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const currentPage = useMemo(() => getCurrentPageInfo("/inbox-audit"), []);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [summaryRes, missesRes, runsRes] = await Promise.all([
        InboxAuditApi.getSummary(7),
        InboxAuditApi.listMisses({ reviewed: false, days: 30 }),
        InboxAuditApi.listRuns({ days: 30 }),
      ]);
      setSummary(summaryRes);
      setOpenMisses(missesRes.items);
      setRuns(runsRes.items);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Failed to load audit data";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!queueBatch || queueBatch.tasks.length === 0) return;

    let cancelled = false;
    let timeoutId: number | null = null;

    const poll = async () => {
      try {
        const result = await InboxAuditApi.getQueueProcessingStatus(queueBatch.tasks);
        if (cancelled) return;
        setQueueDashboard(result);

        if (result.pending > 0) {
          timeoutId = window.setTimeout(poll, 2500);
        }
      } catch (err) {
        if (!cancelled) {
          setStatusMessage(
            err instanceof ApiError ? err.message : "Failed to load queue status"
          );
          timeoutId = window.setTimeout(poll, 5000);
        }
      }
    };

    timeoutId = window.setTimeout(poll, 800);

    return () => {
      cancelled = true;
      if (timeoutId !== null) window.clearTimeout(timeoutId);
    };
  }, [queueBatch]);

  const handleTrigger = async () => {
    setTriggering(true);
    setStatusMessage(null);
    try {
      const result = await InboxAuditApi.triggerRun();
      setStatusMessage(result.message);
    } catch (err) {
      setStatusMessage(
        err instanceof ApiError ? err.message : "Failed to trigger audit"
      );
    } finally {
      setTriggering(false);
    }
  };

  const handleQueueMiss = async (missId: string) => {
    setQueueingId(missId);
    setStatusMessage(null);
    try {
      const result = await InboxAuditApi.queueMissProcessing(missId);
      setStatusMessage(result.message);
    } catch (err) {
      setStatusMessage(
        err instanceof ApiError ? err.message : "Failed to queue processing"
      );
    } finally {
      setQueueingId(null);
    }
  };

  const handleQueueAll = async () => {
    setQueueingAll(true);
    setStatusMessage(null);
    try {
      const result = await InboxAuditApi.queueOpenMissesProcessing(5000, 5);
      const tasks = result.task_ids
        .map((taskId, index) => ({
          task_id: taskId,
          conversation_id: result.conversation_ids[index] ?? "",
        }))
        .filter((task) => task.task_id && task.conversation_id);

      setQueueBatch(
        tasks.length > 0 ? { startedAt: new Date().toISOString(), tasks } : null
      );
      setQueueDashboardCollapsed(false);
      setQueueDashboard(
        tasks.length > 0
          ? {
              total_queued: tasks.length,
              processed: 0,
              failed: 0,
              pending: tasks.length,
              failed_conversation_ids: [],
              items: tasks.map((task) => ({
                ...task,
                state: "PENDING",
                status: "pending",
              })),
            }
          : null
      );
      setStatusMessage(result.message);
    } catch (err) {
      setStatusMessage(
        err instanceof ApiError ? err.message : "Failed to queue open misses"
      );
    } finally {
      setQueueingAll(false);
    }
  };

  const handleReview = async (missId: string) => {
    setReviewingId(missId);
    try {
      await InboxAuditApi.reviewMiss(missId, { reviewed_by: "Settings UI" });
      setOpenMisses((prev) => prev.filter((m) => m.id !== missId));
      setSummary((prev) =>
        prev ? { ...prev, open_misses: Math.max(0, prev.open_misses - 1) } : prev
      );
    } catch (err) {
      setStatusMessage(
        err instanceof ApiError ? err.message : "Failed to mark reviewed"
      );
    } finally {
      setReviewingId(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Header user="Admin" currentPage={currentPage} />

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Inbox Audit</h1>
            <p className="text-sm text-slate-500">
              Daily reconciliation of Front inboxes against our processed emails. Runs
              every morning at 6:00 AM PT.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              onClick={loadAll}
              disabled={loading}
            >
              {loading ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <RefreshCw className="mr-2 h-4 w-4" />
              )}
              Refresh
            </Button>
            <Button
              variant="ghost"
              className="border border-slate-200 bg-white"
              onClick={handleQueueAll}
              disabled={queueingAll || loading || openMisses.length === 0}
            >
              {queueingAll ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Play className="mr-2 h-4 w-4" />
              )}
              Add all to queue
            </Button>
            <Button onClick={handleTrigger} disabled={triggering}>
              {triggering ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ShieldCheck className="mr-2 h-4 w-4" />
              )}
              Run audit now
            </Button>
          </div>
        </div>

        {statusMessage && (
          <div className="mb-4 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700">
            {statusMessage}
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        {queueDashboard && queueBatch && (
          <Card className="mb-8">
            <CardHeader>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <CardTitle>Queue dashboard</CardTitle>
                  <CardDescription>
                    Last batch started {formatDateTime(queueBatch.startedAt)}
                  </CardDescription>
                </div>
                <div className="flex items-center gap-3">
                  <div className="hidden items-center gap-3 text-xs text-slate-500 md:flex">
                    <span>Queued {queueDashboard.total_queued}</span>
                    <span>Processed {queueDashboard.processed}</span>
                    <span>Pending {queueDashboard.pending}</span>
                    <span>Failed {queueDashboard.failed}</span>
                  </div>
                  <Badge
                    className={
                      queueDashboard.pending > 0
                        ? "bg-blue-100 text-blue-700"
                        : queueDashboard.failed > 0
                          ? "bg-rose-100 text-rose-700"
                          : "bg-emerald-100 text-emerald-700"
                    }
                  >
                    {queueDashboard.pending > 0 ? "running" : "complete"}
                  </Badge>
                  <Button
                    variant="ghost"
                    className="px-2"
                    onClick={() => setQueueDashboardCollapsed((value) => !value)}
                    aria-expanded={!queueDashboardCollapsed}
                    aria-label={
                      queueDashboardCollapsed
                        ? "Expand queue dashboard"
                        : "Collapse queue dashboard"
                    }
                  >
                    <ChevronDown
                      className={`h-4 w-4 transition ${
                        queueDashboardCollapsed ? "-rotate-90" : ""
                      }`}
                    />
                  </Button>
                </div>
              </div>
            </CardHeader>
            {!queueDashboardCollapsed && (
              <CardContent>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="text-xs font-medium uppercase text-slate-500">Queued</div>
                    <div className="mt-1 text-2xl font-semibold text-slate-900">
                      {queueDashboard.total_queued}
                    </div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="text-xs font-medium uppercase text-slate-500">Processed</div>
                    <div className="mt-1 text-2xl font-semibold text-emerald-700">
                      {queueDashboard.processed}
                    </div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="text-xs font-medium uppercase text-slate-500">Pending</div>
                    <div className="mt-1 text-2xl font-semibold text-blue-700">
                      {queueDashboard.pending}
                    </div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                    <div className="text-xs font-medium uppercase text-slate-500">Failed</div>
                    <div className="mt-1 text-2xl font-semibold text-rose-700">
                      {queueDashboard.failed}
                    </div>
                  </div>
                </div>

                {queueDashboard.failed_conversation_ids.length > 0 && (
                  <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-4 py-3">
                    <div className="mb-2 text-xs font-medium uppercase text-rose-700">
                      Failed conversation IDs
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {queueDashboard.failed_conversation_ids.map((conversationId) => (
                        <span
                          key={conversationId}
                          className="rounded bg-white px-2 py-1 font-mono text-xs text-rose-700"
                        >
                          {conversationId}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            )}
          </Card>
        )}

        <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-slate-500">
                Last audit
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-lg font-semibold text-slate-900">
                {formatDateTime(summary?.last_run_at)}
              </div>
              {summary?.last_run_status && (
                <Badge
                  className={`mt-2 ${
                    RUN_STATUS_STYLE[summary.last_run_status] ||
                    "bg-slate-100 text-slate-600"
                  }`}
                >
                  {summary.last_run_status}
                </Badge>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-slate-500">
                Open misses
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-slate-900">
                {summary?.open_misses ?? 0}
              </div>
              <CardDescription className="mt-1">
                Unreviewed misses across all inboxes
              </CardDescription>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium text-slate-500">
                7-day misses
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-3xl font-bold text-slate-900">
                {(summary?.misses_by_day ?? []).reduce((s, d) => s + d.count, 0)}
              </div>
              <CardDescription className="mt-1">
                Total misses detected in the last 7 days
              </CardDescription>
            </CardContent>
          </Card>
        </div>

        <Card className="mb-8">
          <CardHeader>
            <CardTitle>Open misses by state</CardTitle>
            <CardDescription>
              Distinct open miss conversations grouped by pipeline failure state.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {(summary?.misses_by_state ?? []).length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                No open miss state data available.
              </div>
            ) : (
              <div className="space-y-3">
                {(summary?.misses_by_state ?? []).map((item) => {
                  const maxCount = Math.max(
                    1,
                    ...(summary?.misses_by_state ?? []).map(
                      (stateItem) => stateItem.count
                    )
                  );
                  const width = `${Math.max(8, (item.count / maxCount) * 100)}%`;
                  const stateMeta = STATE_LABELS[item.state] ?? {
                    label: item.state,
                    className: "bg-slate-100 text-slate-600",
                  };
                  return (
                    <div key={item.state}>
                      <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                        <Badge className={stateMeta.className}>{stateMeta.label}</Badge>
                        <span className="shrink-0 tabular-nums text-slate-500">
                          {item.count}
                        </span>
                      </div>
                      <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-slate-700"
                          style={{ width }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldAlert className="h-5 w-5 text-rose-600" />
              Open misses
            </CardTitle>
            <CardDescription>
              Conversations Front received but our pipeline did not fully process.
              Mark as reviewed once investigated.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {openMisses.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                No open misses. All clear.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="py-2 pr-4">Conversation</th>
                      <th className="py-2 pr-4">Inbox</th>
                      <th className="py-2 pr-4">State</th>
                      <th className="py-2 pr-4">Reason</th>
                      <th className="py-2 pr-4">Detected</th>
                      <th className="py-2 pr-4 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {openMisses.map((m) => {
                      const stateMeta = STATE_LABELS[m.state] ?? {
                        label: m.state,
                        className: "bg-slate-100 text-slate-600",
                      };
                      return (
                        <tr key={m.id} className="border-b border-slate-100 align-top">
                          <td className="py-3 pr-4">
                            {m.front_url ? (
                              <a
                                href={m.front_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 font-mono text-xs text-blue-600 hover:underline"
                              >
                                {m.conversation_id}
                                <ExternalLink className="h-3 w-3" />
                              </a>
                            ) : (
                              <span className="font-mono text-xs">{m.conversation_id}</span>
                            )}
                            {m.subject && (
                              <div className="mt-1 text-xs text-slate-500 line-clamp-1">
                                {m.subject}
                              </div>
                            )}
                          </td>
                          <td className="py-3 pr-4 text-slate-700">
                            {m.inbox_name || m.inbox_id}
                          </td>
                          <td className="py-3 pr-4">
                            <Badge className={stateMeta.className}>{stateMeta.label}</Badge>
                          </td>
                          <td className="py-3 pr-4 text-slate-600">{m.reason || "—"}</td>
                          <td className="py-3 pr-4 text-slate-500">
                            {formatDateTime(m.detected_at)}
                          </td>
                          <td className="py-3 pr-4 text-right">
                            <Button
                              variant="ghost"
                              className="mr-2 px-3 py-1 text-xs"
                              disabled={queueingId === m.id}
                              onClick={() => handleQueueMiss(m.id)}
                            >
                              {queueingId === m.id ? "…" : "Queue"}
                            </Button>
                            <Button
                              variant="ghost"
                              className="px-3 py-1 text-xs"
                              disabled={reviewingId === m.id}
                              onClick={() => handleReview(m.id)}
                            >
                              {reviewingId === m.id ? "…" : "Mark reviewed"}
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Run history (last 30 days)</CardTitle>
            <CardDescription>One row per inbox per daily audit run.</CardDescription>
          </CardHeader>
          <CardContent>
            {runs.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                No runs yet.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="py-2 pr-4">Date</th>
                      <th className="py-2 pr-4">Inbox</th>
                      <th className="py-2 pr-4 text-right">Received</th>
                      <th className="py-2 pr-4 text-right">Processed</th>
                      <th className="py-2 pr-4 text-right">Missed</th>
                      <th className="py-2 pr-4">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runs.map((r) => (
                      <tr key={r.id} className="border-b border-slate-100">
                        <td className="py-3 pr-4 text-slate-700">
                          {formatDate(r.run_at)}
                        </td>
                        <td className="py-3 pr-4 text-slate-700">
                          {r.inbox_name || r.inbox_id}
                        </td>
                        <td className="py-3 pr-4 text-right text-slate-700">
                          {r.total_received}
                        </td>
                        <td className="py-3 pr-4 text-right text-slate-700">
                          {r.total_processed}
                        </td>
                        <td
                          className={`py-3 pr-4 text-right font-medium ${
                            r.total_missed > 0 ? "text-rose-600" : "text-slate-500"
                          }`}
                        >
                          {r.total_missed}
                        </td>
                        <td className="py-3 pr-4">
                          <Badge
                            className={
                              RUN_STATUS_STYLE[r.status] || "bg-slate-100 text-slate-600"
                            }
                          >
                            {r.status}
                          </Badge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
}
