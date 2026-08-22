"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  CheckCircle2,
  ChevronRight,
  Eye,
  Loader2,
  Play,
  RefreshCw,
  Star,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ApiError, ModelEvaluationApi } from "@/lib/api";
import type {
  EvaluationModelOption,
  LegacyRxBulkJobStatusResponse,
  LegacyRxCasesResponse,
  VisionBulkJobStatusResponse,
  VisionEvaluationExample,
  VisionEvaluationResponse,
} from "@/lib/types";

const OBJECTIVE_LABELS = { rx: "RX documents", lien: "Lien processing" };
type VisionObjective = keyof typeof OBJECTIVE_LABELS;

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export function VisionEvaluationSection() {
  const router = useRouter();
  const [data, setData] = useState<VisionEvaluationResponse | null>(null);
  const [legacyRx, setLegacyRx] = useState<LegacyRxCasesResponse | null>(null);
  const [legacyJob, setLegacyJob] = useState<LegacyRxBulkJobStatusResponse | null>(null);
  const [models, setModels] = useState<EvaluationModelOption[]>([]);
  const [visionJobs, setVisionJobs] = useState<Partial<Record<VisionObjective, VisionBulkJobStatusResponse>>>({});
  const [objective, setObjective] = useState<VisionObjective>("rx");
  const [rankingSort, setRankingSort] = useState<"accuracy" | "cost_asc" | "cost_desc">("accuracy");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [response, legacy, catalog] = await Promise.all([
        ModelEvaluationApi.getVisionEvaluation(10),
        ModelEvaluationApi.getLegacyRxCases(),
        ModelEvaluationApi.getModels("vision"),
      ]);
      setData(response);
      setLegacyRx(legacy);
      setModels(catalog.models);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load vision examples");
    } finally {
      setLoading(false);
    }
  };

  const pollLegacyJob = async (jobId: string) => {
    while (true) {
      await wait(5000);
      const status = await ModelEvaluationApi.getLegacyRxBulkRerunJob(jobId);
      setLegacyJob(status);
      if (status.status === "error") {
        window.localStorage.removeItem("legacy-rx-evaluation-job");
        throw new Error(status.error || "RX bulk rerun failed");
      }
      if (status.status === "completed") {
        window.localStorage.removeItem("legacy-rx-evaluation-job");
        await load();
        return;
      }
    }
  };

  const rerunLegacyRx = async () => {
    setError(null);
    try {
      const started = await ModelEvaluationApi.startLegacyRxBulkRerun();
      setLegacyJob({
        ...started,
        completed_cases: 0,
        failed_cases: 0,
        current_case_id: null,
        errors: [],
        error: null,
      });
      window.localStorage.setItem("legacy-rx-evaluation-job", started.job_id);
      await pollLegacyJob(started.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rerun legacy RX cases");
    }
  };

  const pollVisionJob = async (jobObjective: VisionObjective, jobId: string) => {
    while (true) {
      await wait(5000);
      let status: VisionBulkJobStatusResponse;
      try {
        status = await ModelEvaluationApi.getVisionBulkJob(jobId);
      } catch (err) {
        if (err instanceof ApiError && err.status >= 500) continue;
        window.localStorage.removeItem(`vision-${jobObjective}-evaluation-job`);
        throw err;
      }
      setVisionJobs((current) => ({ ...current, [jobObjective]: status }));
      if (status.status === "error") {
        window.localStorage.removeItem(`vision-${jobObjective}-evaluation-job`);
        throw new Error(status.error || `${OBJECTIVE_LABELS[jobObjective]} bulk evaluation failed`);
      }
      if (status.status === "completed") {
        window.localStorage.removeItem(`vision-${jobObjective}-evaluation-job`);
        await load();
        return;
      }
    }
  };

  const startVisionBulkRun = async (jobObjective: VisionObjective) => {
    const cases = (data?.examples || []).filter((item) => item.objective === jobObjective);
    const activeModels = models.filter((model) => model.enabled && model.available);
    if (!cases.length || !activeModels.length) return;
    const evaluationCount = cases.length * activeModels.length;
    const confirmed = window.confirm(
      `Evaluate all ${cases.length} ${OBJECTIVE_LABELS[jobObjective].toLowerCase()} cases?\n\n`
      + `Each case will run against ${activeModels.length} enabled vision models `
      + `(${evaluationCount} total model evaluations). Existing latest results for these models will be replaced.`
    );
    if (!confirmed) return;

    setError(null);
    try {
      const started = await ModelEvaluationApi.startVisionBulkRun(
        jobObjective,
        cases.map((item) => ({
          email_id: item.email_id,
          result_index: Number(item.example_id.split(":").at(-1) || 0),
        }))
      );
      const initial: VisionBulkJobStatusResponse = {
        ...started,
        completed_cases: 0,
        failed_cases: 0,
        current_case_id: null,
        errors: [],
        error: null,
      };
      setVisionJobs((current) => ({ ...current, [jobObjective]: initial }));
      window.localStorage.setItem(`vision-${jobObjective}-evaluation-job`, started.job_id);
      await pollVisionJob(jobObjective, started.job_id);
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error
        ? err.message
        : `Could not evaluate ${OBJECTIVE_LABELS[jobObjective].toLowerCase()}`);
    }
  };

  useEffect(() => {
    load().then(() => {
      const existingJob = window.localStorage.getItem("legacy-rx-evaluation-job");
      if (existingJob) pollLegacyJob(existingJob).catch((err) => {
        setError(err instanceof Error ? err.message : "Could not resume RX bulk rerun");
      });
      (["rx", "lien"] as const).forEach((jobObjective) => {
        const visionJobId = window.localStorage.getItem(`vision-${jobObjective}-evaluation-job`);
        if (visionJobId) pollVisionJob(jobObjective, visionJobId).catch((err) => {
          setError(err instanceof Error ? err.message : `Could not resume ${OBJECTIVE_LABELS[jobObjective]} evaluation`);
        });
      });
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const examples = useMemo(
    () => data?.examples.filter((item) => item.objective === objective) || [],
    [data, objective]
  );
  const averagePages = useMemo(() => {
    const counts = examples.map((item) => item.page_count).filter((count) => count > 0);
    return counts.length ? counts.reduce((total, count) => total + count, 0) / counts.length : null;
  }, [examples]);
  const rankings = useMemo(() => {
    const rows = [...(data?.rankings?.[objective] || [])];
    const pageCost = (row: (typeof rows)[number]) =>
      row.average_cost_per_page_usd
      ?? (row.average_cost_usd !== null && averagePages ? row.average_cost_usd / averagePages : null);
    return rows.sort((left, right) => {
      if (rankingSort === "cost_asc") {
        return (pageCost(left) ?? Number.POSITIVE_INFINITY) - (pageCost(right) ?? Number.POSITIVE_INFINITY);
      }
      if (rankingSort === "cost_desc") {
        return (pageCost(right) ?? -1) - (pageCost(left) ?? -1);
      }
      return (right.average_accuracy ?? -1) - (left.average_accuracy ?? -1)
        || (pageCost(left) ?? Number.POSITIVE_INFINITY) - (pageCost(right) ?? Number.POSITIVE_INFINITY);
    });
  }, [averagePages, data, objective, rankingSort]);

  const changeObjective = (value: VisionObjective) => {
    setObjective(value);
  };

  const openCase = (example: VisionEvaluationExample) => {
    const params = new URLSearchParams({
      case_type: "vision",
      case_id: example.example_id,
      email_id: example.email_id,
      result_index: String(example.example_id.split(":").at(-1) || 0),
      objective: example.objective,
      filename: example.filename,
      conversation_id: example.conversation_id,
      content_type: example.content_type || "application/pdf",
    });
    router.push(`/settings/model-evaluation/case?${params.toString()}`);
  };

  return (
    <section className="mt-12 border-t border-slate-300 pt-10">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="flex items-center gap-3 text-2xl font-bold text-slate-900">
            <Eye className="h-7 w-7 text-indigo-600" /> Structured Document Evaluation
          </h2>
          <p className="mt-2 max-w-3xl text-slate-600">
            Structured RX and lien examples with field-level model comparison. Each document needs
            a human-reviewed reference answer before accuracy can be scored.
          </p>
        </div>
        <Button onClick={load} disabled={loading} variant="ghost" className="gap-2 border border-slate-300">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Reload vision examples
        </Button>
      </div>

      {error && <div className="mb-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {objective === "rx" && legacyRx && legacyRx.total_cases > 0 && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
          <div>
            <p className="font-semibold text-amber-900">{legacyRx.total_cases} RX case{legacyRx.total_cases === 1 ? "" : "s"} use the older extraction schema</p>
            <p className="mt-1 text-xs text-amber-800">Rerun all enabled vision models to add ICD-10/diagnosis codes and structured patient addresses.</p>
          </div>
          <Button onClick={rerunLegacyRx} disabled={legacyJob?.status === "queued" || legacyJob?.status === "running"} className="gap-2">
            {legacyJob?.status === "queued" || legacyJob?.status === "running" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {legacyJob?.status === "queued" || legacyJob?.status === "running"
              ? `${legacyJob.completed_cases}/${legacyJob.total_cases} cases completed`
              : `Rerun ${legacyRx.total_cases} legacy RX cases`}
          </Button>
        </div>
      )}
      {legacyJob?.status === "completed" && legacyJob.failed_cases > 0 && (
        <div className="mb-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
          {legacyJob.failed_cases} RX case{legacyJob.failed_cases === 1 ? "" : "s"} failed while the remaining cases completed.
        </div>
      )}
      {loading && !data ? (
        <div className="flex h-48 items-center justify-center rounded-2xl border bg-white text-slate-500">
          <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Loading processed documents…
        </div>
      ) : data ? (
        <>
          <div className="mb-6 grid gap-4 md:grid-cols-2">
            {data.coverage.map((coverage) => (
              <Card key={coverage.objective}>
                <CardContent className="p-5">
                  <div className="flex items-center justify-between">
                    <p className="font-semibold text-slate-900">{OBJECTIVE_LABELS[coverage.objective]}</p>
                    <span className="text-xl font-bold text-indigo-700">{coverage.found}/{coverage.requested}</span>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-slate-500">{coverage.description}</p>
                  <div className="mt-3 flex flex-wrap gap-1">
                    {coverage.metrics.map((metric) => <Badge key={metric} className="bg-slate-50 text-[10px] text-slate-600">{metric}</Badge>)}
                  </div>
                  {(() => {
                    const coverageObjective = coverage.objective;
                    const bulkJob = visionJobs[coverageObjective];
                    const running = bulkJob?.status === "queued" || bulkJob?.status === "running";
                    const activeModelCount = models.filter((model) => model.enabled && model.available).length;
                    return (
                      <div className="mt-4 border-t border-slate-200 pt-4">
                        <Button
                          onClick={() => startVisionBulkRun(coverageObjective)}
                          disabled={running || loading || !coverage.found || !activeModelCount}
                          className="w-full gap-2"
                        >
                          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                          {running
                            ? `${bulkJob.completed_cases}/${bulkJob.total_cases} cases completed`
                            : `Process all ${coverage.found} ${coverageObjective.toUpperCase()} cases`}
                        </Button>
                        <p className="mt-2 text-center text-[10px] text-slate-500">
                          {running
                            ? `${bulkJob.total_models} models per case`
                            : `Runs ${activeModelCount} globally enabled vision models after confirmation`}
                        </p>
                        {bulkJob?.status === "completed" && (
                          <p className={`mt-2 text-center text-[10px] ${bulkJob.failed_cases ? "text-amber-700" : "text-emerald-700"}`}>
                            Completed {bulkJob.total_cases} cases{bulkJob.failed_cases ? ` · ${bulkJob.failed_cases} failed` : ""}
                          </p>
                        )}
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>
            ))}
          </div>

          <div className="mb-5 flex flex-wrap gap-2">
            {(["rx", "lien"] as const).map((value) => (
              <button
                key={value}
                onClick={() => changeObjective(value)}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${objective === value ? "bg-slate-900 text-white" : "bg-white text-slate-600"}`}
              >
                {OBJECTIVE_LABELS[value]}
              </button>
            ))}
          </div>

          <div className="mb-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
              <div>
                <h3 className="font-semibold text-slate-900">{OBJECTIVE_LABELS[objective]} model ranking</h3>
                <p className="mt-1 text-xs text-slate-500">Average field accuracy and cost across all persisted {OBJECTIVE_LABELS[objective].toLowerCase()} evaluations.</p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                {([
                  ["accuracy", "Accuracy"],
                  ["cost_asc", "Cost low–high"],
                  ["cost_desc", "Cost high–low"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setRankingSort(value)}
                    className={`rounded-md border px-2.5 py-1 font-medium ${rankingSort === value ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            {rankings.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[700px] text-left text-xs">
                  <thead className="bg-slate-100 text-[10px] uppercase tracking-wide text-slate-500">
                    <tr><th className="p-3">Rank</th><th className="p-3">Model</th><th className="p-3">Average accuracy</th><th className="p-3">Average cost/page</th><th className="p-3">Scored cases</th><th className="p-3">Completion</th></tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {rankings.map((row, index) => (
                      <tr key={row.model_key}>
                        <td className="p-3 font-semibold text-slate-500">#{index + 1}</td>
                        <td className="p-3"><p className="font-semibold text-slate-900">{row.model}</p><p className="mt-0.5 uppercase text-[10px] text-slate-500">{row.provider}</p></td>
                        <td className="p-3 font-semibold text-slate-900">{row.average_accuracy === null ? "—" : `${row.average_accuracy.toFixed(1)}%`}</td>
                        <td className="p-3">
                          <p className="font-semibold text-slate-900">{summaryDollars(row.average_cost_per_page_usd ?? (row.average_cost_usd !== null && averagePages ? row.average_cost_usd / averagePages : null))}</p>
                          <p className="mt-0.5 text-[10px] text-slate-500">{summaryDollars(row.average_cost_usd)} per document</p>
                        </td>
                        <td className="p-3 text-slate-600">{row.scored_cases}/{row.attempted_cases}</td>
                        <td className="p-3 text-slate-600">{row.completion_rate.toFixed(0)}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="p-6 text-center text-sm text-slate-500">Run models and establish a Sol or reviewed reference to build this ranking.</p>
            )}
          </div>

          <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="hidden grid-cols-[minmax(240px,2fr)_110px_130px_120px_minmax(130px,1fr)_150px_28px] gap-4 border-b border-slate-200 bg-slate-100 px-5 py-3 text-[10px] font-bold uppercase tracking-wider text-slate-500 lg:grid">
              <span>Document</span>
              <span>Models</span>
              <span>Review</span>
              <span>Results</span>
              <span>Preferred</span>
              <span>Cost per page</span>
              <span />
            </div>
            <div className="divide-y divide-slate-200">
              {examples.map((example) => (
                <DocumentEvaluationRow
                  key={example.example_id}
                  example={example}
                  onOpen={() => openCase(example)}
                />
              ))}
              {!examples.length && (
                <p className="p-8 text-center text-sm text-slate-500">No {OBJECTIVE_LABELS[objective].toLowerCase()} are available.</p>
              )}
            </div>
          </div>
        </>
      ) : null}
    </section>
  );
}

function summaryDollars(value: number | null): string {
  return value === null ? "—" : `$${value.toFixed(6)}`;
}

function DocumentEvaluationRow({
  example,
  onOpen,
}: {
  example: VisionEvaluationExample;
  onOpen: () => void;
}) {
  const summary = example.evaluation_summary;
  const hasProblems = summary.problem_models > 0;
  const cost = summary.minimum_cost_usd === summary.maximum_cost_usd
    ? summaryDollars(example.page_count > 0 && summary.minimum_cost_usd !== null ? summary.minimum_cost_usd / example.page_count : null)
    : `${summaryDollars(example.page_count > 0 && summary.minimum_cost_usd !== null ? summary.minimum_cost_usd / example.page_count : null)} – ${summaryDollars(example.page_count > 0 && summary.maximum_cost_usd !== null ? summary.maximum_cost_usd / example.page_count : null)}`;

  return (
    <div className="bg-white">
      <button
        type="button"
        onClick={onOpen}
        className="grid w-full gap-3 px-5 py-4 text-left transition hover:bg-slate-50 sm:grid-cols-2 lg:grid-cols-[minmax(240px,2fr)_110px_130px_120px_minmax(130px,1fr)_150px_28px] lg:items-center lg:gap-4"
      >
        <div className="min-w-0 sm:col-span-2 lg:col-span-1">
          <p className="truncate text-sm font-semibold text-slate-900">{example.filename}</p>
          <p className="mt-1 text-xs text-slate-500">
            {example.document_type.toUpperCase()} · {example.page_count || "?"} page{example.page_count === 1 ? "" : "s"} · Front {example.conversation_id}
          </p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-slate-400 lg:hidden">Models</p>
          <p className="mt-1 text-sm font-semibold text-slate-800 lg:mt-0">{summary.evaluated_models}</p>
          <p className="text-[10px] text-slate-500">{summary.total_runs} total runs</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-slate-400 lg:hidden">Review</p>
          <Badge className={example.ground_truth_status === "reviewed" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : example.ground_truth_status === "sol_baseline" ? "border-indigo-200 bg-indigo-50 text-indigo-700" : "border-amber-200 bg-amber-50 text-amber-800"}>
            {example.ground_truth_status === "reviewed" ? "Ground truth saved" : example.ground_truth_status === "sol_baseline" ? "Sol baseline" : "Needs ground truth"}
          </Badge>
          <p className="mt-1 text-[10px] text-slate-500">{summary.reviewed_models}/{summary.evaluated_models} models reviewed</p>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-slate-400 lg:hidden">Results</p>
          {summary.evaluated_models === 0 ? (
            <span className="text-xs text-slate-500">Not run</span>
          ) : hasProblems ? (
            <span className="flex items-center gap-1 text-xs font-medium text-amber-700"><TriangleAlert className="h-3.5 w-3.5" /> {summary.problem_models} issue{summary.problem_models === 1 ? "" : "s"}</span>
          ) : (
            <span className="flex items-center gap-1 text-xs font-medium text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" /> {summary.completed_models} complete</span>
          )}
        </div>
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase text-slate-400 lg:hidden">Preferred</p>
          {summary.preferred_model ? (
            <p className="flex items-center gap-1 truncate text-xs font-medium text-slate-800"><Star className="h-3.5 w-3.5 fill-amber-400 text-amber-400" /> {summary.preferred_model}</p>
          ) : (
            <span className="text-xs text-slate-400">Not selected</span>
          )}
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase text-slate-400 lg:hidden">Cost per page</p>
          <p className="mt-1 text-xs font-semibold text-slate-800 lg:mt-0">{cost}</p>
          <p className="text-[10px] text-slate-500">normalized from {example.page_count || "?"} page{example.page_count === 1 ? "" : "s"}</p>
        </div>
        <div className="flex items-center justify-end text-indigo-600 sm:col-span-2 lg:col-span-1">
          <span className="mr-1 text-xs font-medium lg:hidden">View details</span>
          <ChevronRight className="h-5 w-5" />
        </div>
      </button>
    </div>
  );
}
