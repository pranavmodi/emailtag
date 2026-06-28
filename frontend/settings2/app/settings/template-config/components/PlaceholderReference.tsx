/**
 * PlaceholderReference component - displays available placeholders documentation
 */

import { DEFAULT_TAG_SETTINGS } from "../constants/template-config.constants";

interface PlaceholderReferenceProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
}

export function PlaceholderReference({ tagSettings }: PlaceholderReferenceProps) {
  return (
    <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 p-5">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <span className="text-lg">📋</span>
        Available Placeholders
        <span className="ml-auto rounded-full bg-emerald-600 px-2 py-0.5 text-xs text-white">
          Copy & Paste
        </span>
      </h3>
      <p className="mb-4 text-xs text-slate-600">
        Use these placeholders in any text field above. They will be automatically replaced with actual patient data when sending autoresponds.
      </p>

      <div className="space-y-3">
        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
            Patient Information
          </h4>
          <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{first_name}"}
            </code>
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{last_name}"}
            </code>
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{dob}"}
            </code>
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{address}"}
            </code>
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{home_phone}"}
            </code>
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{cell_phone}"}
            </code>
            <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
              {"{patient_id_confirmed}"}
            </code>
          </div>
        </div>

        <div>
          <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-700">
            Special Placeholders
          </h4>
          <div className="grid grid-cols-1 gap-2">
            <code className="block rounded-lg border-2 border-blue-400 bg-blue-50 px-3 py-2 text-xs font-mono font-semibold text-blue-900 shadow-sm transition hover:border-blue-600 hover:shadow-md">
              {"{appointment_table}"} - Complete appointment information table
            </code>
            <code className="block rounded-lg border border-blue-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-blue-500 hover:shadow-md">
              {"{personal_injury_info}"} - Shown only for PI cases
            </code>
          </div>
        </div>

        {/* Custom Placeholders Section - Show all custom placeholders */}
        {tagSettings.custom_placeholders && Object.keys(tagSettings.custom_placeholders).length > 0 && (
          <div>
            <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
              Custom Placeholders
            </h4>
            <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
              {Object.keys(tagSettings.custom_placeholders).map((key) => (
                <code
                  key={key}
                  className="block rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-amber-500 hover:shadow-md"
                >
                  {`{${key}}`}
                </code>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50/50 p-3 text-xs text-amber-800">
        <span className="font-semibold">💡 Tip:</span> If a patient field is missing, it will display as &ldquo;Not Available&rdquo; in the email.
      </div>
    </div>
  );
}
