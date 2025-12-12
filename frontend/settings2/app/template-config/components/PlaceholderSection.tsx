"use client";

import React from 'react';
import { Placeholder, getPlaceholdersForType, TAG_TO_AUTORESPOND_TYPE } from '../constants/placeholders';

interface PlaceholderSectionProps {
  selectedTag: string; // Tag name from dropdown (e.g., "Apt status req")
  onPlaceholderClick?: (placeholder: string) => void;
}

const PlaceholderSection: React.FC<PlaceholderSectionProps> = ({
  selectedTag,
  onPlaceholderClick
}) => {
  // Convert tag name to autorespond type
  const autorespondType = TAG_TO_AUTORESPOND_TYPE[selectedTag] || selectedTag;
  const { common, specific } = getPlaceholdersForType(autorespondType);

  const handlePlaceholderClick = (placeholderKey: string) => {
    if (onPlaceholderClick) {
      onPlaceholderClick(placeholderKey);
    }
  };

  const PlaceholderItem: React.FC<{ placeholder: Placeholder }> = ({ placeholder }) => (
    <div
      className="placeholder-item group cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800 p-2 rounded border border-transparent hover:border-blue-300 dark:hover:border-blue-600 transition-all"
      onClick={() => handlePlaceholderClick(placeholder.key)}
      title="Click to insert"
    >
      <div className="flex items-start gap-2">
        <code className="text-sm font-mono bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 px-2 py-0.5 rounded flex-shrink-0">
          {placeholder.key}
        </code>
        <div className="flex-1 min-w-0">
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {placeholder.description}
          </p>
          {placeholder.example && (
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 italic">
              e.g., {placeholder.example}
            </p>
          )}
        </div>
        <svg
          className="w-4 h-4 text-gray-400 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 4v16m8-8H4"
          />
        </svg>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
          Available Placeholders
        </h3>
        <span className="text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded">
          Click to insert
        </span>
      </div>

      {/* Common Placeholders Section */}
      <div className="placeholder-section">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg">📌</span>
          <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 uppercase tracking-wide">
            Common (All Types)
          </h4>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            {common.length} placeholder{common.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="space-y-1 pl-7">
          {common.map((placeholder) => (
            <PlaceholderItem key={placeholder.key} placeholder={placeholder} />
          ))}
        </div>
      </div>

      {/* Specific Placeholders Section */}
      {specific.length > 0 && (
        <div className="placeholder-section">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-lg">🎯</span>
            <h4 className="text-sm font-semibold text-indigo-700 dark:text-indigo-300 uppercase tracking-wide">
              Specific to This Type
            </h4>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {specific.length} placeholder{specific.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div className="space-y-1 pl-7">
            {specific.map((placeholder) => (
              <PlaceholderItem key={placeholder.key} placeholder={placeholder} />
            ))}
          </div>
        </div>
      )}

      {/* No specific placeholders message */}
      {specific.length === 0 && (
        <div className="text-sm text-gray-500 dark:text-gray-400 italic pl-7">
          No type-specific placeholders for this autorespond type.
        </div>
      )}

      {/* Help text */}
      <div className="mt-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded text-sm">
        <p className="text-blue-800 dark:text-blue-200">
          <strong>Tip:</strong> Click any placeholder above to insert it into your template.
          Placeholders will be automatically replaced with actual values when sending the autoresponse.
        </p>
      </div>
    </div>
  );
};

export default PlaceholderSection;
