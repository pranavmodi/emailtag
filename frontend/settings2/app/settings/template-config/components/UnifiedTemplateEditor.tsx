/**
 * UnifiedTemplateEditor component - edits the unified email template for Apt status req
 */

import { DEFAULT_TAG_SETTINGS, DEFAULT_UNIFIED_TEMPLATE, DEFAULT_HIPAA_TEMPLATE } from "../constants/template-config.constants";

interface UnifiedTemplateEditorProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  onSave: () => void;
  onReset: () => void;
}

export function UnifiedTemplateEditor({ tagSettings, onFieldChange, onSave, onReset }: UnifiedTemplateEditorProps) {
  return (
    <div className="space-y-4">
      {/* Main Email Template */}
      <div className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-900">
          📧 Complete Email Template
        </h3>
        <p className="mb-4 text-xs text-slate-600">
          Customize the complete autoresponse email template. Use {"{appointment_table}"} where you want the appointment information to appear.
        </p>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-slate-700">
              Email Template
            </label>
            <button
              onClick={() => onFieldChange("unified_template", DEFAULT_UNIFIED_TEMPLATE)}
              className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-200 hover:text-slate-900"
            >
              ↻ Restore to Default
            </button>
          </div>
          <textarea
            value={tagSettings.unified_template || ""}
            onChange={(event) => onFieldChange("unified_template", event.target.value)}
            placeholder="Patient ID: {patient_id_confirmed}&#10;&#10;Dear {first_name} {last_name},&#10;&#10;Our phone: {scheduling_phone}&#10;{no_show_policy}&#10;&#10;Here are your appointments:&#10;{appointment_table}&#10;&#10;{personal_injury_info}&#10;&#10;Access bills: {bills_link}"
            className="min-h-[400px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 font-mono text-sm shadow-inner focus:border-brand.indigo focus:outline-none"
          />
          <span className="text-xs text-slate-500">
            HTML and placeholders supported. Use {"{appointment_table}"} for the appointment table. See all available placeholders below.
          </span>
        </div>
      </div>

      {/* HIPAA Authorization Template */}
      <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-4">
        <h3 className="mb-3 text-sm font-semibold text-slate-900">
          🔒 HIPAA Authorization Template
        </h3>
        <p className="mb-4 text-xs text-slate-600">
          This template is sent when a sender is not authorized to access patient information. The HIPAA release form (uploaded in Document Attachments) will be attached automatically.
        </p>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <label className="text-sm font-medium text-slate-700">
              HIPAA Request Template
            </label>
            <button
              onClick={() => onFieldChange("hipaa_template", DEFAULT_HIPAA_TEMPLATE)}
              className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-200 hover:text-slate-900"
            >
              ↻ Restore to Default
            </button>
          </div>
          <textarea
            value={tagSettings.hipaa_template || ""}
            onChange={(event) => onFieldChange("hipaa_template", event.target.value)}
            placeholder="Hello,&#10;&#10;To proceed with your request for patient information, we require authorization...&#10;&#10;Thank you for your cooperation."
            className="min-h-[150px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 font-mono text-sm shadow-inner focus:border-brand.indigo focus:outline-none"
          />
          <span className="text-xs text-slate-500">
            Plain text template. Upload the HIPAA release form PDF in the Document Attachments section below with the name &quot;hipaa_form&quot;.
          </span>
        </div>
      </div>

      {/* Save Button for Templates */}
      <div className="flex justify-end gap-2 border-t border-slate-200 pt-4">
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
  );
}
