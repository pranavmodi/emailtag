/**
 * TemplatePreview component - live preview of email template with dummy data
 */

import { DEFAULT_TAG_SETTINGS } from "../constants/template-config.constants";
import { generatePreviewHtml } from "../utils/template-helpers";

interface TemplatePreviewProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  showPreview: boolean;
  setShowPreview: (show: boolean) => void;
  showPersonalInjuryInPreview: boolean;
  setShowPersonalInjuryInPreview: (show: boolean) => void;
}

export function TemplatePreview({
  tagSettings,
  showPreview,
  setShowPreview,
  showPersonalInjuryInPreview,
  setShowPersonalInjuryInPreview,
}: TemplatePreviewProps) {
  const previewHtml = generatePreviewHtml(tagSettings, showPersonalInjuryInPreview);

  return (
    <div className="rounded-2xl border border-purple-200 bg-gradient-to-br from-purple-50 to-indigo-50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          👁️ Live Preview
          <span className="text-xs font-normal text-slate-500">
            (using dummy patient data)
          </span>
        </h3>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-2 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={showPersonalInjuryInPreview}
              onChange={(e) => setShowPersonalInjuryInPreview(e.target.checked)}
              className="rounded border-slate-300"
            />
            Show Personal Injury Info
          </label>
          <button
            onClick={() => setShowPreview(!showPreview)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
          >
            {showPreview ? "Hide" : "Show"} Preview
          </button>
        </div>
      </div>

      {showPreview && (
        <div className="rounded-xl border border-slate-300 bg-white p-4 shadow-inner">
          <div
            className="max-w-none [&_ul]:list-disc [&_ul]:ml-6 [&_ul]:my-2 [&_ol]:list-decimal [&_ol]:ml-6 [&_ol]:my-2 [&_li]:my-1 [&_p]:my-2 [&_br]:block [&_a]:text-blue-600 [&_a]:underline [&_b]:font-bold [&_strong]:font-bold"
            dangerouslySetInnerHTML={{ __html: previewHtml }}
          />
        </div>
      )}
    </div>
  );
}
