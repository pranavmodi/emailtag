"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Columns3,
  FlaskConical,
  Loader2,
  Plus,
  Save,
  Star,
  Trash2,
  TriangleAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ApiError, ModelEvaluationApi } from "@/lib/api";
import type {
  EvaluationModelOption,
  ModelEvaluationGroundTruth,
  ModelEvaluationRunRequest,
  ModelEvaluationRunResult,
} from "@/lib/types";

type Props = {
  caseType: "classification" | "vision";
  caseId: string;
  target: Omit<ModelEvaluationRunRequest, "case_type" | "model_keys">;
};

type Rating = ModelEvaluationRunResult["human_rating"];

const RATINGS: Array<{ value: Rating; label: string }> = [
  { value: null, label: "Not reviewed" },
  { value: "correct", label: "Correct" },
  { value: "minor_errors", label: "Minor errors" },
  { value: "major_errors", label: "Major errors" },
  { value: "incorrect", label: "Incorrect" },
];

const FIELD_LABELS: Record<string, string> = {
  attorney: "Attorney",
  attorney_present: "Attorney signature present",
  barcode_values: "Barcode values",
  body_parts: "Body parts",
  both_present: "Both signatures present",
  classification_path: "Classification path",
  contrast: "Contrast",
  cpt_codes: "CPT codes",
  credentials: "Credentials",
  date_of_birth: "Date of birth",
  date_of_injury: "Date of injury",
  diagnosis_codes: "ICD-10 / diagnosis codes",
  document_style: "Document style",
  exams: "Exams",
  lien_types: "Lien types",
  line1: "Address line 1",
  line2: "Address line 2",
  modifications: "Modifications",
  new_value: "New value",
  original_value: "Original value",
  patient: "Patient",
  patient_id: "Patient ID",
  patient_present: "Patient signature present",
  postal_code: "ZIP / postal code",
  provider: "Provider / doctor",
  provider_present: "Provider signature present",
  selected_checkboxes: "Selected checkboxes",
  signatures: "Signatures",
  tags: "Tags",
};

const FIELD_HINTS: Record<string, string> = {
  barcode_values: "Enter every visible 1D or 2D barcode value.",
  diagnosis_codes: "Include ICD-10, DX, reason-for-study, or diagnosis codes visible on the document.",
  exams: "Add one entry for each requested exam.",
  modifications: "Record each visible alteration or handwritten change.",
  selected_checkboxes: "Enter the labels of checked or circled choices.",
};

const HIDDEN_GROUND_TRUTH_FIELDS = new Set(["classification_path", "notes", "steps"]);

function fieldLabel(key: string): string {
  return FIELD_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizedFieldPath(path: string[]): string {
  return path.filter((part) => !/^\d+$/.test(part)).join(".");
}

function newArrayItem(path: string[]): unknown {
  const normalizedPath = normalizedFieldPath(path);
  if (normalizedPath.endsWith("exams")) {
    return {
      cpt_codes: [],
      description: "",
      body_parts: [],
      laterality: "",
      contrast: "",
      selected_checkboxes: [],
    };
  }
  if (normalizedPath.endsWith("modifications")) {
    return { field: "", original_value: "", new_value: "", description: "" };
  }
  return "";
}

function countReviewFields(value: unknown): number {
  if (Array.isArray(value)) {
    if (!value.length) return 1;
    return value.reduce((count, item) => count + countReviewFields(item), 0);
  }
  if (value && typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !HIDDEN_GROUND_TRUTH_FIELDS.has(key))
      .reduce((count, [, child]) => count + countReviewFields(child), 0);
  }
  return 1;
}

function GroundTruthField({
  fieldKey,
  value,
  path,
  onChange,
}: {
  fieldKey: string;
  value: unknown;
  path: string[];
  onChange: (value: unknown) => void;
}) {
  const label = fieldLabel(fieldKey);
  const hint = FIELD_HINTS[fieldKey];

  if (Array.isArray(value)) {
    const objectItems = value.some((item) => item !== null && typeof item === "object");
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 sm:col-span-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <label className="text-xs font-semibold text-slate-800">{label}</label>
            {hint && <p className="mt-0.5 text-[10px] text-slate-500">{hint}</p>}
          </div>
          <Button
            type="button"
            variant="ghost"
            onClick={() => onChange([...value, newArrayItem(path)])}
            className="h-8 gap-1 border border-slate-300 bg-white px-2.5 text-xs text-indigo-700 hover:bg-indigo-50"
          >
            <Plus className="h-3.5 w-3.5" /> Add {fieldKey === "exams" ? "exam" : fieldKey === "modifications" ? "modification" : "value"}
          </Button>
        </div>
        {value.length === 0 ? (
          <p className="mt-3 rounded-lg border border-dashed border-slate-300 bg-white p-3 text-xs text-slate-400">
            None recorded. Add a value if one is visible in the source.
          </p>
        ) : objectItems ? (
          <div className="mt-3 space-y-3">
            {value.map((item, index) => (
              <div key={index} className="rounded-lg border border-slate-200 bg-white p-3">
                <div className="mb-3 flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold text-slate-700">{label.replace(/s$/, "")} {index + 1}</p>
                  <button
                    type="button"
                    onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}
                    className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[10px] font-medium text-red-600 hover:bg-red-50"
                  >
                    <Trash2 className="h-3 w-3" /> Remove
                  </button>
                </div>
                {item && typeof item === "object" && !Array.isArray(item) ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {Object.entries(item as Record<string, unknown>)
                      .filter(([key]) => !HIDDEN_GROUND_TRUTH_FIELDS.has(key))
                      .map(([key, child]) => (
                        <GroundTruthField
                          key={key}
                          fieldKey={key}
                          value={child}
                          path={[...path, String(index), key]}
                          onChange={(nextChild) => {
                            const next = [...value];
                            next[index] = { ...(item as Record<string, unknown>), [key]: nextChild };
                            onChange(next);
                          }}
                        />
                      ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-3 space-y-2">
            {value.map((item, index) => (
              <div key={index} className="flex items-center gap-2">
                <input
                  aria-label={`${label} ${index + 1}`}
                  value={String(item ?? "")}
                  onChange={(event) => {
                    const next = [...value];
                    next[index] = event.target.value;
                    onChange(next);
                  }}
                  placeholder={`Enter ${label.toLocaleLowerCase().replace(/s$/, "")}`}
                  className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800"
                />
                <button
                  type="button"
                  aria-label={`Remove ${label} ${index + 1}`}
                  onClick={() => onChange(value.filter((_, itemIndex) => itemIndex !== index))}
                  className="rounded-md p-2 text-slate-400 hover:bg-red-50 hover:text-red-600"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  if (value && typeof value === "object") {
    return (
      <fieldset className="rounded-xl border border-slate-200 bg-slate-50/70 p-3 sm:col-span-2">
        <legend className="px-1 text-xs font-semibold text-slate-800">{label}</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(value as Record<string, unknown>)
            .filter(([key]) => !HIDDEN_GROUND_TRUTH_FIELDS.has(key))
            .map(([key, child]) => (
              <GroundTruthField
                key={key}
                fieldKey={key}
                value={child}
                path={[...path, key]}
                onChange={(nextChild) => onChange({ ...(value as Record<string, unknown>), [key]: nextChild })}
              />
            ))}
        </div>
      </fieldset>
    );
  }

  if (typeof value === "boolean") {
    return (
      <label className="block">
        <span className="text-xs font-semibold text-slate-700">{label}</span>
        <select
          value={value ? "true" : "false"}
          onChange={(event) => onChange(event.target.value === "true")}
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800"
        >
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
      </label>
    );
  }

  if (fieldKey === "document_style") {
    return (
      <label className="block">
        <span className="text-xs font-semibold text-slate-700">{label}</span>
        <select
          value={String(value ?? "unknown")}
          onChange={(event) => onChange(event.target.value)}
          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800"
        >
          <option value="printed">Printed</option>
          <option value="handwritten">Handwritten</option>
          <option value="mixed">Mixed</option>
          <option value="unknown">Unknown</option>
        </select>
      </label>
    );
  }

  return (
    <label className="block">
      <span className="text-xs font-semibold text-slate-700">{label}</span>
      <input
        type={typeof value === "number" ? "number" : "text"}
        value={String(value ?? "")}
        onChange={(event) => onChange(typeof value === "number" ? Number(event.target.value) : event.target.value)}
        placeholder="Not present / unreadable"
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800"
      />
      {hint && <span className="mt-1 block text-[10px] text-slate-500">{hint}</span>}
    </label>
  );
}

function dollars(value: number): string {
  if (value === 0) return "$0.000000";
  return `$${value.toFixed(6)}`;
}

function pagesProcessed(run: ModelEvaluationRunResult): number | null {
  const pages = Number(run.request_metadata?.pages_sent);
  return Number.isFinite(pages) && pages > 0 ? pages : null;
}

function costPerPage(run: ModelEvaluationRunResult): number | null {
  const pages = pagesProcessed(run);
  return pages ? run.cost_usd / pages : null;
}

function displayedCost(run: ModelEvaluationRunResult): number {
  return run.case_type === "vision" ? costPerPage(run) ?? run.cost_usd : run.cost_usd;
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function latency(run: ModelEvaluationRunResult): string {
  const duration = Number(run.request_metadata?.duration_ms);
  if (!Number.isFinite(duration) || duration < 0) return "—";
  if (duration < 1000) return `${Math.round(duration)} ms`;
  return `${(duration / 1000).toFixed(1)} s`;
}

function provenanceLabel(value: ModelEvaluationGroundTruth["reference_source"]): string {
  return {
    human: "Human-created",
    ai_seeded: "AI-seeded",
    ai_seeded_human_edited: "AI-seeded, human-corrected",
    unknown: "Legacy / unknown source",
  }[value];
}

function isIncomplete(run: ModelEvaluationRunResult): boolean {
  return run.status === "incomplete" || Boolean(run.output?.parse_error);
}

function latestComparableRunIds(
  runs: ModelEvaluationRunResult[],
  allowedModelKeys?: Set<string>
): Set<string> {
  const seen = new Set<string>();
  const ids = new Set<string>();
  for (const run of runs) {
    if (allowedModelKeys && !allowedModelKeys.has(run.model_key)) continue;
    if (seen.has(run.model_key)) continue;
    seen.add(run.model_key);
    if (run.status !== "error" && !isIncomplete(run) && run.output) ids.add(run.id);
  }
  return ids;
}

function normalize(value: unknown): string {
  if (Array.isArray(value)) return value.map(normalize).sort().join(" | ");
  if (value && typeof value === "object") return JSON.stringify(value);
  return String(value ?? "").toLocaleLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function flatten(value: unknown, prefix = ""): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return prefix ? { [prefix]: value } : {};
  }
  return Object.entries(value as Record<string, unknown>).reduce<Record<string, unknown>>(
    (result, [key, child]) => {
      if (key === "steps" || key === "classification_path" || key === "notes") return result;
      const path = prefix ? `${prefix}.${key}` : key;
      if (Array.isArray(child) && child.some((item) => item && typeof item === "object")) {
        child.forEach((item, index) => Object.assign(result, flatten(item, `${path}[${index}]`)));
      } else if (child && typeof child === "object" && !Array.isArray(child)) {
        Object.assign(result, flatten(child, path));
      } else {
        result[path] = child;
      }
      return result;
    },
    {}
  );
}

function fieldAccuracy(
  reference: Record<string, unknown> | null,
  candidate: Record<string, unknown> | null
): { score: number; matched: number; total: number } | null {
  if (!reference || !candidate) return null;
  const expected = flatten(reference);
  const actual = flatten(candidate);
  const fields = Object.keys(expected);
  if (!fields.length) return null;
  const matched = fields.filter((field) => normalize(expected[field]) === normalize(actual[field])).length;
  return { score: (matched / fields.length) * 100, matched, total: fields.length };
}

function accuracyFor(
  run: ModelEvaluationRunResult,
  referenceOutput: Record<string, unknown> | null
): { score: number; label: string } | null {
  if (
    run.case_type === "classification"
    && run.output?.evaluation_mode === "exact_production_trace_replay"
    && run.status !== "error"
    && !isIncomplete(run)
  ) {
    const passed = run.output.production_match === true;
    return {
      score: passed ? 100 : 0,
      label: passed
        ? "Every hierarchy step matched"
        : `Failed at hierarchy step ${String(run.output.failed_at_step || "unknown")}`,
    };
  }
  if (!referenceOutput || run.status === "error" || isIncomplete(run)) return null;
  const result = fieldAccuracy(referenceOutput, run.output);
  return result
    ? { score: result.score, label: `${result.matched}/${result.total} fields` }
    : null;
}

function StatusBadge({ run }: { run: ModelEvaluationRunResult }) {
  if (run.status === "error") {
    return <Badge className="gap-1 border-red-200 bg-red-50 text-red-700"><AlertCircle className="h-3 w-3" /> Error</Badge>;
  }
  if (isIncomplete(run)) {
    return <Badge className="gap-1 border-amber-200 bg-amber-50 text-amber-800"><TriangleAlert className="h-3 w-3" /> Incomplete</Badge>;
  }
  if (run.case_type === "classification" && run.output?.evaluation_mode === "exact_production_trace_replay") {
    return run.output.production_match === true
      ? <Badge className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-700"><CheckCircle2 className="h-3 w-3" /> Passed</Badge>
      : <Badge className="gap-1 border-red-200 bg-red-50 text-red-700"><AlertCircle className="h-3 w-3" /> Failed</Badge>;
  }
  return <Badge className="gap-1 border-emerald-200 bg-emerald-50 text-emerald-700"><CheckCircle2 className="h-3 w-3" /> Complete</Badge>;
}

function ModelOutput({ run, displayName }: { run: ModelEvaluationRunResult; displayName: string }) {
  const [notes, setNotes] = useState(run.human_notes || "");
  const [saving, setSaving] = useState(false);

  const saveNotes = async () => {
    setSaving(true);
    try {
      await ModelEvaluationApi.reviewRun(run.id, {
        human_rating: run.human_rating,
        human_notes: notes || null,
        is_preferred: run.is_preferred,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <article className="min-w-[360px] flex-1 rounded-xl border border-slate-200 bg-white">
      <div className="sticky top-0 z-10 border-b border-slate-200 bg-white p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="font-semibold text-slate-900">{displayName}</p>
            <p className="mt-1 text-xs text-slate-500">
              {run.provider} · {run.case_type === "vision" && costPerPage(run) !== null
                ? `${dollars(costPerPage(run) as number)}/page · ${dollars(run.cost_usd)} total`
                : dollars(run.cost_usd)}
            </p>
          </div>
          <StatusBadge run={run} />
        </div>
      </div>
      {run.error_text && (
        <div className="border-b border-amber-200 bg-amber-50 p-3 text-xs text-amber-900">
          {run.error_text}
        </div>
      )}
      <pre className="h-[520px] overflow-auto whitespace-pre-wrap break-words bg-slate-950 p-4 text-xs leading-5 text-slate-100">
        {JSON.stringify(run.output, null, 2)}
      </pre>
      <div className="space-y-2 border-t border-slate-200 p-3">
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          rows={2}
          placeholder="Note the specific omissions or hallucinations…"
          className="w-full rounded-lg border border-slate-300 p-2 text-xs text-slate-700"
        />
        <button onClick={saveNotes} disabled={saving} className="text-xs font-medium text-indigo-700 disabled:opacity-50">
          {saving ? "Saving…" : "Save reviewer notes"}
        </button>
      </div>
    </article>
  );
}

function FieldComparison({
  reference,
  runs,
  modelNames,
}: {
  reference: Record<string, unknown>;
  runs: ModelEvaluationRunResult[];
  modelNames: Record<string, string>;
}) {
  const expected = flatten(reference);
  const candidates = runs.map((run) => flatten(run.output || {}));
  return (
    <div className="mb-5 overflow-x-auto rounded-xl border border-slate-200">
      <table className="w-full min-w-[800px] text-left text-xs">
        <thead className="bg-slate-100 text-[10px] uppercase text-slate-500">
          <tr><th className="p-3">Field</th><th className="p-3">Ground truth</th>{runs.map((run) => <th key={run.id} className="p-3">{modelNames[run.model_key] || run.model}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white">
          {Object.entries(expected).map(([field, expectedValue]) => (
            <tr key={field}>
              <td className="p-3 font-medium text-slate-700">{field}</td>
              <td className="max-w-xs p-3 text-slate-800">{normalize(expectedValue) || <span className="text-slate-400">empty</span>}</td>
              {candidates.map((candidate, index) => {
                const matches = normalize(candidate[field]) === normalize(expectedValue);
                return <td key={runs[index].id} className={`max-w-xs p-3 ${matches ? "bg-emerald-50 text-emerald-800" : "bg-red-50 text-red-800"}`}><span className="mr-1 font-bold">{matches ? "✓" : "≠"}</span>{normalize(candidate[field]) || "missing"}</td>;
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function EvaluationRunner({ caseType, caseId, target }: Props) {
  const [models, setModels] = useState<EvaluationModelOption[]>([]);
  const [runs, setRuns] = useState<ModelEvaluationRunResult[]>([]);
  const [compareIds, setCompareIds] = useState<Set<string>>(new Set());
  const [groundTruth, setGroundTruth] = useState<ModelEvaluationGroundTruth | null>(null);
  const [referenceJson, setReferenceJson] = useState("{}");
  const [groundTruthNotes, setGroundTruthNotes] = useState("");
  const [seedModelKey, setSeedModelKey] = useState<string | null>(null);
  const [seedRunId, setSeedRunId] = useState<string | null>(null);
  const [seedEdited, setSeedEdited] = useState(false);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [savingTruth, setSavingTruth] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scoreSort, setScoreSort] = useState<"accuracy" | "cost_asc" | "cost_desc">("accuracy");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    Promise.all([
      ModelEvaluationApi.getModels(caseType),
      ModelEvaluationApi.getRuns(caseType, caseId),
      ModelEvaluationApi.getGroundTruth(caseType, caseId),
    ])
      .then(([catalog, history, truth]) => {
        if (!active) return;
        setModels(catalog.models);
        setRuns(history.runs);
        setGroundTruth(truth);
        const defaultSol = history.runs.find(
          (runItem) =>
            runItem.model_key === "openai:gpt-5.6-sol" &&
            runItem.status === "completed" &&
            !isIncomplete(runItem) &&
            Boolean(runItem.output)
        );
        const referenceOutput = truth.reference_output || defaultSol?.output || {};
        setReferenceJson(JSON.stringify(referenceOutput, null, 2));
        setGroundTruthNotes(truth.notes || "");
        setSeedModelKey(truth.seed_model_key || (!truth.reference_output ? defaultSol?.model_key || null : null));
        setSeedRunId(truth.seed_run_id || (!truth.reference_output ? defaultSol?.id || null : null));
        setSeedEdited(truth.reference_source === "ai_seeded_human_edited");
        setCompareIds(
          truth.reference_output
            ? latestComparableRunIds(
                history.runs,
                new Set(catalog.models.map((model) => model.key))
              )
            : new Set()
        );
      })
      .catch((err) => {
        if (active) setError(err instanceof ApiError ? err.message : "Could not load evaluation data");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => { active = false; };
  }, [caseId, caseType]);

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

  const runnableModels = useMemo(
    () => models.filter((model) => model.enabled && model.available),
    [models]
  );
  const catalogKeys = useMemo(() => new Set(models.map((model) => model.key)), [models]);
  const activeRuns = useMemo(
    () => runs.filter((run) => catalogKeys.has(run.model_key)),
    [catalogKeys, runs]
  );
  const retiredRuns = useMemo(
    () => runs.filter((run) => !catalogKeys.has(run.model_key)),
    [catalogKeys, runs]
  );
  const latestRuns = useMemo(() => {
    const seen = new Set<string>();
    return activeRuns.filter((run) => {
      if (seen.has(run.model_key)) return false;
      seen.add(run.model_key);
      return true;
    });
  }, [activeRuns]);
  const modelNames = useMemo(
    () => Object.fromEntries(models.map((model) => [model.key, model.display_name])),
    [models]
  );
  const parsedReference = useMemo<Record<string, unknown> | null>(() => {
    try {
      const parsed = JSON.parse(referenceJson);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed as Record<string, unknown>
        : null;
    } catch {
      return null;
    }
  }, [referenceJson]);
  const editableReferenceEntries = useMemo(
    () => Object.entries(parsedReference || {}).filter(([key]) => !HIDDEN_GROUND_TRUTH_FIELDS.has(key)),
    [parsedReference]
  );
  const comparisonRuns = latestRuns.filter((run) => compareIds.has(run.id));
  const comparableRuns = latestRuns.filter(
    (runItem) => runItem.status !== "error" && !isIncomplete(runItem) && Boolean(runItem.output)
  );
  const completedCount = latestRuns.filter((runItem) => runItem.status === "completed" && !isIncomplete(runItem) && (caseType !== "classification" || runItem.output?.production_match === true)).length;
  const underBudgetCount = latestRuns.filter((runItem) => runItem.status === "completed" && displayedCost(runItem) <= 0.01).length;
  const reviewedCount = latestRuns.filter((runItem) => Boolean(runItem.human_rating)).length;
  const solRun = latestRuns.find(
    (runItem) =>
      runItem.model_key === "openai:gpt-5.6-sol" &&
      runItem.status === "completed" &&
      !isIncomplete(runItem) &&
      Boolean(runItem.output)
  );
  const referenceOutput = groundTruth?.reference_output || solRun?.output || null;
  const usingSolDefault = !groundTruth?.reference_output && Boolean(solRun?.output);
  const needsRxSchemaRefresh = caseType === "vision" && target.objective === "rx" && latestRuns.some(
    (runItem) => runItem.output && !("diagnosis_codes" in runItem.output)
  );
  const scorecardRuns = useMemo(
    () => [...latestRuns].sort((left, right) => {
      if (scoreSort === "cost_asc") return displayedCost(left) - displayedCost(right);
      if (scoreSort === "cost_desc") return displayedCost(right) - displayedCost(left);
      const leftStatus = left.status === "completed" && !isIncomplete(left) ? 0 : left.status === "error" ? 2 : 1;
      const rightStatus = right.status === "completed" && !isIncomplete(right) ? 0 : right.status === "error" ? 2 : 1;
      if (leftStatus !== rightStatus) return leftStatus - rightStatus;
      const leftAccuracy = accuracyFor(left, referenceOutput)?.score ?? -1;
      const rightAccuracy = accuracyFor(right, referenceOutput)?.score ?? -1;
      if (leftAccuracy !== rightAccuracy) return rightAccuracy - leftAccuracy;
      return displayedCost(left) - displayedCost(right);
    }),
    [latestRuns, referenceOutput, scoreSort]
  );

  const run = async () => {
    if (!runnableModels.length) return;
    setRunning(true);
    setError(null);
    try {
      const job = await ModelEvaluationApi.startRun({
        ...target,
        case_type: caseType,
        model_keys: runnableModels.map((model) => model.key),
      });
      let response: Awaited<ReturnType<typeof ModelEvaluationApi.getRunJob>> | null = null;
      for (let attempt = 0; attempt < 180; attempt += 1) {
        await wait(attempt === 0 ? 1000 : 5000);
        const status = await ModelEvaluationApi.getRunJob(job.job_id);
        if (status.status === "error") {
          throw new Error(status.error || "Evaluation failed");
        }
        if (status.status === "completed") {
          response = status;
          break;
        }
      }
      if (!response) {
        throw new Error(
          "The evaluation is still running in the background. Reload this case shortly to see saved results."
        );
      }
      const updatedRuns = [...response.runs, ...runs];
      setRuns(updatedRuns);
      const newSol = response.runs.find(
        (runItem) => runItem.model_key === "openai:gpt-5.6-sol" && runItem.output
      );
      setCompareIds(
        groundTruth?.reference_output || newSol?.output || solRun?.output
          ? latestComparableRunIds(updatedRuns, catalogKeys)
          : new Set()
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setRunning(false);
    }
  };

  const seedReference = (run: ModelEvaluationRunResult) => {
    setReferenceJson(JSON.stringify(run.output || {}, null, 2));
    setSeedModelKey(run.model_key);
    setSeedRunId(run.id);
    setSeedEdited(false);
  };

  const updateReferenceField = (key: string, value: unknown) => {
    if (!parsedReference) return;
    setReferenceJson(JSON.stringify({ ...parsedReference, [key]: value }, null, 2));
    if (seedModelKey) setSeedEdited(true);
  };

  const saveGroundTruth = async (
    referenceOverride?: Record<string, unknown>,
    sourceRun?: ModelEvaluationRunResult
  ) => {
    setSavingTruth(true);
    setError(null);
    try {
      const value = referenceOverride || JSON.parse(referenceJson);
      if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Reference JSON must be an object");
      const parsed = Object.fromEntries(
        Object.entries(value as Record<string, unknown>).filter(([key]) => key !== "notes")
      );
      const activeSeedModel = sourceRun?.model_key || seedModelKey;
      const activeSeedRun = sourceRun?.id || seedRunId;
      const referenceSource = activeSeedModel
        ? (seedEdited && !sourceRun ? "ai_seeded_human_edited" : "ai_seeded")
        : "human";
      const saved = await ModelEvaluationApi.saveGroundTruth({
        case_type: caseType,
        case_id: caseId,
        reference_output: parsed,
        reference_text: null,
        notes: groundTruthNotes || null,
        reference_source: referenceSource,
        seed_model_key: activeSeedModel,
        seed_run_id: activeSeedRun,
      });
      setGroundTruth(saved);
      setReferenceJson(JSON.stringify(parsed, null, 2));
      setSeedModelKey(saved.seed_model_key);
      setSeedRunId(saved.seed_run_id);
      setSeedEdited(saved.reference_source === "ai_seeded_human_edited");
      setCompareIds(new Set(comparableRuns.map((runItem) => runItem.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save ground truth");
    } finally {
      setSavingTruth(false);
    }
  };

  const reviewRun = async (runItem: ModelEvaluationRunResult, rating: Rating, preferred = runItem.is_preferred) => {
    try {
      const updated = await ModelEvaluationApi.reviewRun(runItem.id, {
        human_rating: rating,
        human_notes: runItem.human_notes,
        is_preferred: preferred,
      });
      setRuns((current) => current.map((item) => {
        if (preferred && item.case_id === updated.case_id) return { ...item, is_preferred: item.id === updated.id };
        return item.id === updated.id ? updated : item;
      }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save review");
    }
  };

  if (loading) {
    return <div className="flex h-32 items-center justify-center text-sm text-slate-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading evaluation workspace…</div>;
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 p-4">
        <div>
          <h3 className="flex items-center gap-2 font-semibold text-slate-900"><FlaskConical className="h-4 w-4 text-indigo-600" /> Run evaluation</h3>
          <p className="mt-1 text-xs text-slate-600">
            Runs all {runnableModels.length} globally enabled compatible models.
            {caseType === "vision" && ` Only the ${target.objective === "lien" ? "lien" : "RX"} extraction schema is sent.`}
          </p>
        </div>
        <Button onClick={run} disabled={running || runnableModels.length === 0} className="gap-2">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <FlaskConical className="h-4 w-4" />}
          {running ? "Running in background…" : `Run all ${runnableModels.length} enabled models`}
        </Button>
      </section>

      {needsRxSchemaRefresh && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          These results use the older RX schema and do not include diagnosis/ICD-10 codes. Run all enabled models to replace them with current-schema results.
        </div>
      )}

      {error && <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">{error}</div>}

      {latestRuns.length > 0 && (
        <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-200 p-4">
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <h3 className="font-semibold text-slate-900">Latest-result scorecard</h3>
                <p className="mt-1 text-xs text-slate-500">
                  All {latestRuns.length} latest model results are shown. Select rows only when you want their full outputs compared below.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-slate-500">Sort:</span>
                {([
                  ["accuracy", "Accuracy"],
                  ["cost_asc", "Cost low–high"],
                  ["cost_desc", "Cost high–low"],
                ] as const).map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setScoreSort(value)}
                    className={`rounded-md border px-2.5 py-1 font-medium ${scoreSort === value ? "border-indigo-600 bg-indigo-50 text-indigo-700" : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="rounded-full bg-indigo-50 px-2.5 py-1 font-medium text-indigo-700">
                  {comparisonRuns.length ? `${comparisonRuns.length} selected` : "No detailed comparison selected"}
                </span>
                <button
                  onClick={() => setCompareIds(new Set(comparableRuns.map((item) => item.id)))}
                  className="rounded-md border border-slate-300 bg-white px-2.5 py-1 font-medium text-indigo-700 hover:bg-slate-50"
                >
                  Compare all completed
                </button>
                {comparisonRuns.length > 0 && (
                  <button onClick={() => setCompareIds(new Set())} className="px-2 py-1 font-medium text-slate-600">Clear</button>
                )}
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              <div className="rounded-lg bg-slate-50 p-3"><p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">Models tested</p><p className="mt-1 text-lg font-bold text-slate-900">{latestRuns.length}</p></div>
              <div className="rounded-lg bg-emerald-50 p-3"><p className="text-[10px] font-bold uppercase tracking-wide text-emerald-600">{caseType === "classification" ? "Passed" : "Completed"}</p><p className="mt-1 text-lg font-bold text-emerald-800">{completedCount}</p></div>
              <div className="rounded-lg bg-cyan-50 p-3"><p className="text-[10px] font-bold uppercase tracking-wide text-cyan-600">Under $0.01{caseType === "vision" ? "/page" : "/email"}</p><p className="mt-1 text-lg font-bold text-cyan-800">{underBudgetCount}</p></div>
              <div className="rounded-lg bg-amber-50 p-3"><p className="text-[10px] font-bold uppercase tracking-wide text-amber-600">Human reviewed</p><p className="mt-1 text-lg font-bold text-amber-800">{reviewedCount}/{latestRuns.length}</p></div>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1080px] text-left text-xs">
              <thead className="bg-slate-100 text-[10px] uppercase tracking-wide text-slate-500">
                <tr><th className="w-16 p-3 text-center">Details</th><th className="p-3">Model</th><th className="p-3">Result</th><th className="p-3">{caseType === "classification" ? "Exact production replay" : usingSolDefault ? "Accuracy vs Sol baseline" : "Accuracy vs ground truth"}</th><th className="p-3">{caseType === "vision" ? "Cost per page" : "Cost per email"}</th><th className="p-3">Time</th><th className="p-3">Tokens</th><th className="p-3">Human verdict</th><th className="p-3 text-center">Preferred</th></tr>
              </thead>
              <tbody className="divide-y divide-slate-200 bg-white">
                {scorecardRuns.map((runItem) => {
                  const accuracy = accuracyFor(runItem, referenceOutput);
                  const comparable = comparableRuns.some((item) => item.id === runItem.id);
                  return (
                    <tr key={runItem.id} className={`${runItem.is_preferred ? "bg-indigo-50/70" : ""} ${compareIds.has(runItem.id) ? "ring-1 ring-inset ring-indigo-200" : ""}`}>
                      <td className="p-3 text-center"><input aria-label={`Compare ${modelNames[runItem.model_key] || runItem.model}`} type="checkbox" checked={compareIds.has(runItem.id)} disabled={!comparable} onChange={() => setCompareIds((current) => { const next = new Set(current); if (next.has(runItem.id)) next.delete(runItem.id); else next.add(runItem.id); return next; })} /></td>
                      <td className="p-3"><p className="font-semibold text-slate-900">{modelNames[runItem.model_key] || runItem.model}</p><p className="mt-0.5 text-[10px] uppercase tracking-wide text-slate-500">{runItem.provider}</p></td>
                      <td className="max-w-[220px] p-3"><StatusBadge run={runItem} />{runItem.error_text && <p title={runItem.error_text} className="mt-1 truncate text-[10px] text-red-600">{runItem.error_text}</p>}</td>
                      <td className="p-3">{accuracy ? <><p className="text-base font-bold text-slate-900">{accuracy.score.toFixed(1)}%</p><p className="text-[10px] text-slate-500">{accuracy.label}</p></> : <span className="text-slate-400">Not scored</span>}</td>
                      <td className="p-3">
                        <p className={`font-semibold ${displayedCost(runItem) <= 0.01 ? "text-emerald-700" : "text-amber-700"}`}>{dollars(displayedCost(runItem))}</p>
                        {caseType === "vision" ? (
                          <p className="mt-0.5 text-[10px] text-slate-500">{pagesProcessed(runItem) || "?"} page{pagesProcessed(runItem) === 1 ? "" : "s"} · {dollars(runItem.cost_usd)} total</p>
                        ) : (
                          <p className="mt-0.5 text-[10px] text-slate-500">{runItem.cost_usd <= 0.01 ? "Within target" : "Above target"}</p>
                        )}
                      </td>
                      <td className="p-3"><p className="font-semibold text-slate-800">{latency(runItem)}</p><p className="mt-0.5 text-[10px] text-slate-500">wall time</p></td>
                      <td className="p-3 text-slate-600"><span className="font-medium text-slate-800">{runItem.total_tokens.toLocaleString()}</span> total<p className="mt-0.5 text-[10px]">{runItem.input_tokens.toLocaleString()} in · {runItem.output_tokens.toLocaleString()} out</p></td>
                      <td className="p-3"><select value={runItem.human_rating || ""} onChange={(event) => reviewRun(runItem, (event.target.value || null) as Rating)} className="rounded border border-slate-300 bg-white px-2 py-1.5"><option value="">Not reviewed</option>{RATINGS.filter((item) => item.value).map((item) => <option key={item.value} value={item.value || ""}>{item.label}</option>)}</select></td>
                      <td className="p-3 text-center"><button onClick={() => reviewRun(runItem, runItem.human_rating, !runItem.is_preferred)} aria-label="Mark preferred" className={runItem.is_preferred ? "text-amber-500" : "text-slate-300 hover:text-amber-500"}><Star className={`h-5 w-5 ${runItem.is_preferred ? "fill-current" : ""}`} /></button></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="border-t border-slate-200 bg-slate-50 px-4 py-3 text-[10px] text-slate-500">
            Ranked by completion, accuracy, then {caseType === "vision" ? "cost per page" : "cost per email"}. Token counts come directly from each provider; document input includes image tokens and may include billed reasoning tokens.
          </p>
        </section>
      )}

      {caseType === "vision" && <section id="ground-truth-editor" className="scroll-mt-4 rounded-xl border border-indigo-200 bg-indigo-50/50 p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h3 className="font-semibold text-slate-900">Evaluation ground truth</h3>
            <p className="mt-1 text-xs text-slate-600">GPT-5.6 Sol fills these fields by default. Review each value against the source, correct anything wrong, then save the human-reviewed answer.</p>
          </div>
          {groundTruth?.reference_output && groundTruth.updated_at && (
            <div className="flex flex-wrap gap-2">
              <Badge className="border-indigo-200 bg-white text-indigo-700">{provenanceLabel(groundTruth.reference_source)}</Badge>
              <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Saved {new Date(groundTruth.updated_at).toLocaleString()}</Badge>
            </div>
          )}
          {usingSolDefault && <Badge className="border-indigo-200 bg-white text-indigo-700">Sol baseline active</Badge>}
        </div>
        {solRun?.output && groundTruth?.reference_output && groundTruth.seed_model_key !== solRun.model_key && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3">
            <div>
              <p className="text-xs font-semibold text-amber-900">Use the GPT-5.6 Sol result as the reference answer</p>
              <p className="mt-0.5 text-[10px] text-amber-800">This saves Sol&apos;s structured output as ground truth for this evaluation case. You can still edit or replace it later.</p>
            </div>
            <Button
              type="button"
              variant="ghost"
              disabled={savingTruth}
              onClick={() => saveGroundTruth(solRun.output || {}, solRun)}
              className="border border-amber-300 bg-white text-amber-900 hover:bg-amber-100"
            >
              <Star className="mr-2 h-4 w-4" /> Use Sol as ground truth
            </Button>
          </div>
        )}
        {usingSolDefault && (
          <div className="mt-3 rounded-lg border border-indigo-200 bg-indigo-50 p-3">
            <p className="text-xs font-semibold text-indigo-900">GPT-5.6 Sol is the current default ground truth</p>
            <p className="mt-0.5 text-[10px] text-indigo-700">Accuracy is already scored against this AI-seeded output. Saving your corrections below creates the human-reviewed reference.</p>
          </div>
        )}
        {latestRuns.length > 0 && (
          <details className="mt-3 rounded-lg border border-indigo-100 bg-white/60 px-3 py-2">
            <summary className="cursor-pointer text-xs font-medium text-indigo-700">Use a different model output as the starting point</summary>
            <div className="mt-2 flex flex-wrap gap-2">
              {latestRuns.filter((item) => item.output).map((item) => <button key={item.id} onClick={() => seedReference(item)} className="rounded-full border border-indigo-200 bg-white px-2.5 py-1 text-[10px] font-medium text-indigo-700">{modelNames[item.model_key] || item.model}</button>)}
            </div>
          </details>
        )}
        {seedModelKey && (
          <p className="mt-3 text-[10px] font-medium text-indigo-700">
            Seeded from {modelNames[seedModelKey] || seedModelKey}{seedEdited ? " · human edits detected" : ""}
          </p>
        )}
        <div className="mt-3 rounded-xl border border-indigo-200 bg-white p-4">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-2 border-b border-slate-100 pb-3">
            <div>
              <h4 className="text-sm font-semibold text-slate-900">Review extracted fields</h4>
              <p className="mt-0.5 text-xs text-slate-500">Empty values mean the information is absent or unreadable. Add rows when the document contains multiple values.</p>
            </div>
            {parsedReference && (
              <Badge className="border-slate-200 bg-slate-50 text-slate-600">
                {countReviewFields(parsedReference)} fields to review
              </Badge>
            )}
          </div>
          {parsedReference ? (
            editableReferenceEntries.length ? (
              <div className="grid gap-3 sm:grid-cols-2">
                {editableReferenceEntries.map(([key, value]) => (
                  <GroundTruthField
                    key={key}
                    fieldKey={key}
                    value={value}
                    path={[key]}
                    onChange={(nextValue) => updateReferenceField(key, nextValue)}
                  />
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-500">No structured fields are available yet. Run GPT-5.6 Sol to create the default ground truth.</p>
            )
          ) : (
            <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">The advanced JSON is invalid. Correct it below before using the field editor.</div>
          )}
        </div>
        <details className="mt-3 rounded-lg border border-slate-200 bg-white p-3">
          <summary className="cursor-pointer text-xs font-medium text-slate-600">Advanced: edit raw JSON</summary>
          <p className="mt-2 text-[10px] text-slate-500">Use this only when you need to change the underlying structure. Invalid JSON cannot be saved.</p>
          <textarea value={referenceJson} onChange={(event) => { setReferenceJson(event.target.value); if (seedModelKey) setSeedEdited(true); }} rows={14} className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-950 p-3 font-mono text-xs leading-5 text-slate-100" />
        </details>
        <label className="mt-3 block">
          <span className="text-xs font-semibold text-slate-700">Reviewer notes (optional)</span>
          <textarea value={groundTruthNotes} onChange={(event) => setGroundTruthNotes(event.target.value)} rows={2} placeholder="Record ambiguities or anything another reviewer should know…" className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs" />
        </label>
        <Button onClick={() => saveGroundTruth()} disabled={savingTruth || !parsedReference} className="mt-3 gap-2"><Save className="h-4 w-4" />{savingTruth ? "Saving…" : "Save reviewed ground truth & rescore"}</Button>
      </section>}

      {comparisonRuns.length > 0 && (
        <section>
          <h3 className="mb-3 flex items-center gap-2 font-semibold text-slate-900"><Columns3 className="h-4 w-4 text-indigo-600" /> Side-by-side output review</h3>
          {referenceOutput && (
            <FieldComparison reference={referenceOutput} runs={comparisonRuns} modelNames={modelNames} />
          )}
          <div className="flex gap-4 overflow-x-auto pb-3">{comparisonRuns.map((runItem) => <ModelOutput key={runItem.id} run={runItem} displayName={modelNames[runItem.model_key] || runItem.model} />)}</div>
        </section>
      )}

      {retiredRuns.length > 0 && (
        <details className="rounded-xl border border-slate-200 bg-slate-50 p-4">
          <summary className="cursor-pointer text-sm font-semibold text-slate-600">Retired model results ({retiredRuns.length})</summary>
          <p className="mt-2 text-xs text-slate-500">These models were removed from the runnable catalog because their hosted endpoint was unavailable or unreliable. Results are retained only for audit history.</p>
          <div className="mt-3 space-y-2">{retiredRuns.map((runItem) => <div key={runItem.id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 bg-white p-3 text-xs"><span className="font-medium text-slate-700">{runItem.model}</span><span>{new Date(runItem.created_at).toLocaleString()}</span><StatusBadge run={runItem} /></div>)}</div>
        </details>
      )}

      <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500">All reviews and reference answers are evaluation-only. They do not change Front tags, replies, OCR records, or production processing.</p>
    </div>
  );
}
