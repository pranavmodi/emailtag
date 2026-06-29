/**
 * SenderVerificationTemplates component - edits workspace-level HIPAA sender
 * verification template and manages the HIPAA form PDF attachment.
 *
 * This template is used universally across all autoresponders (apt status, billing,
 * release of records, etc.) when a sender cannot be verified as associated with a patient.
 */

import { useState } from "react";
import { DEFAULT_TAG_SETTINGS } from "../constants/template-config.constants";
import { DocumentAttachments } from "./DocumentAttachments";

const DEFAULT_HIPAA_TEMPLATE = `Hello,

To proceed with your request for patient information, we require authorization. Please complete the attached HIPAA release form and reply to this email with the completed document.

Thank you for your cooperation.`;

interface SenderVerificationTemplatesProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  onSave: () => void;
  onReset: () => void;
  currentUser: string;
}

export function SenderVerificationTemplates({
  tagSettings,
  onFieldChange,
  onSave,
  onReset,
  currentUser,
}: SenderVerificationTemplatesProps) {
  const [showHipaaPreview, setShowHipaaPreview] = useState(false);

  const hipaaTemplate = typeof tagSettings.hipaa_template === "string"
    ? tagSettings.hipaa_template as string
    : "";

  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-rose-200 bg-gradient-to-br from-rose-50 to-pink-50 p-5">
        <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <span className="text-lg">🔒</span>
          Sender Verification Response (Universal)
        </h3>
        <p className="mb-6 text-xs text-slate-600">
          This template is used across <strong>all autoresponders</strong> (Apt Status, Billing,
          Release of Records, etc.) when a sender cannot be verified as associated with a patient.
          The HIPAA form PDF must be uploaded below for this response to be sent.
        </p>

        {/* HIPAA Template */}
        <div className="mb-6 space-y-2 rounded-xl border-2 border-rose-200 bg-gradient-to-br from-rose-50 to-pink-50 p-4">
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 text-sm font-semibold text-rose-900">
              <span className="text-lg">📋</span>
              HIPAA Authorization Request
            </label>
            <button
              onClick={() => onFieldChange("hipaa_template", DEFAULT_HIPAA_TEMPLATE)}
              className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-200"
            >
              ↻ Restore Default
            </button>
          </div>
          <textarea
            value={hipaaTemplate}
            onChange={(e) => onFieldChange("hipaa_template", e.target.value)}
            placeholder="Template for HIPAA authorization request..."
            rows={8}
            className="w-full rounded-lg border-2 border-rose-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-rose-500 focus:outline-none focus:ring-2 focus:ring-rose-200"
          />
          <p className="text-xs text-slate-500">
            The HIPAA form PDF (uploaded below) will be attached automatically to this response.
          </p>

          {/* Preview */}
          <div className="mt-2">
            <button
              onClick={() => setShowHipaaPreview(!showHipaaPreview)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
            >
              {showHipaaPreview ? "Hide Preview" : "Show Preview"}
            </button>
            {showHipaaPreview && (
              <div className="mt-2 rounded-lg border-2 border-slate-200 bg-white p-4">
                {hipaaTemplate ? (
                  <div className="whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
                    {hipaaTemplate}
                  </div>
                ) : (
                  <span className="italic text-slate-400">No template content</span>
                )}
              </div>
            )}
          </div>
        </div>

        {/* HIPAA Form PDF Attachment */}
        <DocumentAttachments
          tagName="WORKSPACE"
          templateKey="hipaa_form"
          currentUser={currentUser}
        />

        {/* Save/Reset */}
        <div className="mt-4 flex justify-end gap-2 border-t-2 border-rose-300 pt-4">
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
