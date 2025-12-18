"use client";

import React, { useState } from "react";
import { Placeholder, getPlaceholdersForType, TAG_TO_AUTORESPOND_TYPE } from "../constants/placeholders";

interface PlaceholderSectionProps {
  selectedTag: string;
  customPlaceholders?: Record<string, string>;
  onPlaceholderClick?: (placeholder: string) => void;
}

const PlaceholderSection: React.FC<PlaceholderSectionProps> = ({
  selectedTag,
  customPlaceholders,
  onPlaceholderClick,
}) => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const autorespondType = TAG_TO_AUTORESPOND_TYPE[selectedTag] || selectedTag;
  const { common, specific } = getPlaceholdersForType(autorespondType);
  const customPlaceholderEntries = Object.entries(customPlaceholders || {}).map(([key, description]) => ({
    key: `{${key}}`,
    description: description || "Custom placeholder defined in workspace settings",
  }));

  const handlePlaceholderClick = async (placeholderKey: string) => {
    // Copy to clipboard
    try {
      await navigator.clipboard.writeText(placeholderKey);
      setCopiedKey(placeholderKey);

      // Reset copied state after 2 seconds
      setTimeout(() => {
        setCopiedKey(null);
      }, 2000);
    } catch (err) {
      console.error("Failed to copy placeholder:", err);
    }

    // Call original callback if provided
    if (onPlaceholderClick) {
      onPlaceholderClick(placeholderKey);
    }
  };

  const PlaceholderCard: React.FC<{ placeholder: Placeholder }> = ({ placeholder }) => {
    const isCopied = copiedKey === placeholder.key;

    return (
      <button
        type="button"
        onClick={() => handlePlaceholderClick(placeholder.key)}
        className={`group relative w-full rounded-2xl border p-4 text-left shadow-sm transition-all duration-200 ${
          isCopied
            ? "border-green-400 bg-green-50 shadow-md"
            : "border-slate-200 bg-white/80 hover:-translate-y-0.5 hover:border-indigo-300 hover:shadow-lg"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <code
            className={`rounded-lg px-2 py-1 font-mono text-sm transition-colors ${
              isCopied ? "bg-green-100 text-green-700" : "bg-indigo-50 text-indigo-600"
            }`}
          >
            {placeholder.key}
          </code>

          {/* Copy icon with visual feedback */}
          <div className="flex items-center gap-1">
            {isCopied ? (
              <span className="flex items-center gap-1 text-xs font-medium text-green-600">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                Copied!
              </span>
            ) : (
              <span className="flex items-center gap-1 text-xs font-medium text-slate-400 opacity-0 transition-opacity group-hover:opacity-100">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                  />
                </svg>
                Click to copy
              </span>
            )}
          </div>
        </div>

        <p className="mt-2 text-sm text-slate-700">{placeholder.description}</p>
        {placeholder.example && (
          <p className="mt-1 text-xs text-slate-500">
            <span className="font-semibold">Example:</span> {placeholder.example}
          </p>
        )}
      </button>
    );
  };

  const PlaceholderGroup: React.FC<{
    icon: string;
    title: string;
    accent: string;
    placeholders: Placeholder[];
    subtitle?: string;
  }> = ({ icon, title, accent, placeholders, subtitle }) => (
    <section className={`rounded-3xl border ${accent} p-4`}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-lg">{icon}</span>
        <div>
          <h4 className="text-sm font-semibold uppercase tracking-wide text-slate-800">{title}</h4>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>
        <span className="ml-auto rounded-full bg-white/70 px-2 py-0.5 text-xs font-semibold text-slate-600">
          {placeholders.length} placeholder{placeholders.length !== 1 ? "s" : ""}
        </span>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {placeholders.map((placeholder) => (
          <PlaceholderCard key={placeholder.key} placeholder={placeholder} />
        ))}
      </div>
    </section>
  );

  return (
    <div className="space-y-4 rounded-3xl border border-slate-200 bg-white/80 p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Template Helpers</p>
          <h3 className="text-lg font-semibold text-slate-900">Available Placeholders</h3>
        </div>
      </div>

      <PlaceholderGroup
        icon="📌"
        title="Common (All Types)"
        accent="border-slate-200 bg-slate-50"
        placeholders={common}
        subtitle="Always available placeholders every autorespond can use"
      />

      {customPlaceholderEntries.length > 0 && (
        <PlaceholderGroup
          icon="🧩"
          title="Workspace Custom Placeholders"
          accent="border-amber-200 bg-amber-50"
          placeholders={customPlaceholderEntries}
          subtitle="Defined by your team and injected into every autorespond type"
        />
      )}

      {specific.length > 0 ? (
        <PlaceholderGroup
          icon="🎯"
          title="Specific to this type"
          accent="border-indigo-200 bg-indigo-50"
          placeholders={specific}
          subtitle="Contextual placeholders unique to this autorespond type"
        />
      ) : (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          This autorespond type doesn’t expose additional placeholders beyond the common set.
        </div>
      )}

      <div className="space-y-2 rounded-2xl border border-indigo-200 bg-indigo-50/80 p-4 text-sm text-indigo-900">
        <p>
          <strong>💡 Quick Copy:</strong> Click any placeholder card to instantly copy it to your clipboard. The card will
          turn green to confirm the copy.
        </p>
        <p className="text-xs text-indigo-700">
          <strong>Note:</strong> Placeholders that don't resolve (e.g., if DOB isn't on file) are automatically replaced
          with "Not Available."
        </p>
      </div>
    </div>
  );
};

export default PlaceholderSection;
