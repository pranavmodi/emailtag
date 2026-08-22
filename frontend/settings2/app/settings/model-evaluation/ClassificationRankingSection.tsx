"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart3, Loader2, Play } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ApiError, ModelEvaluationApi } from "@/lib/api";
import type {
  ClassificationBulkJobStatusResponse,
  ClassificationModelRanking,
  ClassificationRankingResponse,
  EvaluationModelOption,
} from "@/lib/types";

type RankingSort = "accuracy" | "cost_asc" | "cost_desc";

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function dollars(value: number | null): string {
  return value === null ? "—" : `$${value.toFixed(6)}`;
}

function endToEndSuccess(row: ClassificationModelRanking): number | null {
  return row.attempted_cases
    ? row.exact_matches / row.attempted_cases * 100
    : null;
}

function outcomeCounts(row: ClassificationModelRanking) {
  return {
    mismatches: row.classification_mismatches
      ?? Math.max(0, row.scored_cases - row.exact_matches),
    errors: row.execution_errors
      ?? Math.max(0, row.attempted_cases - row.scored_cases),
  };
}

export function ClassificationRankingSection({ conversationIds }: { conversationIds: string[] }) {
  const [ranking, setRanking] = useState<ClassificationRankingResponse | null>(null);
  const [models, setModels] = useState<EvaluationModelOption[]>([]);
  const [job, setJob] = useState<ClassificationBulkJobStatusResponse | null>(null);
  const [sort, setSort] = useState<RankingSort>("accuracy");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadRanking = useCallback(async () => {
    if (!conversationIds.length) return;
    const [rankingResponse, catalog] = await Promise.all([
      ModelEvaluationApi.getClassificationRankings(conversationIds),
      ModelEvaluationApi.getModels("classification"),
    ]);
    setRanking(rankingResponse);
    setModels(catalog.models);
  }, [conversationIds]);

  const pollJob = useCallback(async (jobId: string) => {
    while (true) {
      await wait(5000);
      let status: ClassificationBulkJobStatusResponse;
      try {
        status = await ModelEvaluationApi.getClassificationBulkJob(jobId);
      } catch (err) {
        if (err instanceof ApiError && err.status >= 500) continue;
        window.localStorage.removeItem("classification-evaluation-job");
        setJob(null);
        throw new Error("The previous classification job is no longer active. Start it again to continue.");
      }
      setJob(status);
      if (status.status === "error") {
        window.localStorage.removeItem("classification-evaluation-job");
        throw new Error(status.error || "Classification evaluation failed");
      }
      if (status.status === "completed") {
        window.localStorage.removeItem("classification-evaluation-job");
        await loadRanking();
        return;
      }
    }
  }, [loadRanking]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    loadRanking()
      .then(async () => {
        if (!active) return;
        const activeJob = await ModelEvaluationApi.getActiveClassificationBulkJob();
        if (activeJob) {
          setJob(activeJob);
          window.localStorage.setItem("classification-evaluation-job", activeJob.job_id);
          await pollJob(activeJob.job_id);
        } else {
          setJob(null);
          window.localStorage.removeItem("classification-evaluation-job");
        }
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Could not load classification rankings");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [loadRanking, pollJob]);

  useEffect(() => {
    const handleSettingChange = (event: Event) => {
      const updated = (event as CustomEvent<EvaluationModelOption>).detail;
      if (!updated) return;
      setModels((current) =>
        current.map((model) => model.key === updated.key ? updated : model)
      );
    };
    window.addEventListener("model-evaluation-settings-changed", handleSettingChange);
    return () => window.removeEventListener("model-evaluation-settings-changed", handleSettingChange);
  }, []);

  const activeModels = useMemo(
    () => models.filter((model) => model.enabled && model.available),
    [models]
  );
  const modelNames = useMemo(
    () => Object.fromEntries(models.map((model) => [model.key, model.display_name])),
    [models]
  );
  const activeModelKeys = useMemo(
    () => new Set(activeModels.map((model) => model.key)),
    [activeModels]
  );
  const rows = useMemo(() => {
    const values = (ranking?.rankings || []).filter((row) => activeModelKeys.has(row.model_key));
    return values.sort((left, right) => {
      if (sort === "cost_asc") {
        return (left.average_cost_usd ?? Number.POSITIVE_INFINITY) - (right.average_cost_usd ?? Number.POSITIVE_INFINITY);
      }
      if (sort === "cost_desc") {
        return (right.average_cost_usd ?? -1) - (left.average_cost_usd ?? -1);
      }
      return (endToEndSuccess(right) ?? -1) - (endToEndSuccess(left) ?? -1)
        || (left.average_cost_usd ?? Number.POSITIVE_INFINITY) - (right.average_cost_usd ?? Number.POSITIVE_INFINITY);
    });
  }, [activeModelKeys, ranking, sort]);
  const running = job?.status === "queued" || job?.status === "running";

  const start = async () => {
    setError(null);
    try {
      const started = await ModelEvaluationApi.startClassificationBulkRun(conversationIds);
      const initial: ClassificationBulkJobStatusResponse = {
        ...started,
        completed_cases: 0,
        failed_cases: 0,
        current_case_id: null,
        errors: [],
        error: null,
      };
      setJob(initial);
      window.localStorage.setItem("classification-evaluation-job", started.job_id);
      await pollJob(started.job_id);
    } catch (err) {
      setError(err instanceof ApiError || err instanceof Error ? err.message : "Could not run classification dataset");
    }
  };

  const progress = job?.total_cases
    ? Math.round(job.completed_cases / job.total_cases * 100)
    : 0;

  return (
    <section className="mb-6 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 p-5">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-bold text-slate-900">
            <BarChart3 className="h-5 w-5 text-indigo-600" /> Email classification ranking
          </h2>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500">
            Replays the exact stored production prompt and OCR context at every hierarchy step. A model passes only when every choice matches production; the first divergence fails that email.
            OCR is not rerun. Provider and output-format errors count as failed attempts. Completed email results are saved case by case.
          </p>
        </div>
        <Button
          onClick={start}
          disabled={running || loading || !conversationIds.length || !activeModels.length}
          className="gap-2"
        >
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          {running
            ? `${job.completed_cases}/${job.total_cases} emails completed`
            : `Run all ${conversationIds.length} emails × ${activeModels.length} models`}
        </Button>
      </div>

      {running && job && (
        <div className="border-b border-slate-200 bg-indigo-50 px-5 py-4">
          <div className="flex justify-between text-xs font-medium text-indigo-800">
            <span>{job.completed_cases}/{job.total_cases} emails · {job.total_models} models each</span>
            <span>{progress}%</span>
          </div>
          <div className="mt-2 h-2 overflow-hidden rounded-full bg-indigo-100">
            <div className="h-full rounded-full bg-indigo-600 transition-all" style={{ width: `${progress}%` }} />
          </div>
          {job.current_case_id && <p className="mt-2 text-[10px] text-indigo-700">Currently evaluating {job.current_case_id}</p>}
        </div>
      )}

      {error && <div className="border-b border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}
      {job?.status === "completed" && job.failed_cases > 0 && (
        <div className="border-b border-amber-200 bg-amber-50 p-4 text-xs text-amber-800">
          {job.failed_cases} email{job.failed_cases === 1 ? "" : "s"} could not be prepared. The remaining cases were ranked normally.
        </div>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-3">
        <p className="text-xs text-slate-500">
          {ranking ? `${ranking.reference_cases}/${ranking.shortlisted_cases} emails have a stored production reference` : "Loading ranking…"}
        </p>
        <div className="flex flex-wrap gap-2 text-xs">
          {([
            ["accuracy", "End-to-end success"],
            ["cost_asc", "Cost low–high"],
            ["cost_desc", "Cost high–low"],
          ] as const).map(([value, label]) => (
            <button
              key={value}
              onClick={() => setSort(value)}
              className={`rounded-md border px-2.5 py-1 font-medium ${sort === value ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-slate-300 text-slate-600"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] text-left text-xs">
            <thead className="bg-slate-100 text-[10px] uppercase tracking-wide text-slate-500">
              <tr><th className="p-3">Rank</th><th className="p-3">Model</th><th className="p-3">End-to-end exact match</th><th className="p-3">Outcomes</th><th className="p-3">Average cost/email</th><th className="p-3">Total cost</th><th className="p-3">Coverage</th><th className="p-3">Avg tokens</th></tr>
            </thead>
            <tbody className="divide-y divide-slate-200">
              {rows.map((row: ClassificationModelRanking, index) => {
                const success = endToEndSuccess(row);
                const { mismatches, errors } = outcomeCounts(row);
                return <tr key={row.model_key} className="align-top">
                  <td className="p-3 font-semibold text-slate-500">#{index + 1}</td>
                  <td className="p-3">
                    <p className="font-semibold text-slate-900">{modelNames[row.model_key] || row.model}</p>
                    <p className="mt-0.5 text-[10px] uppercase text-slate-500">{row.provider}</p>
                  </td>
                  <td className="p-3"><p className="font-bold text-slate-900">{success === null ? "—" : `${success.toFixed(1)}%`}</p><p className="mt-1 text-[10px] text-slate-500">{row.exact_matches}/{row.attempted_cases} attempts matched</p></td>
                  <td className="p-3">
                    <div className="flex flex-wrap gap-1.5 text-[10px] font-semibold">
                      <span className="rounded-full bg-emerald-50 px-2 py-1 text-emerald-700">{row.exact_matches} exact</span>
                      <span className="rounded-full bg-amber-50 px-2 py-1 text-amber-700">{mismatches} mismatch{mismatches === 1 ? "" : "es"}</span>
                      <span className="rounded-full bg-red-50 px-2 py-1 text-red-700">{errors} error{errors === 1 ? "" : "s"}</span>
                    </div>
                  </td>
                  <td className="p-3 font-semibold text-slate-900">{dollars(row.average_cost_usd)}</td>
                  <td className="p-3 text-slate-700">{dollars(row.total_cost_usd)}</td>
                  <td className="p-3"><p className="text-slate-700">{row.attempted_cases}/{ranking?.reference_cases || 0} attempted</p><p className="mt-1 text-[10px] text-slate-500">{row.scored_cases} valid outputs · {row.completion_rate.toFixed(0)}% execution success</p></td>
                  <td className="p-3 text-slate-700">{row.average_tokens.toLocaleString()}</td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-8 text-center text-sm text-slate-500">
          No dataset-wide classification results yet. Use the button above to run every shortlisted email.
        </p>
      )}
    </section>
  );
}
