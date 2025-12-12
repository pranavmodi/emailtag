/**
 * LienTemplatesEditor component - edits 5 lien template scenarios with dropdown selectors
 */

import { useState } from "react";
import { DEFAULT_TAG_SETTINGS, DUMMY_LIEN_STATUS_TABLE } from "../constants/template-config.constants";

interface LienTemplatesEditorProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  onSave: () => void;
  onReset: () => void;
}

type LienScenario = "success" | "patient_not_found" | "reject_no_changes" | "reject_not_readable" | "reject_sig_not_valid";

const SCENARIO_OPTIONS: Array<{ value: LienScenario; label: string; description: string; emoji: string; color: string }> = [
  { value: "success", label: "Success", description: "Patient found, lien uploaded", emoji: "✅", color: "green" },
  { value: "patient_not_found", label: "Patient Not Found", description: "Will tag for human review", emoji: "❓", color: "yellow" },
  { value: "reject_no_changes", label: "Reply & Reject - No Changes", description: "Cross-outs, black-outs, added text", emoji: "✏️", color: "red" },
  { value: "reject_not_readable", label: "Reply & Reject - Not Readable", description: "Blurry or poor quality", emoji: "🔍", color: "orange" },
  { value: "reject_sig_not_valid", label: "Reply & Reject - Sig Not Valid", description: "Wrong box or outside designated area", emoji: "🖊️", color: "pink" },
];

export function LienTemplatesEditor({ tagSettings, onFieldChange, onSave, onReset }: LienTemplatesEditorProps) {
  const [selectedScenario, setSelectedScenario] = useState<LienScenario>("success");
  const [showPreview, setShowPreview] = useState(true);

  const getTemplateKey = (scenario: LienScenario): keyof typeof DEFAULT_TAG_SETTINGS => {
    const keyMap: Record<LienScenario, keyof typeof DEFAULT_TAG_SETTINGS> = {
      success: "lien_success_template",
      patient_not_found: "lien_patient_not_found_template",
      reject_no_changes: "lien_reject_no_changes_template",
      reject_not_readable: "lien_reject_not_readable_template",
      reject_sig_not_valid: "lien_reject_sig_not_valid_template",
    };
    return keyMap[scenario];
  };

  const selectedOption = SCENARIO_OPTIONS.find(opt => opt.value === selectedScenario)!;
  const templateKey = getTemplateKey(selectedScenario);
  const templateValue = typeof tagSettings[templateKey] === 'string' ? tagSettings[templateKey] : "";

  const getColorClasses = (color: string) => {
    const colorMap: Record<string, { border: string; bg: string; text: string; focusBorder: string; focusRing: string }> = {
      green: { border: "border-green-200", bg: "bg-gradient-to-br from-green-50 to-emerald-50", text: "text-green-900", focusBorder: "focus:border-green-500", focusRing: "focus:ring-green-200" },
      yellow: { border: "border-yellow-200", bg: "bg-gradient-to-br from-yellow-50 to-amber-50", text: "text-yellow-900", focusBorder: "focus:border-yellow-500", focusRing: "focus:ring-yellow-200" },
      red: { border: "border-red-200", bg: "bg-gradient-to-br from-red-50 to-rose-50", text: "text-red-900", focusBorder: "focus:border-red-500", focusRing: "focus:ring-red-200" },
      orange: { border: "border-orange-200", bg: "bg-gradient-to-br from-orange-50 to-amber-50", text: "text-orange-900", focusBorder: "focus:border-orange-500", focusRing: "focus:ring-orange-200" },
      pink: { border: "border-pink-200", bg: "bg-gradient-to-br from-pink-50 to-rose-50", text: "text-pink-900", focusBorder: "focus:border-pink-500", focusRing: "focus:ring-pink-200" },
    };
    return colorMap[color];
  };

  const colors = getColorClasses(selectedOption.color);

  // Generate preview with dummy data
  const generatePreview = () => {
    let preview = templateValue;
    const dummyData: Record<string, string> = {
      "{lien_type}": "Attorney Signed Lien (ASL)",
      "{patient_id}": "PRE1234567",
      "{patient_name}": "John Doe",
      "{dob}": "01/15/1985",
      "{doi}": "03/22/2024",
      "{lien_status_table}": DUMMY_LIEN_STATUS_TABLE,
    };

    Object.entries(dummyData).forEach(([placeholder, value]) => {
      preview = preview.replace(new RegExp(placeholder.replace(/[{}]/g, '\\$&'), 'g'), value);
    });

    return preview;
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-purple-200 bg-gradient-to-br from-purple-50 to-indigo-50 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span className="text-lg">📄</span>
          Lien Response Templates
          <span className="ml-auto rounded-full bg-purple-600 px-2 py-0.5 text-xs text-white">
            5 Scenarios
          </span>
        </h3>
        <p className="mb-6 text-xs text-slate-600">
          Configure autoresponse templates for different lien processing scenarios.
        </p>

        {/* Scenario Selector Dropdown */}
        <div className="mb-6">
          <label className="mb-2 block text-sm font-semibold text-slate-700">
            Select Scenario to Edit
          </label>
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value as LienScenario)}
            className="w-full rounded-xl border-2 border-purple-300 bg-white p-3 text-base font-medium shadow-sm transition focus:border-purple-500 focus:outline-none focus:ring-2 focus:ring-purple-200"
          >
            {SCENARIO_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.emoji} {option.label} - {option.description}
              </option>
            ))}
          </select>
        </div>

        {/* Dynamic Template Editor based on selected scenario */}
        <div className={`mb-4 space-y-2 rounded-xl border-2 ${colors.border} ${colors.bg} p-4`}>
          <div className="flex items-center justify-between">
            <label className={`flex items-center gap-2 text-sm font-semibold ${colors.text}`}>
              <span className="text-lg">{selectedOption.emoji}</span>
              {selectedOption.label}
              <span className="text-xs font-normal text-slate-600">({selectedOption.description})</span>
            </label>
          </div>
          <textarea
            value={templateValue}
            onChange={(event) => onFieldChange(templateKey, event.target.value)}
            placeholder={`Template for ${selectedOption.label.toLowerCase()}...`}
            rows={12}
            className={`w-full rounded-lg border-2 ${colors.border} bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 ${colors.focusBorder} focus:outline-none focus:ring-2 ${colors.focusRing}`}
          />
        </div>

        {/* Live Preview Section */}
        <div className="mb-4 space-y-2 rounded-xl border-2 border-indigo-200 bg-gradient-to-br from-indigo-50 to-blue-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-indigo-900">
              <span className="text-lg">👁️</span>
              Live Preview
              <span className="text-xs font-normal text-slate-600">(with dummy data)</span>
            </label>
            <button
              onClick={() => setShowPreview(!showPreview)}
              className="rounded-lg border border-indigo-300 bg-white px-3 py-1 text-xs font-medium text-indigo-700 transition hover:bg-indigo-50"
            >
              {showPreview ? "Hide Preview" : "Show Preview"}
            </button>
          </div>

          {showPreview && (
            <div className="mt-3 rounded-lg border-2 border-indigo-200 bg-white p-4">
              {generatePreview() ? (
                <div
                  className="text-sm leading-relaxed text-slate-700"
                  dangerouslySetInnerHTML={{ __html: generatePreview() }}
                />
              ) : (
                <span className="text-slate-400 italic">No template content to preview</span>
              )}
            </div>
          )}
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
