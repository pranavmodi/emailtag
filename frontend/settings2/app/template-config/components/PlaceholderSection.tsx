"use client";

import React from "react";
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
  const autorespondType = TAG_TO_AUTORESPOND_TYPE[selectedTag] || selectedTag;
  const { common, specific } = getPlaceholdersForType(autorespondType);
  const customPlaceholderEntries = Object.entries(customPlaceholders || {}).map(([key, description]) => ({
    key: `{${key}}`,
    description: description || "Custom placeholder defined in workspace settings",
  }));

  const handlePlaceholderClick = (placeholderKey: string) => {
    if (onPlaceholderClick) {
      onPlaceholderClick(placeholderKey);
    }
  };

  const PlaceholderCard: React.FC<{ placeholder: Placeholder }> = ({ placeholder }) => (
    <button
      type="button"
      onClick={() => handlePlaceholderClick(placeholder.key)}
      className="w-full rounded-2xl border border-slate-200 bg-white/80 p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-300 hover:shadow-lg"
    >
      <code className="rounded-lg bg-indigo-50 px-2 py-1 font-mono text-sm text-indigo-600">{placeholder.key}</code>
      <p className="mt-2 text-sm text-slate-700">{placeholder.description}</p>
      {placeholder.example && (
        <p className="mt-1 text-xs text-slate-500">
          <span className="font-semibold">Example:</span> {placeholder.example}
        </p>
      )}
    </button>
  );

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

      <div className="rounded-2xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-amber-900">
        <p>
          <strong>Tip:</strong> Placeholders that don’t resolve (for example, if DOB isn’t on file) are automatically
          replaced with “Not Available.” Use them freely without worrying about broken emails.
        </p>
      </div>
    </div>
  );
};

export default PlaceholderSection;
