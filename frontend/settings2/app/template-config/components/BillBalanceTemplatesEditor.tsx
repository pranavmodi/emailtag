/**
 * BillBalanceTemplatesEditor component - edits bill/balance request template scenarios
 */

import { useState } from "react";
import { DEFAULT_TAG_SETTINGS, DUMMY_BILLING_STATUS_TABLE } from "../constants/template-config.constants";

interface BillBalanceTemplatesEditorProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  customPlaceholders: Record<string, string>;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  onSave: () => void;
  onReset: () => void;
}

type BillBalanceScenario = "balance_found" | "balance_not_found" | "lien_reminder" | "no_data" | "request_patient_id" | "escalation";

const SCENARIO_OPTIONS: Array<{ value: BillBalanceScenario; label: string; description: string; emoji: string; color: string }> = [
  { value: "balance_found", label: "Balance Found", description: "Patient balance retrieved successfully", emoji: "💰", color: "green" },
  { value: "lien_reminder", label: "Lien Reminder", description: "Missing lien signatures before bill can be produced", emoji: "📝", color: "yellow" },
  { value: "balance_not_found", label: "Patient Not Found", description: "Unable to locate patient in system", emoji: "❓", color: "red" },
  { value: "no_data", label: "No Billing Data", description: "Patient found but no billing information available", emoji: "📭", color: "yellow" },
  { value: "request_patient_id", label: "Request Patient ID", description: "First request for patient identification", emoji: "🔍", color: "blue" },
  { value: "escalation", label: "Escalation", description: "Escalate to human review after failed identification", emoji: "🚨", color: "red" },
];

export function BillBalanceTemplatesEditor({ tagSettings, customPlaceholders, onFieldChange, onSave, onReset }: BillBalanceTemplatesEditorProps) {
  const [selectedScenario, setSelectedScenario] = useState<BillBalanceScenario>("balance_found");
  const [showPreview, setShowPreview] = useState(true);

  const getTemplateKey = (scenario: BillBalanceScenario): keyof typeof DEFAULT_TAG_SETTINGS => {
    const keyMap: Record<BillBalanceScenario, keyof typeof DEFAULT_TAG_SETTINGS> = {
      balance_found: "bill_balance_found_template",
      balance_not_found: "bill_balance_not_found_template",
      lien_reminder: "bill_balance_lien_reminder_template",
      no_data: "bill_balance_no_data_template",
      request_patient_id: "bill_balance_request_patient_id_template",
      escalation: "bill_balance_escalation_template",
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
      blue: { border: "border-blue-200", bg: "bg-gradient-to-br from-blue-50 to-cyan-50", text: "text-blue-900", focusBorder: "focus:border-blue-500", focusRing: "focus:ring-blue-200" },
      red: { border: "border-red-200", bg: "bg-gradient-to-br from-red-50 to-rose-50", text: "text-red-900", focusBorder: "focus:border-red-500", focusRing: "focus:ring-red-200" },
    };
    return colorMap[color];
  };

  const colors = getColorClasses(selectedOption.color);

  // Generate preview with dummy data
  const generatePreview = () => {
    let preview = templateValue;

    // Note: Headers like "Billing Status:" and "Lien Status:" are now in the TEMPLATE, not in placeholder values

    const lienStatusTable = `<table style="border-collapse: collapse; width: 100%; margin: 10px 0;">
<tr style="background-color: #f5f5f5;">
<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Lien type</th>
<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Patient Signature</th>
<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Attorney Signature</th>
</tr>
<tr>
<td style="border: 1px solid #ddd; padding: 8px;">Technical Lien (Imaging)</td>
<td style="border: 1px solid #ddd; padding: 8px;">Signed 12/11/2025</td>
<td style="border: 1px solid #ddd; padding: 8px;">Signed 01/06/2026</td>
</tr>
<tr>
<td style="border: 1px solid #ddd; padding: 8px;">Professional Lien (Report)</td>
<td style="border: 1px solid #ddd; padding: 8px;">Signed 12/11/2025</td>
<td style="border: 1px solid #ddd; padding: 8px;">Signed 01/06/2026</td>
</tr>
</table>`;

    // Placeholder dummy data for preview
    const dummyData: Record<string, string> = {
      // Patient info placeholders
      "{patient_id}": "PRE1234567",
      "{patient_name}": "JOHN DOE",
      "{dob}": "01/15/1985",
      "{doi}": "03/20/2024",
      // Table placeholders (generated by agent)
      "{billing_status_table}": DUMMY_BILLING_STATUS_TABLE,
      "{lien_status_table}": lienStatusTable,
    };

    // Merge with custom placeholders (workspace-wide)
    const allPlaceholders = { ...dummyData };
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
      <div className="rounded-2xl border border-blue-200 bg-gradient-to-br from-blue-50 to-cyan-50 p-5">
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span className="text-lg">💵</span>
          Bill & Balance Request Templates
          <span className="ml-auto rounded-full bg-blue-600 px-2 py-0.5 text-xs text-white">
            6 Scenarios
          </span>
        </h3>
        <p className="mb-6 text-xs text-slate-600">
          Configure autoresponse templates for different billing inquiry scenarios.
        </p>

        {/* Scenario Selector Dropdown */}
        <div className="mb-6">
          <label className="mb-2 block text-sm font-semibold text-slate-700">
            Select Scenario to Edit
          </label>
          <select
            value={selectedScenario}
            onChange={(e) => setSelectedScenario(e.target.value as BillBalanceScenario)}
            className="w-full rounded-xl border-2 border-blue-300 bg-white p-3 text-base font-medium shadow-sm transition focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
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

        {/* Save Button for Bill Balance Templates */}
        <div className="mt-4 flex justify-end gap-2 border-t-2 border-blue-300 pt-4">
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
            Save Bill Balance Templates
          </button>
        </div>
      </div>
    </div>
  );
}
