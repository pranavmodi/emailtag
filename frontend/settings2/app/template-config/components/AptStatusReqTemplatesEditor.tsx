/**
 * AptStatusReqTemplatesEditor component - edits all apt status req template scenarios with dropdown selector
 */

import { useState } from "react";
import { DEFAULT_TAG_SETTINGS, DEFAULT_APT_STATUS_TEMPLATES } from "../constants/template-config.constants";
import { getDummyPlaceholders } from "../utils/template-helpers";
import { DocumentAttachments } from "./DocumentAttachments";

interface AptStatusReqTemplatesEditorProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  customPlaceholders: Record<string, string>;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  onSave: () => void;
  onReset: () => void;
  currentUser: string;
}

type AptStatusScenario =
  | "unified"
  | "not_found"
  | "db_error"
  | "request_id"
  | "request_id_escalate"
  | "hipaa"
  | "unauthorized";

const SCENARIO_OPTIONS: Array<{ value: AptStatusScenario; label: string; description: string; emoji: string; color: string }> = [
  { value: "unified", label: "Appointment Found", description: "Success - show appointment details", emoji: "✅", color: "green" },
  { value: "not_found", label: "No Appointments", description: "Patient ID found but no appointments", emoji: "📭", color: "yellow" },
  { value: "db_error", label: "Database Error", description: "Technical error fetching data", emoji: "⚠️", color: "orange" },
  { value: "request_id", label: "Request Patient ID", description: "Ask for patient identification", emoji: "🔍", color: "blue" },
  { value: "request_id_escalate", label: "Escalate to Human", description: "Still can't find patient, escalate", emoji: "👤", color: "purple" },
  { value: "hipaa", label: "HIPAA Authorization", description: "Sender not authorized, request HIPAA form", emoji: "🔒", color: "rose" },
  { value: "unauthorized", label: "Unauthorized Fallback", description: "When HIPAA form can't be sent", emoji: "🚫", color: "red" },
];

export function AptStatusReqTemplatesEditor({
  tagSettings,
  customPlaceholders,
  onFieldChange,
  onSave,
  onReset,
  currentUser
}: AptStatusReqTemplatesEditorProps) {
  const [selectedScenario, setSelectedScenario] = useState<AptStatusScenario>("unified");
  const [showPreview, setShowPreview] = useState(true);

  const getTemplateKey = (scenario: AptStatusScenario): keyof typeof DEFAULT_TAG_SETTINGS => {
    const keyMap: Record<AptStatusScenario, keyof typeof DEFAULT_TAG_SETTINGS> = {
      unified: "apt_status_unified_template",
      not_found: "apt_status_not_found_template",
      db_error: "apt_status_db_error_template",
      request_id: "apt_status_request_id_template",
      request_id_escalate: "apt_status_request_id_escalate_template",
      hipaa: "apt_status_hipaa_template",
      unauthorized: "apt_status_unauthorized_template",
    };
    return keyMap[scenario];
  };

  const getDefaultTemplate = (scenario: AptStatusScenario): string => {
    const keyMap: Record<AptStatusScenario, string> = {
      unified: DEFAULT_APT_STATUS_TEMPLATES.apt_status_unified_template,
      not_found: DEFAULT_APT_STATUS_TEMPLATES.apt_status_not_found_template,
      db_error: DEFAULT_APT_STATUS_TEMPLATES.apt_status_db_error_template,
      request_id: DEFAULT_APT_STATUS_TEMPLATES.apt_status_request_id_template,
      request_id_escalate: DEFAULT_APT_STATUS_TEMPLATES.apt_status_request_id_escalate_template,
      hipaa: DEFAULT_APT_STATUS_TEMPLATES.apt_status_hipaa_template,
      unauthorized: DEFAULT_APT_STATUS_TEMPLATES.apt_status_unauthorized_template,
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
      orange: { border: "border-orange-200", bg: "bg-gradient-to-br from-orange-50 to-amber-50", text: "text-orange-900", focusBorder: "focus:border-orange-500", focusRing: "focus:ring-orange-200" },
      blue: { border: "border-blue-200", bg: "bg-gradient-to-br from-blue-50 to-cyan-50", text: "text-blue-900", focusBorder: "focus:border-blue-500", focusRing: "focus:ring-blue-200" },
      purple: { border: "border-purple-200", bg: "bg-gradient-to-br from-purple-50 to-violet-50", text: "text-purple-900", focusBorder: "focus:border-purple-500", focusRing: "focus:ring-purple-200" },
      rose: { border: "border-rose-200", bg: "bg-gradient-to-br from-rose-50 to-pink-50", text: "text-rose-900", focusBorder: "focus:border-rose-500", focusRing: "focus:ring-rose-200" },
      red: { border: "border-red-200", bg: "bg-gradient-to-br from-red-50 to-rose-50", text: "text-red-900", focusBorder: "focus:border-red-500", focusRing: "focus:ring-red-200" },
    };
    return colorMap[color];
  };

  const colors = getColorClasses(selectedOption.color);

  // Generate preview with dummy data
  const generatePreview = () => {
    let preview = templateValue;

    // Get shared dummy placeholders
    const dummyPlaceholders = getDummyPlaceholders();

    // Merge with custom placeholders (workspace-wide)
    const allPlaceholders = { ...dummyPlaceholders };
    Object.entries(customPlaceholders).forEach(([key, value]) => {
      allPlaceholders[`{${key}}`] = value;
    });

    // Replace all placeholders
    Object.entries(allPlaceholders).forEach(([placeholder, value]) => {
      preview = preview.replace(new RegExp(placeholder.replace(/[{}]/g, '\\$&'), 'g'), value);
    });

    return preview;
  };

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-indigo-200 bg-gradient-to-br from-indigo-50 to-blue-50 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span className="text-lg">📋</span>
          Appointment Status Response Templates
          <span className="ml-auto rounded-full bg-indigo-600 px-2 py-0.5 text-xs text-white">
            7 Scenarios
          </span>
        </h3>
        <p className="mb-6 text-xs text-slate-600">
          Configure autoresponse templates for different appointment status inquiry scenarios.
        </p>

        {/* Scenario Selector Dropdown */}
        <div className="mb-6">
          <label className="mb-2 block text-sm font-semibold text-slate-700">
            Select Scenario to Edit
          </label>
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value as AptStatusScenario)}
            className="w-full rounded-xl border-2 border-indigo-300 bg-white p-3 text-base font-medium shadow-sm transition focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
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
            <button
              onClick={() => onFieldChange(templateKey, getDefaultTemplate(selectedScenario))}
              className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-200 hover:text-slate-900"
            >
              ↻ Restore Default
            </button>
          </div>
          <textarea
            value={templateValue}
            onChange={(event) => onFieldChange(templateKey, event.target.value)}
            placeholder={`Template for ${selectedOption.label.toLowerCase()}...`}
            rows={selectedScenario === "unified" ? 20 : 8}
            className={`w-full rounded-lg border-2 ${colors.border} bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 ${colors.focusBorder} focus:outline-none focus:ring-2 ${colors.focusRing}`}
          />

          {/* Scenario-specific hints */}
          {selectedScenario === "unified" && (
            <p className="text-xs text-slate-500">
              Use {"{appointment_table}"} for the appointment table, {"{personal_injury_info}"} for PI info, and custom placeholders.
            </p>
          )}
          {selectedScenario === "not_found" && (
            <p className="text-xs text-slate-500">
              Use {"{patient_id}"} to show the patient ID that was found.
            </p>
          )}
          {selectedScenario === "db_error" && (
            <p className="text-xs text-slate-500">
              Use {"{patient_id}"} to reference the patient ID in the error message.
            </p>
          )}
          {selectedScenario === "hipaa" && (
            <p className="text-xs text-slate-500">
              The HIPAA release form PDF (uploaded in Document Attachments) will be attached automatically.
            </p>
          )}
        </div>

        {/* Live Preview Section */}
        <div className="mb-4 space-y-2 rounded-xl border-2 border-slate-200 bg-gradient-to-br from-slate-50 to-gray-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-slate-700">
              <span className="text-lg">👁️</span>
              Live Preview
              <span className="text-xs font-normal text-slate-500">(with dummy data)</span>
            </label>
            <button
              onClick={() => setShowPreview(!showPreview)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
            >
              {showPreview ? "Hide Preview" : "Show Preview"}
            </button>
          </div>

          {showPreview && (
            <div className="mt-3 rounded-lg border-2 border-slate-200 bg-white p-4">
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

        {/* Per-scenario Document Attachments */}
        <DocumentAttachments
          tagName="Apt status req"
          templateKey={templateKey}
          currentUser={currentUser}
        />

        {/* Save Button for Templates */}
        <div className="mt-4 flex justify-end gap-2 border-t-2 border-indigo-300 pt-4">
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
            Save Templates
          </button>
        </div>
      </div>
    </div>
  );
}
