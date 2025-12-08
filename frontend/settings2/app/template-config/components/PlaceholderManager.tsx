/**
 * PlaceholderManager component - manages custom placeholders
 */

import { useEffect, useState } from "react";
import { DEFAULT_TAG_SETTINGS } from "../constants/template-config.constants";

interface PlaceholderManagerProps {
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string | Record<string, string>) => void;
  onSave: () => void;
  onReset: () => void;
}

export function PlaceholderManager({ tagSettings, onFieldChange, onSave, onReset }: PlaceholderManagerProps) {
  const [isPlaceholdersExpanded, setIsPlaceholdersExpanded] = useState(false);
  const [selectedPlaceholder, setSelectedPlaceholder] = useState<string>("");

  // Initialize selected placeholder when custom_placeholders change
  useEffect(() => {
    if (tagSettings.custom_placeholders && Object.keys(tagSettings.custom_placeholders).length > 0) {
      const firstKey = Object.keys(tagSettings.custom_placeholders)[0];
      if (!selectedPlaceholder || !(selectedPlaceholder in tagSettings.custom_placeholders)) {
        setSelectedPlaceholder(firstKey);
      }
    }
  }, [tagSettings.custom_placeholders, selectedPlaceholder]);

  const handleAddPlaceholder = () => {
    const name = prompt("Enter placeholder name (without braces):");
    if (name && /^[a-z_][a-z0-9_]*$/i.test(name)) {
      const customPlaceholders = tagSettings.custom_placeholders || {};
      onFieldChange("custom_placeholders", {
        ...customPlaceholders,
        [name]: ""
      });
      setSelectedPlaceholder(name);
    } else if (name) {
      alert("Invalid placeholder name. Use only letters, numbers, and underscores, starting with a letter.");
    }
  };

  const handleDeletePlaceholder = () => {
    const customPlaceholders = { ...tagSettings.custom_placeholders };
    delete customPlaceholders[selectedPlaceholder];
    onFieldChange("custom_placeholders", customPlaceholders);
    const remaining = Object.keys(customPlaceholders);
    setSelectedPlaceholder(remaining.length > 0 ? remaining[0] : "");
  };

  const handleUpdatePlaceholder = (value: string) => {
    const customPlaceholders = { ...tagSettings.custom_placeholders };
    customPlaceholders[selectedPlaceholder] = value;
    onFieldChange("custom_placeholders", customPlaceholders);
  };

  return (
    <div className="group overflow-hidden rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 via-orange-50 to-amber-50 shadow-sm transition-all duration-200 hover:shadow-md">
      <button
        onClick={() => setIsPlaceholdersExpanded(!isPlaceholdersExpanded)}
        className="w-full p-5 text-left transition-colors duration-200 hover:bg-amber-100/50"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-sm">
              <span className="text-sm font-bold">{ }</span>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Custom Placeholders
              </h3>
              <p className="text-xs text-slate-600">
                {Object.keys(tagSettings.custom_placeholders || {}).length} placeholder{Object.keys(tagSettings.custom_placeholders || {}).length !== 1 ? 's' : ''} defined
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-amber-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm">
              {Object.keys(tagSettings.custom_placeholders || {}).length}
            </span>
            <svg
              className={`h-5 w-5 text-amber-700 transition-transform duration-300 ${isPlaceholdersExpanded ? 'rotate-180' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </button>

      <div className={`transition-all duration-300 ease-in-out ${isPlaceholdersExpanded ? 'max-h-[800px] opacity-100' : 'max-h-0 opacity-0'}`}>
        <div className="border-t border-amber-200 bg-white/50 p-5">
          <p className="mb-4 text-xs text-slate-600">
            Define custom placeholders available across all autorespond templates. Values are replaced when emails are sent.
          </p>

          {/* Placeholder Selector and Editor */}
          {tagSettings.custom_placeholders && Object.keys(tagSettings.custom_placeholders).length > 0 ? (
            <div className="space-y-4">
              {/* Dropdown Selector */}
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                  </svg>
                  Select Placeholder
                </label>
                <select
                  value={selectedPlaceholder}
                  onChange={(e) => setSelectedPlaceholder(e.target.value)}
                  className="w-full rounded-xl border-2 border-amber-200 bg-white px-4 py-3 font-mono text-sm font-medium text-slate-800 shadow-sm transition-all focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
                >
                  {Object.keys(tagSettings.custom_placeholders).map((key) => (
                    <option key={key} value={key}>
                      {`{${key}}`}
                    </option>
                  ))}
                </select>
              </div>

              {/* Value Editor */}
              {selectedPlaceholder && (
                <div className="space-y-3 rounded-xl border-2 border-amber-200 bg-gradient-to-br from-white to-amber-50/30 p-4 shadow-sm">
                  <div className="flex items-center justify-between">
                    <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      Value for <code className="ml-1 rounded bg-amber-200 px-1.5 py-0.5 font-mono text-xs text-amber-900">{`{${selectedPlaceholder}}`}</code>
                    </label>
                    <button
                      onClick={handleDeletePlaceholder}
                      className="flex items-center gap-1 rounded-lg bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 shadow-sm transition-all hover:bg-red-200 hover:shadow active:scale-95"
                    >
                      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Delete
                    </button>
                  </div>
                  <textarea
                    value={tagSettings.custom_placeholders[selectedPlaceholder] || ""}
                    onChange={(e) => handleUpdatePlaceholder(e.target.value)}
                    placeholder={`Enter value for {${selectedPlaceholder}}`}
                    rows={7}
                    className="w-full rounded-lg border-2 border-amber-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
                  />
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-xl border-2 border-dashed border-amber-300 bg-amber-50/50 p-8 text-center">
              <svg className="mx-auto mb-3 h-12 w-12 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
              </svg>
              <p className="text-sm font-medium text-slate-700">No placeholders yet</p>
              <p className="mt-1 text-xs text-slate-500">Create your first custom placeholder below</p>
            </div>
          )}

          {/* Add New Placeholder Button */}
          <button
            onClick={handleAddPlaceholder}
            className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-amber-400 bg-gradient-to-br from-amber-50 to-orange-50 px-4 py-3 text-sm font-semibold text-amber-700 shadow-sm transition-all hover:border-amber-500 hover:from-amber-100 hover:to-orange-100 hover:shadow active:scale-[0.98]"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
            </svg>
            Add New Placeholder
          </button>

          {/* Save Buttons */}
          <div className="mt-6 flex justify-end gap-3 border-t-2 border-amber-200 pt-4">
            <button
              onClick={onReset}
              className="flex items-center gap-2 rounded-xl border-2 border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-400 hover:bg-slate-50 hover:shadow active:scale-95"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              Reset
            </button>
            <button
              onClick={onSave}
              className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:from-amber-700 hover:to-orange-700 hover:shadow-lg active:scale-95"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
              Save Placeholders
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
