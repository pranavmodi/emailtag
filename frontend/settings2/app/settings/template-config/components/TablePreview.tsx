"use client";

import { useState } from "react";
import { ApiError, TemplatesApi } from "@/lib/api";

const TABLE_TYPE_OPTIONS = [
  { value: "appointment_table", label: "Appointment Table" },
  { value: "billing_status_table", label: "Billing Status" },
  { value: "lien_status_table", label: "Lien Status" },
  { value: "call_log_table", label: "Call Log" },
  { value: "text_log_table", label: "Text Log" },
];

export function TablePreview() {
  const [patientId, setPatientId] = useState("");
  const [tableType, setTableType] = useState(TABLE_TYPE_OPTIONS[0].value);
  const [signatureType, setSignatureType] = useState("ASL");
  const [loading, setLoading] = useState(false);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    const trimmed = patientId.trim();
    if (!trimmed) {
      setError("Please enter a Patient ID.");
      return;
    }

    setLoading(true);
    setError(null);
    setHtml(null);

    try {
      const result = await TemplatesApi.previewTable(
        trimmed,
        tableType,
        tableType === "lien_status_table" ? signatureType : undefined
      );
      setHtml(result.html);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(err instanceof Error ? err.message : "An unexpected error occurred.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-4 text-lg font-semibold text-slate-800">
        Live Table Preview
      </h3>
      <p className="mb-4 text-sm text-slate-500">
        Enter a real patient ID and select a table type to preview the exact HTML
        table that would appear in a production autorespond email.
      </p>

      <div className="flex flex-wrap items-end gap-3">
        {/* Patient ID */}
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
          Patient ID
          <input
            type="text"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleGenerate();
            }}
            placeholder="e.g. 12345"
            className="w-44 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-inner focus:border-indigo-400 focus:outline-none"
          />
        </label>

        {/* Table Type */}
        <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
          Table Type
          <select
            value={tableType}
            onChange={(e) => setTableType(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-inner focus:border-indigo-400 focus:outline-none"
          >
            {TABLE_TYPE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </label>

        {/* Signature Type (lien only) */}
        {tableType === "lien_status_table" && (
          <label className="flex flex-col gap-1 text-sm font-medium text-slate-700">
            Signature Type
            <select
              value={signatureType}
              onChange={(e) => setSignatureType(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-inner focus:border-indigo-400 focus:outline-none"
            >
              <option value="ASL">ASL</option>
              <option value="PSL">PSL</option>
            </select>
          </label>
        )}

        {/* Generate Button */}
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white shadow hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? (
            <span className="flex items-center gap-2">
              <svg
                className="h-4 w-4 animate-spin"
                viewBox="0 0 24 24"
                fill="none"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                />
              </svg>
              Generating...
            </span>
          ) : (
            "Generate Preview"
          )}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {/* Preview */}
      {html !== null && !error && (
        <div className="mt-4">
          <div className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">
            Preview Output
          </div>
          <div
            className="overflow-x-auto rounded-lg border border-slate-200 bg-white p-4"
            dangerouslySetInnerHTML={{ __html: html }}
          />
        </div>
      )}
    </div>
  );
}
