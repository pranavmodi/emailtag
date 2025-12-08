/**
 * LienTemplatesEditor component - edits 4 lien template scenarios
 */

import { DEFAULT_TAG_SETTINGS } from "../constants/template-config.constants";

interface LienTemplatesEditorProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  onSave: () => void;
  onReset: () => void;
}

export function LienTemplatesEditor({ tagSettings, onFieldChange, onSave, onReset }: LienTemplatesEditorProps) {
  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-purple-200 bg-gradient-to-br from-purple-50 to-indigo-50 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span className="text-lg">📄</span>
          Lien Response Templates
          <span className="ml-auto rounded-full bg-purple-600 px-2 py-0.5 text-xs text-white">
            4 Scenarios
          </span>
        </h3>
        <p className="mb-4 text-xs text-slate-600">
          Configure autoresponse templates for different lien processing scenarios. Available placeholders: {"{lien_type}"}, {"{patient_id}"}, {"{patient_name}"}, {"{dob}"}, {"{doi}"}
        </p>

        {/* Success Template */}
        <div className="mb-4 space-y-2 rounded-xl border-2 border-green-200 bg-gradient-to-br from-green-50 to-emerald-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-green-900">
              <span className="text-lg">✅</span>
              Success Template
              <span className="text-xs font-normal text-slate-600">(Patient found, lien uploaded)</span>
            </label>
          </div>
          <textarea
            value={tagSettings.lien_success_template || ""}
            onChange={(event) => onFieldChange("lien_success_template", event.target.value)}
            placeholder="Template for successful lien upload..."
            rows={8}
            className="w-full rounded-lg border-2 border-green-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-green-500 focus:outline-none focus:ring-2 focus:ring-green-200"
          />
        </div>

        {/* Unreadable Template */}
        <div className="mb-4 space-y-2 rounded-xl border-2 border-orange-200 bg-gradient-to-br from-orange-50 to-amber-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-orange-900">
              <span className="text-lg">🔍</span>
              Unreadable Document Template
              <span className="text-xs font-normal text-slate-600">(Blurry/poor quality)</span>
            </label>
          </div>
          <textarea
            value={tagSettings.lien_unreadable_template || ""}
            onChange={(event) => onFieldChange("lien_unreadable_template", event.target.value)}
            placeholder="Template for unreadable lien documents..."
            rows={8}
            className="w-full rounded-lg border-2 border-orange-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-200"
          />
        </div>

        {/* Patient Not Found Template */}
        <div className="mb-4 space-y-2 rounded-xl border-2 border-yellow-200 bg-gradient-to-br from-yellow-50 to-amber-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-yellow-900">
              <span className="text-lg">❓</span>
              Patient Not Found Template
              <span className="text-xs font-normal text-slate-600">(Will tag for human review)</span>
            </label>
          </div>
          <textarea
            value={tagSettings.lien_patient_not_found_template || ""}
            onChange={(event) => onFieldChange("lien_patient_not_found_template", event.target.value)}
            placeholder="Template when patient cannot be located..."
            rows={8}
            className="w-full rounded-lg border-2 border-yellow-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-yellow-500 focus:outline-none focus:ring-2 focus:ring-yellow-200"
          />
        </div>

        {/* Modified Lien Template */}
        <div className="mb-4 space-y-2 rounded-xl border-2 border-red-200 bg-gradient-to-br from-red-50 to-rose-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-red-900">
              <span className="text-lg">⚠️</span>
              Modified Lien Template
              <span className="text-xs font-normal text-slate-600">(Strikethrough/alterations detected)</span>
            </label>
          </div>
          <textarea
            value={tagSettings.lien_modified_template || ""}
            onChange={(event) => onFieldChange("lien_modified_template", event.target.value)}
            placeholder="Template for modified lien documents..."
            rows={8}
            className="w-full rounded-lg border-2 border-red-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-red-500 focus:outline-none focus:ring-2 focus:ring-red-200"
          />
        </div>

        {/* Save Button for Lien Templates */}
        <div className="mt-4 flex justify-end gap-2 border-t-2 border-purple-300 pt-4">
          <button
            onClick={onReset}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
          >
            Reset
          </button>
          <button
            onClick={onSave}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
          >
            Save Lien Templates
          </button>
        </div>
      </div>
    </div>
  );
}
