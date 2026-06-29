/**
 * DocumentAttachments component - manages document attachments for templates
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, TemplatesApi } from "@/lib/api";
import type { TemplateAttachmentResponse } from "@/lib/types";

interface DocumentAttachmentsProps {
  tagName: string;
  templateKey?: string;
  currentUser: string;
}

const TAG_HINTS: Record<string, string> = {
  "Apt status req": "Upload documents for this specific scenario. They will be attached automatically when this template is used.",
  "Lien Templates": "Upload documents to include with lien-related autorespond emails.",
  "Bill or Balance Request": "Upload documents for this specific scenario. They will be attached automatically when this template is used.",
  "WORKSPACE": "Upload the HIPAA authorization form (PDF) used across all autoresponders when a sender cannot be verified.",
};

function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function getFileIcon(mimeType: string): string {
  if (mimeType === "application/pdf") return "📄";
  if (mimeType.startsWith("image/")) return "🖼️";
  if (mimeType.includes("word")) return "📝";
  return "📎";
}

export function DocumentAttachments({
  tagName,
  templateKey,
  currentUser,
}: DocumentAttachmentsProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [attachments, setAttachments] = useState<TemplateAttachmentResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadAttachments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await TemplatesApi.getTagAttachments(tagName, templateKey);
      setAttachments(response.items);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to load attachments");
      }
    } finally {
      setLoading(false);
    }
  }, [tagName, templateKey]);

  // Load attachments on mount to show correct count, and reload when expanded
  useEffect(() => {
    loadAttachments();
  }, [loadAttachments]);

  useEffect(() => {
    if (isExpanded) {
      loadAttachments();
    }
  }, [isExpanded, loadAttachments]);

  const handleFileUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    setError(null);
    setSuccess(null);

    const uploadedFiles: string[] = [];
    const failedFiles: string[] = [];

    for (const file of Array.from(files)) {
      try {
        await TemplatesApi.uploadTagAttachment(tagName, file, {
          templateKey,
          uploadedBy: currentUser,
        });
        uploadedFiles.push(file.name);
      } catch (err) {
        failedFiles.push(file.name);
        console.error(`Failed to upload ${file.name}:`, err);
      }
    }

    setUploading(false);

    if (uploadedFiles.length > 0) {
      setSuccess(`Uploaded: ${uploadedFiles.join(", ")}`);
      loadAttachments();
    }
    if (failedFiles.length > 0) {
      setError(`Failed to upload: ${failedFiles.join(", ")}`);
    }

    // Clear success message after 5 seconds
    if (uploadedFiles.length > 0) {
      setTimeout(() => setSuccess(null), 5000);
    }
  };

  const handleDelete = async (attachment: TemplateAttachmentResponse) => {
    if (!confirm(`Delete "${attachment.filename}"?\nThis action cannot be undone.`)) {
      return;
    }

    setError(null);
    try {
      await TemplatesApi.deleteTagAttachment(tagName, attachment.id);
      setSuccess(`Deleted: ${attachment.filename}`);
      loadAttachments();
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("Failed to delete attachment");
      }
    }
  };

  const handleView = (attachment: TemplateAttachmentResponse) => {
    const url = TemplatesApi.getAttachmentViewUrl(tagName, attachment.id);
    window.open(url, "_blank");
  };

  const handleDownload = (attachment: TemplateAttachmentResponse) => {
    const url = TemplatesApi.getAttachmentDownloadUrl(tagName, attachment.id);
    window.open(url, "_blank");
  };

  const isViewableInBrowser = (mimeType: string): boolean => {
    return (
      mimeType === "application/pdf" ||
      mimeType.startsWith("image/")
    );
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFileUpload(e.dataTransfer.files);
  };

  return (
    <div className="group overflow-hidden rounded-2xl border border-sky-200 bg-gradient-to-br from-sky-50 via-blue-50 to-sky-50 shadow-sm transition-all duration-200 hover:shadow-md">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-5 text-left transition-colors duration-200 hover:bg-sky-100/50"
      >
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-blue-500 text-white shadow-sm">
              <span className="text-sm">📎</span>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-900">
                Document Attachments
              </h3>
              <p className="text-xs text-slate-600">
                Documents to send with autorespond emails
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <span className="rounded-full bg-sky-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm">
              {attachments.length}
            </span>
            <svg
              className={`h-5 w-5 text-sky-700 transition-transform duration-300 ${isExpanded ? "rotate-180" : ""}`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </div>
        </div>
      </button>

      <div
        className={`transition-all duration-300 ease-in-out ${isExpanded ? "max-h-[1000px] opacity-100" : "max-h-0 opacity-0"}`}
      >
        <div className="border-t border-sky-200 bg-white/50 p-5">
          {/* Status Messages */}
          {error && (
            <div className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3">
              <div className="flex items-center gap-2 text-sm text-red-800">
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                {error}
              </div>
            </div>
          )}

          {success && (
            <div className="mb-4 rounded-lg border border-green-200 bg-green-50 p-3">
              <div className="flex items-center gap-2 text-sm text-green-800">
                <svg
                  className="h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                {success}
              </div>
            </div>
          )}

          {/* Upload Area */}
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`mb-4 cursor-pointer rounded-xl border-2 border-dashed p-6 text-center transition-all ${
              dragOver
                ? "border-sky-500 bg-sky-100"
                : "border-sky-300 bg-sky-50/50 hover:border-sky-400 hover:bg-sky-100/50"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.png,.jpg,.jpeg,.gif,.doc,.docx"
              onChange={(e) => handleFileUpload(e.target.files)}
              className="hidden"
            />
            {uploading ? (
              <div className="flex flex-col items-center">
                <svg
                  className="mb-2 h-8 w-8 animate-spin text-sky-600"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                <p className="text-sm font-medium text-sky-700">Uploading...</p>
              </div>
            ) : (
              <>
                <svg
                  className="mx-auto mb-2 h-10 w-10 text-sky-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={1.5}
                    d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                  />
                </svg>
                <p className="text-sm font-medium text-slate-700">
                  Drop files here or click to upload
                </p>
                <p className="mt-1 text-xs text-slate-500">
                  PDF, Images, Word documents (max 10MB)
                </p>
              </>
            )}
          </div>

          {/* Attachments List */}
          {loading ? (
            <div className="py-8 text-center text-sm text-slate-500">
              Loading attachments...
            </div>
          ) : attachments.length === 0 ? (
            <div className="rounded-xl border-2 border-dashed border-sky-300 bg-sky-50/30 p-8 text-center">
              <svg
                className="mx-auto mb-3 h-12 w-12 text-sky-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
              <p className="text-sm font-medium text-slate-700">
                No attachments yet
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Upload documents to include with autorespond emails
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              {attachments.map((attachment) => (
                <div
                  key={attachment.id}
                  className="flex items-center justify-between rounded-xl border border-sky-200 bg-white p-3 shadow-sm transition-all hover:shadow"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">
                      {getFileIcon(attachment.mime_type)}
                    </span>
                    <div>
                      <p className="text-sm font-medium text-slate-800">
                        {attachment.filename}
                      </p>
                      <p className="text-xs text-slate-500">
                        {formatFileSize(attachment.file_size)} •{" "}
                        {new Date(attachment.created_at).toLocaleDateString()}
                        {attachment.uploaded_by && (
                          <> • by {attachment.uploaded_by}</>
                        )}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isViewableInBrowser(attachment.mime_type) && (
                      <button
                        onClick={() => handleView(attachment)}
                        className="rounded-lg bg-emerald-100 p-2 text-emerald-700 transition-colors hover:bg-emerald-200"
                        title="View in new tab"
                      >
                        <svg
                          className="h-4 w-4"
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"
                          />
                        </svg>
                      </button>
                    )}
                    <button
                      onClick={() => handleDownload(attachment)}
                      className="rounded-lg bg-sky-100 p-2 text-sky-700 transition-colors hover:bg-sky-200"
                      title="Download"
                    >
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                        />
                      </svg>
                    </button>
                    <button
                      onClick={() => handleDelete(attachment)}
                      className="rounded-lg bg-red-100 p-2 text-red-700 transition-colors hover:bg-red-200"
                      title="Delete"
                    >
                      <svg
                        className="h-4 w-4"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                        />
                      </svg>
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Info Note */}
          <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-3">
            <div className="flex items-start gap-2">
              <svg
                className="mt-0.5 h-5 w-5 flex-shrink-0 text-blue-600"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              <p className="text-xs text-blue-800">
                <strong className="font-semibold">Note:</strong>{" "}
                {TAG_HINTS[tagName] ||
                  "Uploaded documents will be sent as attachments with autorespond emails for this template category."}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
