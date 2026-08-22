"use client";

import { useEffect, useMemo, useState } from "react";
import { Loader2, Settings2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { ApiError, ModelEvaluationApi } from "@/lib/api";
import type { EvaluationModelOption } from "@/lib/types";

export function ModelControls() {
  const [models, setModels] = useState<EvaluationModelOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ModelEvaluationApi.getModels()
      .then((response) => setModels(response.models))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Could not load model controls"))
      .finally(() => setLoading(false));
  }, []);

  const providers = useMemo(
    () => Array.from(new Set(models.map((model) => model.provider))),
    [models]
  );

  const toggle = async (model: EvaluationModelOption) => {
    setSaving(model.key);
    setError(null);
    try {
      const updated = await ModelEvaluationApi.setModelEnabled(model.key, !model.enabled);
      setModels((current) => current.map((item) => item.key === updated.key ? updated : item));
      window.dispatchEvent(
        new CustomEvent("model-evaluation-settings-changed", { detail: updated })
      );
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update model");
    } finally {
      setSaving(null);
    }
  };

  return (
    <details className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <summary className="cursor-pointer list-none">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
              <Settings2 className="h-4 w-4 text-indigo-600" /> Evaluation model controls
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Global controls for email and document evaluation. Every case runs all enabled compatible models. Production is unaffected.
            </p>
          </div>
          <Badge className="border-slate-200 bg-slate-50 text-slate-600">
            {models.filter((model) => model.enabled).length}/{models.length || "—"} enabled
          </Badge>
        </div>
      </summary>

      {loading ? (
        <p className="mt-4 flex items-center text-xs text-slate-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading models…</p>
      ) : (
        <div className="mt-5 grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {providers.map((provider) => (
            <div key={provider}>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">{provider}</p>
              <div className="space-y-2">
                {models.filter((model) => model.provider === provider).map((model) => (
                  <div key={model.key} className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 p-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-slate-800">{model.display_name}</p>
                      <p className="text-[10px] text-slate-500">{model.case_types.join(" + ")}</p>
                    </div>
                    <button
                      type="button"
                      role="switch"
                      aria-checked={model.enabled}
                      disabled={saving === model.key}
                      onClick={() => toggle(model)}
                      className={`relative h-6 w-11 shrink-0 rounded-full transition ${model.enabled ? "bg-indigo-600" : "bg-slate-300"}`}
                    >
                      <span className={`absolute top-1 h-4 w-4 rounded-full bg-white transition ${model.enabled ? "left-6" : "left-1"}`} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
      {error && <p className="mt-3 text-xs text-red-600">{error}</p>}
    </details>
  );
}
