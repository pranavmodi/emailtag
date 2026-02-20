"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Clock,
  FileSearch,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  Shield,
  Tag,
  Archive,
  Zap,
  AlertTriangle,
  CheckCircle,
  XCircle,
  Sparkles,
  ScrollText,
  Filter,
} from "lucide-react";

import { ApiError, ClassificationTracesApi, SettingsApi, type FullTracesResponse, type ConversationLogsResponse, type LogEntry } from "@/lib/api";
import type { RecentConversation, ClassificationTrace } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Header } from "@/components/layout/Header";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

function formatTimeAgo(isoString: string | null): string {
  if (!isoString) return "Unknown time";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHour = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHour / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  if (diffHour < 24) return `${diffHour} hour${diffHour > 1 ? "s" : ""} ago`;
  if (diffDay < 7) return `${diffDay} day${diffDay > 1 ? "s" : ""} ago`;

  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function getTraceTypeIcon(traceType: string) {
  switch (traceType) {
    case "document_processing":
      return <FileText className="h-4 w-4" />;
    case "lien_validation":
      return <Shield className="h-4 w-4" />;
    case "archival":
      return <Archive className="h-4 w-4" />;
    case "classification":
      return <Tag className="h-4 w-4" />;
    default:
      return <Zap className="h-4 w-4" />;
  }
}

function getTraceTypeColor(traceType: string) {
  switch (traceType) {
    case "document_processing":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "lien_validation":
      return "bg-pink-50 text-pink-700 border-pink-200";
    case "archival":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "classification":
      return "bg-violet-50 text-violet-700 border-violet-200";
    default:
      return "bg-slate-50 text-slate-700 border-slate-200";
  }
}

function getTraceTypeBorderColor(traceType: string) {
  switch (traceType) {
    case "document_processing":
      return "border-l-emerald-500";
    case "lien_validation":
      return "border-l-pink-500";
    case "archival":
      return "border-l-amber-500";
    case "classification":
      return "border-l-violet-500";
    default:
      return "border-l-slate-500";
  }
}

// Trace Card Component
function TraceCard({ trace, index, isExpanded, onToggle }: {
  trace: ClassificationTrace;
  index: number;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  return (
    <div className={`bg-white rounded-xl border border-slate-200 overflow-hidden border-l-4 ${getTraceTypeBorderColor(trace.trace_type)} transition-shadow hover:shadow-md`}>
      {/* Header */}
      <div
        className="flex items-center justify-between p-4 cursor-pointer hover:bg-slate-50 transition-colors"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          <span className="flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-purple-600 text-white text-sm font-bold">
            {index + 1}
          </span>
          <div>
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${getTraceTypeColor(trace.trace_type)}`}>
                {getTraceTypeIcon(trace.trace_type)}
                {trace.trace_type.replace("_", " ")}
              </span>
              <span className="font-semibold text-slate-800">{trace.step_name}</span>
              {trace.chosen_option && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-indigo-100 text-indigo-700">
                  {trace.chosen_option}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1 text-xs text-slate-500">
              {trace.classification_path && <span>{trace.classification_path}</span>}
              {trace.email_format && (
                <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">{trace.email_format}</span>
              )}
              {trace.llm_model && trace.llm_model !== "archival_check" && (
                <span className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-600">{trace.llm_model}</span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-500">
          {trace.duration_ms !== null && (
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {trace.duration_ms}ms
            </span>
          )}
          {trace.total_tokens !== null && (
            <span className="flex items-center gap-1">
              <Zap className="h-3.5 w-3.5" />
              {trace.total_tokens} tokens
            </span>
          )}
          {isExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
        </div>
      </div>

      {/* Expanded Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-slate-100"
          >
            {/* Document Processing Details */}
            {trace.trace_type === "document_processing" && trace.document_analysis && (
              <CollapsibleSection
                title="Document Details"
                icon={<FileText className="h-4 w-4" />}
                defaultExpanded={true}
                isExpanded={expandedSections["doc-details"] !== false}
                onToggle={() => toggleSection("doc-details")}
              >
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                  <InfoCard label="Filename" value={trace.document_analysis.filename} />
                  <InfoCard label="Document Type" value={trace.document_analysis.document_type} highlight />
                  <InfoCard label="Patient ID" value={trace.document_analysis.patient_id || "Not Found"} />
                  <InfoCard label="Confidence" value={trace.document_analysis.confidence} />
                  <InfoCard label="File Size" value={trace.document_analysis.file_size} />
                  <InfoCard label="Status" value={trace.document_analysis.processing_status} />
                </div>
                {trace.document_analysis.description && (
                  <div className="mt-3 p-3 bg-white rounded-lg border-l-4 border-emerald-500">
                    <p className="text-sm text-slate-700">{trace.document_analysis.description}</p>
                  </div>
                )}
              </CollapsibleSection>
            )}

            {/* Lien Validation Details */}
            {trace.trace_type === "lien_validation" && trace.lien_validation && (
              <LienValidationDetails trace={trace} expandedSections={expandedSections} toggleSection={toggleSection} />
            )}

            {/* Archival Details */}
            {trace.trace_type === "archival" && (
              <>
                {trace.input_data && (
                  <CollapsibleSection
                    title="Input Data"
                    icon={<FileText className="h-4 w-4" />}
                    isExpanded={expandedSections["input"] === true}
                    onToggle={() => toggleSection("input")}
                  >
                    <CodeBlock data={trace.input_data} />
                  </CollapsibleSection>
                )}
                {trace.output_data && (
                  <CollapsibleSection
                    title="Output Data / Decision"
                    icon={<CheckCircle className="h-4 w-4" />}
                    defaultExpanded={true}
                    isExpanded={expandedSections["output"] !== false}
                    onToggle={() => toggleSection("output")}
                  >
                    <CodeBlock data={trace.output_data} />
                  </CollapsibleSection>
                )}
                {trace.error_data && (
                  <CollapsibleSection
                    title="Error Data"
                    icon={<XCircle className="h-4 w-4" />}
                    isExpanded={expandedSections["error"] === true}
                    onToggle={() => toggleSection("error")}
                  >
                    <CodeBlock data={trace.error_data} isError />
                  </CollapsibleSection>
                )}
              </>
            )}

            {/* Classification Details */}
            {trace.trace_type === "classification" && (
              <>
                {trace.prompt_template && (
                  <CollapsibleSection
                    title="Prompt Template (Classification Rules)"
                    icon={<FileText className="h-4 w-4" />}
                    isExpanded={expandedSections["prompt"] === true}
                    onToggle={() => toggleSection("prompt")}
                  >
                    <CodeBlock text={trace.prompt_template} />
                  </CollapsibleSection>
                )}
                {trace.full_prompt && (
                  <CollapsibleSection
                    title="Full Prompt Sent to LLM"
                    icon={<Zap className="h-4 w-4" />}
                    isExpanded={expandedSections["full-prompt"] === true}
                    onToggle={() => toggleSection("full-prompt")}
                  >
                    <CodeBlock text={trace.full_prompt} />
                  </CollapsibleSection>
                )}
                {trace.llm_response && (
                  <CollapsibleSection
                    title="LLM Response"
                    icon={<CheckCircle className="h-4 w-4" />}
                    isExpanded={expandedSections["response"] === true}
                    onToggle={() => toggleSection("response")}
                  >
                    <CodeBlock text={trace.llm_response} />
                  </CollapsibleSection>
                )}
              </>
            )}

            {/* Common sections */}
            {trace.conversation_summary && (
              <CollapsibleSection
                title="Conversation Summary"
                icon={<FileText className="h-4 w-4" />}
                isExpanded={expandedSections["summary"] === true}
                onToggle={() => toggleSection("summary")}
              >
                <div className="p-3 bg-white rounded-lg border-l-4 border-indigo-500">
                  <p className="text-sm text-slate-700">{trace.conversation_summary}</p>
                </div>
              </CollapsibleSection>
            )}

            {trace.classification_reason && (
              <CollapsibleSection
                title="Classification Reason"
                icon={<Tag className="h-4 w-4" />}
                defaultExpanded={true}
                isExpanded={expandedSections["reason"] !== false}
                onToggle={() => toggleSection("reason")}
              >
                <div className="p-3 bg-white rounded-lg border-l-4 border-emerald-500">
                  <p className="text-sm text-slate-700">{trace.classification_reason}</p>
                </div>
              </CollapsibleSection>
            )}

            {/* Token Usage */}
            {(trace.prompt_tokens || trace.completion_tokens || trace.total_tokens) && (
              <CollapsibleSection
                title="Token Usage & Performance"
                icon={<Zap className="h-4 w-4" />}
                isExpanded={expandedSections["tokens"] === true}
                onToggle={() => toggleSection("tokens")}
              >
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <InfoCard label="Prompt Tokens" value={trace.prompt_tokens} large />
                  <InfoCard label="Completion Tokens" value={trace.completion_tokens} large />
                  <InfoCard label="Total Tokens" value={trace.total_tokens} large highlight />
                  <InfoCard label="Duration" value={trace.duration_ms ? `${trace.duration_ms}ms` : "N/A"} large />
                </div>
              </CollapsibleSection>
            )}

            {/* Raw Output for document processing and lien validation */}
            {(trace.trace_type === "document_processing" || trace.trace_type === "lien_validation") && trace.output_data && (
              <CollapsibleSection
                title="Raw Output Data"
                icon={<FileText className="h-4 w-4" />}
                isExpanded={expandedSections["raw-output"] === true}
                onToggle={() => toggleSection("raw-output")}
              >
                <CodeBlock data={trace.output_data} />
              </CollapsibleSection>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Lien Validation Details Component
function LienValidationDetails({ trace, expandedSections, toggleSection }: {
  trace: ClassificationTrace;
  expandedSections: Record<string, boolean>;
  toggleSection: (section: string) => void;
}) {
  const lv = trace.lien_validation;
  if (!lv) return null;

  return (
    <CollapsibleSection
      title="Validation Details"
      icon={<Shield className="h-4 w-4" />}
      defaultExpanded={true}
      isExpanded={expandedSections["lien-details"] !== false}
      onToggle={() => toggleSection("lien-details")}
    >
      {lv.check_type === "signature" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <InfoCard label="Signature Type" value={lv.lien_signature_type} highlight large />
            <InfoCard
              label="Patient Signature"
              value={lv.patient_signature_present ? "Present" : "Not Found"}
              status={lv.patient_signature_present ? "success" : "error"}
            />
            <InfoCard
              label="Attorney Signature"
              value={lv.attorney_signature_present ? "Present" : "Not Found"}
              status={lv.attorney_signature_present ? "success" : "error"}
            />
            <InfoCard
              label="Placement Valid"
              value={lv.placement_valid ? "Valid" : "Issues"}
              status={lv.placement_valid ? "success" : "warning"}
            />
          </div>
          {lv.placement_issues && lv.placement_issues.length > 0 && (
            <div className="p-3 bg-rose-50 rounded-lg border-l-4 border-rose-500">
              <p className="font-medium text-rose-700 mb-1">Placement Issues:</p>
              <ul className="list-disc list-inside text-sm text-rose-600">
                {lv.placement_issues.map((issue: string, i: number) => (
                  <li key={i}>{issue}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {lv.check_type === "barcode" && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <InfoCard
            label="Barcode Status"
            value={lv.barcode_found ? "Found" : "Not Found"}
            status={lv.barcode_found ? "success" : "error"}
          />
          <InfoCard label="Patient IDs" value={lv.patient_ids?.join(", ") || "None"} />
          <InfoCard label="Lien Types" value={lv.lien_types?.join(", ") || "None"} />
          <InfoCard label="Referrer ID" value={lv.referrer_id || "N/A"} />
        </div>
      )}

      {lv.check_type === "cover_letter" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <InfoCard label="Page Classification" value={lv.page_classification} highlight />
            <InfoCard
              label="Is Cover Letter"
              value={lv.is_cover_letter ? "Yes" : "No"}
              status={lv.is_cover_letter ? "warning" : "success"}
            />
            <InfoCard
              label="Conditional Language"
              value={lv.has_conditional_language ? "Found" : "None"}
              status={lv.has_conditional_language ? "error" : "success"}
            />
            <InfoCard label="Confidence" value={lv.cover_letter_confidence || "N/A"} />
          </div>
          {lv.conditional_phrases_found && lv.conditional_phrases_found.length > 0 && (
            <div className="p-3 bg-rose-50 rounded-lg border-l-4 border-rose-500">
              <p className="font-medium text-rose-700 mb-1">Conditional Phrases Found:</p>
              <ul className="list-disc list-inside text-sm text-rose-600">
                {lv.conditional_phrases_found.map((phrase: string, i: number) => (
                  <li key={i}>&quot;{phrase}&quot;</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {lv.check_type === "image_quality" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <InfoCard
              label="Document Quality"
              value={lv.document_quality}
              status={lv.document_quality === "GOOD" ? "success" : lv.document_quality === "BLURRY" ? "warning" : "error"}
              large
              highlight
            />
            <InfoCard label="Overall Quality" value={lv.overall_quality || lv.document_quality} />
          </div>
          {lv.quality_by_page && lv.quality_by_page.length > 0 && (
            <div>
              <p className="font-medium text-slate-600 mb-2 text-sm">Quality by Page:</p>
              <div className="flex flex-wrap gap-2">
                {lv.quality_by_page.map((page: { page: number; quality: string }, i: number) => (
                  <span
                    key={i}
                    className={`px-2 py-1 rounded text-xs font-medium ${
                      page.quality === "GOOD" ? "bg-emerald-100 text-emerald-700" :
                      page.quality === "BLURRY" ? "bg-amber-100 text-amber-700" :
                      "bg-rose-100 text-rose-700"
                    }`}
                  >
                    Page {page.page}: {page.quality}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {lv.check_type === "strikethrough" && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            <InfoCard
              label="Modifications Detected"
              value={lv.strikethrough_detected ? "Yes" : "No"}
              status={lv.strikethrough_detected ? "error" : "success"}
            />
            <InfoCard label="Total Instances" value={lv.total_instances} large />
            <InfoCard label="Pages Affected" value={`${lv.pages_with_strikethrough} / ${lv.total_pages || "?"}`} />
          </div>
          {lv.strikethrough_instances && lv.strikethrough_instances.length > 0 && (
            <div className="p-3 bg-rose-50 rounded-lg border-l-4 border-rose-500">
              <p className="font-medium text-rose-700 mb-2">Strikethrough Instances:</p>
              <div className="space-y-2">
                {lv.strikethrough_instances.map((instance: { page_number?: number; struck_through_text: string; visual_description?: string; confidence?: string }, i: number) => (
                  <div key={i} className="p-2 bg-white rounded border border-rose-200">
                    <p className="font-medium text-slate-700">Page {instance.page_number || "N/A"}: &quot;{instance.struck_through_text}&quot;</p>
                    {instance.visual_description && (
                      <p className="text-xs text-slate-500 mt-1">{instance.visual_description}</p>
                    )}
                    {instance.confidence && (
                      <p className="text-xs text-slate-400 mt-1">Confidence: {instance.confidence}</p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </CollapsibleSection>
  );
}

// Collapsible Section Component
function CollapsibleSection({
  title,
  icon,
  children,
  defaultExpanded = false,
  isExpanded,
  onToggle
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
  defaultExpanded?: boolean;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border-t border-slate-100">
      <div
        className="flex items-center justify-between px-4 py-3 bg-slate-50 cursor-pointer hover:bg-slate-100 transition-colors"
        onClick={onToggle}
      >
        <span className="flex items-center gap-2 text-sm font-medium text-slate-600">
          {icon}
          {title}
        </span>
        {isExpanded ? <ChevronDown className="h-4 w-4 text-slate-400" /> : <ChevronRight className="h-4 w-4 text-slate-400" />}
      </div>
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="p-4 bg-slate-50/50">
              {children}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// Info Card Component
function InfoCard({
  label,
  value,
  highlight = false,
  large = false,
  status
}: {
  label: string;
  value: string | number | null | undefined;
  highlight?: boolean;
  large?: boolean;
  status?: "success" | "warning" | "error";
}) {
  const statusColors = {
    success: "text-emerald-600",
    warning: "text-amber-600",
    error: "text-rose-600",
  };

  return (
    <div className="bg-white p-3 rounded-lg border border-slate-200">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`font-semibold truncate ${large ? "text-lg" : "text-sm"} ${
        status ? statusColors[status] : highlight ? "text-indigo-600" : "text-slate-800"
      }`}>
        {value ?? "N/A"}
      </p>
    </div>
  );
}

// Code Block Component
function CodeBlock({ data, text, isError = false }: { data?: Record<string, unknown>; text?: string; isError?: boolean }) {
  const content = text || (data ? JSON.stringify(data, null, 2) : "No data");
  return (
    <div className={`rounded-lg overflow-auto max-h-96 ${isError ? "bg-rose-900" : "bg-slate-800"}`}>
      <pre className="p-4 text-xs text-slate-200 whitespace-pre-wrap break-words font-mono">
        {content}
      </pre>
    </div>
  );
}

// Main Page Component Content
function ClassificationTracesContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const conversationIdParam = searchParams.get("conversation_id");

  const [user, setUser] = useState<string>("Admin");
  const [conversations, setConversations] = useState<RecentConversation[]>([]);
  const [traceData, setTraceData] = useState<FullTracesResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [searchInput, setSearchInput] = useState(conversationIdParam || "");
  const [searchFilter, setSearchFilter] = useState<string>("");
  const [searchLoading, setSearchLoading] = useState(false);
  const [expandedTraces, setExpandedTraces] = useState<Record<number, boolean>>({});
  const [summaryText, setSummaryText] = useState<string | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  // Logs state
  const [logsData, setLogsData] = useState<ConversationLogsResponse | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [logsError, setLogsError] = useState<string | null>(null);
  const [logsExpanded, setLogsExpanded] = useState(false);
  const [logsLevelFilter, setLogsLevelFilter] = useState<string>("ALL");
  const [logsSearchInput, setLogsSearchInput] = useState<string>("");

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      try {
        const auth = await SettingsApi.getAuthStatus();
        if (!auth.authenticated) {
          window.location.href = "/login";
          return;
        }
        if (!mounted) return;
        setUser(auth.username ?? "Admin");

        if (conversationIdParam) {
          // Load trace data for specific conversation
          await loadTraceData(conversationIdParam);
        } else {
          // Load list of recent conversations
          await loadRecentConversations();
        }
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
          return;
        }
        console.error("Failed to bootstrap auth", err);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    const loadRecentConversations = async () => {
      try {
        const response = await ClassificationTracesApi.getRecentConversations(50);
        if (mounted) {
          setConversations(response.conversations);
        }
      } catch (err) {
        if (mounted) {
          if (err instanceof ApiError) {
            setError(err.message);
          } else {
            setError("An unexpected error occurred");
          }
        }
      }
    };

    const loadTraceData = async (convId: string) => {
      try {
        const response = await ClassificationTracesApi.getFullTraces(convId);
        if (mounted) {
          setTraceData(response);
          // Auto-expand first trace
          if (response.traces.length > 0) {
            setExpandedTraces({ 0: true });
          }
        }
      } catch (err) {
        if (mounted) {
          if (err instanceof ApiError) {
            setError(err.message);
          } else {
            setError("An unexpected error occurred");
          }
        }
      }
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, [conversationIdParam]);

  const handleRefresh = async () => {
    setLoading(true);
    setError(null);
    try {
      if (conversationIdParam) {
        const response = await ClassificationTracesApi.getFullTraces(conversationIdParam);
        setTraceData(response);
      } else {
        const response = await ClassificationTracesApi.getRecentConversations(50);
        setConversations(response.conversations);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    const query = searchInput.trim();
    if (!query) return;
    setSearchFilter(query);

    // Check if any locally-loaded conversations match
    const localMatches = conversations.filter((conv) =>
      conv.conversation_id.toLowerCase().includes(query.toLowerCase())
    );

    // If no local matches, try to look up the conversation via API
    if (localMatches.length === 0) {
      setSearchLoading(true);
      try {
        const response = await ClassificationTracesApi.getFullTraces(query);
        if (response && response.total_traces > 0) {
          // Add this conversation to the list so it appears in search results
          const found: RecentConversation = {
            conversation_id: query,
            last_trace_at: new Date().toISOString(),
            classification_traces: response.classification_count,
            archival_traces: response.archival_count,
            total_tokens: response.total_tokens ?? 0,
          };
          setConversations((prev) => {
            // Avoid duplicates
            if (prev.some((c) => c.conversation_id === query)) return prev;
            return [found, ...prev];
          });
        }
      } catch {
        // Conversation not found in API either — leave empty results
      } finally {
        setSearchLoading(false);
      }
    }
  };

  const handleViewTrace = (conversationId: string) => {
    window.open(`/settings/classification-traces?conversation_id=${encodeURIComponent(conversationId)}`, '_blank');
  };

  const handleViewLogsNewTab = (conversationId: string, e: React.MouseEvent) => {
    e.stopPropagation(); // Prevent triggering the row click
    window.open(`/settings/classification-traces/logs?conversation_id=${encodeURIComponent(conversationId)}`, '_blank');
  };

  const handleBackToList = () => {
    router.push("/classification-traces");
  };

  const toggleTrace = (index: number) => {
    setExpandedTraces(prev => ({ ...prev, [index]: !prev[index] }));
  };

  const handleSummarize = async () => {
    if (!conversationIdParam) return;
    setSummaryLoading(true);
    setSummaryError(null);
    setSummaryText(null);
    try {
      const result = await ClassificationTracesApi.summarize(conversationIdParam);
      setSummaryText(result.summary);
    } catch (err) {
      if (err instanceof ApiError) {
        setSummaryError(err.message);
      } else {
        setSummaryError("Failed to generate summary");
      }
    } finally {
      setSummaryLoading(false);
    }
  };

  const handleViewLogs = async () => {
    if (!conversationIdParam) return;

    // Toggle panel if already loaded
    if (logsData && !logsLoading) {
      setLogsExpanded(!logsExpanded);
      return;
    }

    setLogsLoading(true);
    setLogsError(null);
    setLogsExpanded(true);
    try {
      const levelParam = logsLevelFilter === "ALL" ? undefined : logsLevelFilter;
      const searchParam = logsSearchInput.trim() || undefined;
      const result = await ClassificationTracesApi.getLogs(conversationIdParam, levelParam, searchParam, 500);
      setLogsData(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setLogsError(err.message);
      } else {
        setLogsError("Failed to load logs");
      }
    } finally {
      setLogsLoading(false);
    }
  };

  const handleLogsFilterChange = async (newLevel: string) => {
    setLogsLevelFilter(newLevel);
    if (!conversationIdParam || !logsExpanded) return;

    setLogsLoading(true);
    setLogsError(null);
    try {
      const levelParam = newLevel === "ALL" ? undefined : newLevel;
      const searchParam = logsSearchInput.trim() || undefined;
      const result = await ClassificationTracesApi.getLogs(conversationIdParam, levelParam, searchParam, 500);
      setLogsData(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setLogsError(err.message);
      } else {
        setLogsError("Failed to load logs");
      }
    } finally {
      setLogsLoading(false);
    }
  };

  const handleLogsSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!conversationIdParam || !logsExpanded) return;

    setLogsLoading(true);
    setLogsError(null);
    try {
      const levelParam = logsLevelFilter === "ALL" ? undefined : logsLevelFilter;
      const searchParam = logsSearchInput.trim() || undefined;
      const result = await ClassificationTracesApi.getLogs(conversationIdParam, levelParam, searchParam, 500);
      setLogsData(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setLogsError(err.message);
      } else {
        setLogsError("Failed to load logs");
      }
    } finally {
      setLogsLoading(false);
    }
  };

  const getLogLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case "ERROR":
        return "text-rose-600 bg-rose-50";
      case "WARNING":
        return "text-amber-600 bg-amber-50";
      case "INFO":
        return "text-slate-600 bg-slate-50";
      case "DEBUG":
        return "text-sky-600 bg-sky-50";
      case "DELIMITER":
        return "text-cyan-400 bg-cyan-950";
      default:
        return "text-slate-500 bg-slate-50";
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header user={user} currentPage={{ label: "Traces", icon: "🔍" }} />

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
        >
          {/* Page Header */}
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-2">
              {conversationIdParam && (
                <Button variant="ghost" onClick={handleBackToList} className="p-2">
                  <ArrowLeft className="h-5 w-5" />
                </Button>
              )}
              <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
                <FileSearch className="h-8 w-8 text-indigo-600" />
                {conversationIdParam ? "Trace Viewer" : "Classification Traces"}
              </h1>
            </div>
            <p className="mt-2 text-slate-600">
              {conversationIdParam
                ? (
                  <>
                    Viewing traces for conversation:{" "}
                    <a
                      href={`https://app.frontapp.com/open/${conversationIdParam}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-indigo-600 hover:text-indigo-800 hover:underline"
                    >
                      {conversationIdParam}
                    </a>
                  </>
                )
                : "View classification decisions, archival traces, and LLM interactions for processed conversations."
              }
            </p>
          </div>

          {/* Search Card */}
          <Card className="mb-6">
            <CardHeader className="pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <Search className="h-5 w-5 text-slate-500" />
                Search Conversation
              </CardTitle>
              <CardDescription>
                Enter a conversation ID to view its classification trace
              </CardDescription>
            </CardHeader>
            <CardContent>
              <form onSubmit={handleSearch} className="flex items-center gap-4">
                <div className="relative flex-1 max-w-md">
                  <input
                    type="text"
                    value={searchInput}
                    onChange={(e) => setSearchInput(e.target.value)}
                    placeholder="Enter conversation ID (e.g., cnv_1fu8gs5u)"
                    className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 placeholder:text-slate-400"
                  />
                </div>
                <Button type="submit" disabled={!searchInput.trim()}>
                  <Search className="h-4 w-4 mr-2" />
                  View Trace
                </Button>
                <Button
                  type="button"
                  onClick={handleRefresh}
                  disabled={loading}
                  variant="ghost"
                  className="gap-2 border border-slate-300"
                >
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <RefreshCw className="h-4 w-4" />
                  )}
                  Refresh
                </Button>
              </form>
            </CardContent>
          </Card>

          {/* Error State */}
          {error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mb-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700"
            >
              <p className="font-medium">Error</p>
              <p className="text-sm mt-1">{error}</p>
            </motion.div>
          )}

          {/* Loading State */}
          {loading && (
            <Card>
              <CardContent className="py-12">
                <div className="flex flex-col items-center justify-center gap-3 text-slate-500">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                  <p className="text-sm">Loading...</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Trace Viewer */}
          {!loading && conversationIdParam && traceData && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              {/* Summary Card */}
              <Card className="mb-6 bg-gradient-to-r from-pink-500 via-purple-500 to-indigo-500 text-white border-0">
                <CardHeader className="flex flex-row items-center justify-between">
                  <CardTitle className="text-xl">Decision Summary</CardTitle>
                  <div className="flex gap-2">
                    <Button
                      onClick={handleViewLogs}
                      disabled={logsLoading}
                      variant="ghost"
                      className="text-white hover:bg-white/20 gap-2"
                    >
                      {logsLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <ScrollText className="h-4 w-4" />
                      )}
                      {logsLoading ? "Loading..." : logsExpanded ? "Hide Logs" : "View Logs"}
                    </Button>
                    <Button
                      onClick={handleSummarize}
                      disabled={summaryLoading}
                      variant="ghost"
                      className="text-white hover:bg-white/20 gap-2"
                    >
                      {summaryLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Sparkles className="h-4 w-4" />
                      )}
                      {summaryLoading ? "Summarizing..." : "Summarize"}
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                    <div className="bg-white/20 rounded-lg p-4 text-center backdrop-blur">
                      <p className="text-3xl font-bold">{traceData.total_traces}</p>
                      <p className="text-sm opacity-90">Total Steps</p>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 text-center backdrop-blur">
                      <p className="text-3xl font-bold">{traceData.document_processing_count}</p>
                      <p className="text-sm opacity-90">Documents</p>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 text-center backdrop-blur">
                      <p className="text-3xl font-bold">{traceData.lien_validation_count}</p>
                      <p className="text-sm opacity-90">Lien Checks</p>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 text-center backdrop-blur">
                      <p className="text-3xl font-bold">{traceData.archival_count}</p>
                      <p className="text-sm opacity-90">Archival Steps</p>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 text-center backdrop-blur">
                      <p className="text-3xl font-bold">{traceData.classification_count}</p>
                      <p className="text-sm opacity-90">Classification</p>
                    </div>
                    <div className="bg-white/20 rounded-lg p-4 text-center backdrop-blur">
                      <p className="text-3xl font-bold">{traceData.total_duration_ms}ms</p>
                      <p className="text-sm opacity-90">Total Duration</p>
                    </div>
                  </div>
                </CardContent>
              </Card>

              {/* Worker Logs Panel */}
              <AnimatePresence>
                {logsExpanded && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="mb-6"
                  >
                    <Card>
                      <CardHeader className="pb-3">
                        <div className="flex items-center justify-between">
                          <CardTitle className="text-lg flex items-center gap-2">
                            <ScrollText className="h-5 w-5 text-cyan-600" />
                            Worker Logs
                            {logsData && (
                              <span className="text-sm font-normal text-slate-500 ml-2">
                                ({logsData.filtered_entries} entries
                                {logsData.error_count > 0 && (
                                  <span className="text-rose-600 ml-1">
                                    {logsData.error_count} errors
                                  </span>
                                )}
                                {logsData.warning_count > 0 && (
                                  <span className="text-amber-600 ml-1">
                                    {logsData.warning_count} warnings
                                  </span>
                                )})
                              </span>
                            )}
                          </CardTitle>
                          <Button
                            variant="ghost"
                            onClick={() => setLogsExpanded(false)}
                            className="p-2"
                          >
                            <XCircle className="h-4 w-4" />
                          </Button>
                        </div>
                        {/* Filters */}
                        <div className="flex items-center gap-4 mt-3">
                          <div className="flex items-center gap-2">
                            <Filter className="h-4 w-4 text-slate-400" />
                            <select
                              value={logsLevelFilter}
                              onChange={(e) => handleLogsFilterChange(e.target.value)}
                              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                            >
                              <option value="ALL">All Levels</option>
                              <option value="ERROR">Errors Only</option>
                              <option value="WARNING">Warnings+</option>
                              <option value="INFO">Info+</option>
                            </select>
                          </div>
                          <form onSubmit={handleLogsSearch} className="flex-1 max-w-xs">
                            <div className="relative">
                              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                              <input
                                type="text"
                                value={logsSearchInput}
                                onChange={(e) => setLogsSearchInput(e.target.value)}
                                placeholder="Search logs..."
                                className="w-full rounded-md border border-slate-300 bg-white pl-9 pr-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                              />
                            </div>
                          </form>
                        </div>
                      </CardHeader>
                      <CardContent>
                        {logsLoading && (
                          <div className="flex items-center justify-center py-8">
                            <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
                          </div>
                        )}
                        {logsError && (
                          <div className="rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700">
                            <p className="text-sm">{logsError}</p>
                          </div>
                        )}
                        {!logsLoading && logsData && logsData.log_entries.length === 0 && (
                          <div className="py-8 text-center text-slate-500">
                            <ScrollText className="mx-auto h-8 w-8 text-slate-300 mb-2" />
                            <p className="text-sm">No logs found for this conversation.</p>
                          </div>
                        )}
                        {!logsLoading && logsData && logsData.log_entries.length > 0 && (
                          <div className="max-h-96 overflow-y-auto rounded-lg bg-slate-900 p-4 font-mono text-xs">
                            {logsData.log_entries.map((log, idx) =>
                              log.level === "DELIMITER" ? (
                                <div key={idx} className="flex items-center gap-2 py-2 my-1">
                                  <div className="flex-1 border-t border-cyan-600" />
                                  <span className="shrink-0 text-cyan-400 text-[11px] font-semibold tracking-wide uppercase px-2">
                                    {log.message}
                                  </span>
                                  <div className="flex-1 border-t border-cyan-600" />
                                </div>
                              ) : (
                              <div key={idx} className="flex gap-2 py-1 hover:bg-slate-800/50 rounded px-1">
                                <span className="text-slate-500 shrink-0 w-20">
                                  {new Date(log.timestamp).toLocaleTimeString()}
                                </span>
                                <span className={`shrink-0 w-16 px-1 rounded text-center ${getLogLevelColor(log.level)}`}>
                                  {log.level}
                                </span>
                                <span className="text-slate-400 shrink-0 w-28 truncate" title={log.module}>
                                  {log.module}
                                </span>
                                <span className={`flex-1 ${
                                  log.level === "ERROR" ? "text-rose-300" :
                                  log.level === "WARNING" ? "text-amber-300" :
                                  "text-slate-200"
                                }`}>
                                  {log.message}
                                </span>
                              </div>
                              )
                            )}
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* AI Summary */}
              {summaryError && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  className="mb-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700"
                >
                  <p className="font-medium">Summary Error</p>
                  <p className="text-sm mt-1">{summaryError}</p>
                </motion.div>
              )}
              {summaryText && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={easing}
                >
                  <Card className="mb-6">
                    <CardHeader className="pb-3">
                      <CardTitle className="text-lg flex items-center gap-2">
                        <Sparkles className="h-5 w-5 text-purple-600" />
                        AI Summary
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <pre className="whitespace-pre-wrap text-sm text-slate-700 font-sans leading-relaxed">
                        {summaryText}
                      </pre>
                    </CardContent>
                  </Card>
                </motion.div>
              )}

              {/* Traces List */}
              {traceData.traces.length === 0 ? (
                <Card>
                  <CardContent className="py-12 text-center">
                    <FileSearch className="mx-auto h-12 w-12 text-slate-300" />
                    <p className="mt-4 text-sm text-slate-500">No traces found for this conversation.</p>
                  </CardContent>
                </Card>
              ) : (
                <div className="space-y-4">
                  {traceData.traces.map((trace, index) => (
                    <TraceCard
                      key={trace.id}
                      trace={trace}
                      index={index}
                      isExpanded={expandedTraces[index] || false}
                      onToggle={() => toggleTrace(index)}
                    />
                  ))}
                </div>
              )}
            </motion.div>
          )}

          {/* No traces found for conversation */}
          {!loading && conversationIdParam && !traceData && !error && (
            <Card>
              <CardContent className="py-12 text-center">
                <FileSearch className="mx-auto h-12 w-12 text-slate-300" />
                <p className="mt-4 text-sm text-slate-500">No traces found for conversation: <strong>{conversationIdParam}</strong></p>
                <p className="text-sm text-slate-400">This conversation may not have been classified yet, or the ID is incorrect.</p>
              </CardContent>
            </Card>
          )}

          {/* Recent Conversations List */}
          {!loading && !conversationIdParam && (() => {
            const filteredConversations = searchFilter
              ? conversations.filter((conv) =>
                  conv.conversation_id.toLowerCase().includes(searchFilter.toLowerCase())
                )
              : conversations;
            return (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <Card>
                <CardHeader>
                  <CardTitle className="text-xl flex items-center gap-3">
                    <Clock className="h-5 w-5 text-indigo-600" />
                    {searchFilter ? "Search Results" : "Recent Conversations"}
                  </CardTitle>
                  <CardDescription>
                    {searchFilter ? (
                      <>
                        {filteredConversations.length} result{filteredConversations.length !== 1 ? "s" : ""} matching &quot;{searchFilter}&quot;
                        {" "}
                        <button
                          onClick={() => { setSearchFilter(""); setSearchInput(""); }}
                          className="text-indigo-600 hover:text-indigo-800 underline"
                        >
                          Clear filter
                        </button>
                      </>
                    ) : (
                      <>{conversations.length} conversation{conversations.length !== 1 ? "s" : ""} with traces</>
                    )}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {searchLoading ? (
                    <div className="flex flex-col items-center justify-center gap-3 py-12 text-slate-500">
                      <Loader2 className="h-6 w-6 animate-spin text-indigo-600" />
                      <p className="text-sm">Looking up conversation...</p>
                    </div>
                  ) : filteredConversations.length === 0 ? (
                    <div className="py-12 text-center">
                      <FileSearch className="mx-auto h-12 w-12 text-slate-300" />
                      <p className="mt-4 text-sm text-slate-500">
                        {searchFilter
                          ? <>No conversations matching &quot;{searchFilter}&quot; found.</>
                          : "No conversations with traces found."
                        }
                      </p>
                      <p className="text-sm text-slate-400">
                        {searchFilter
                          ? "Try a different search term or clear the filter."
                          : "Enter a conversation ID above to view its trace."
                        }
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {filteredConversations.map((conv) => (
                        <div
                          key={conv.conversation_id}
                          onClick={() => handleViewTrace(conv.conversation_id)}
                          className="flex items-center justify-between p-4 rounded-xl border border-slate-200 bg-gradient-to-r from-slate-50 to-white cursor-pointer transition-all hover:border-indigo-300 hover:shadow-md hover:translate-x-1"
                        >
                          <div className="flex items-center gap-4">
                            <span className="font-mono text-sm font-semibold text-indigo-600">
                              {conv.conversation_id}
                            </span>
                            <span className="text-sm text-slate-500">
                              {formatTimeAgo(conv.last_trace_at)}
                            </span>
                          </div>
                          <div className="flex items-center gap-3">
                            {conv.classification_traces > 0 && (
                              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-violet-50 text-violet-700 border border-violet-200">
                                {conv.classification_traces} classification
                              </span>
                            )}
                            {conv.archival_traces > 0 && (
                              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                                {conv.archival_traces} archival
                              </span>
                            )}
                            {conv.total_tokens > 0 && (
                              <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium bg-pink-50 text-pink-700 border border-pink-200">
                                {conv.total_tokens.toLocaleString()} tokens
                              </span>
                            )}
                            <Button
                              variant="ghost"
                              onClick={(e) => handleViewLogsNewTab(conv.conversation_id, e)}
                              className="gap-1 text-cyan-600 hover:text-cyan-700 hover:bg-cyan-50 px-2 py-1 text-sm"
                              title="View worker logs"
                            >
                              <ScrollText className="h-4 w-4" />
                              Logs
                            </Button>
                            <ChevronRight className="h-4 w-4 text-slate-400" />
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </motion.div>
            );
          })()}
        </motion.div>
      </main>
    </div>
  );
}

// Loading component for Suspense
function ClassificationTracesLoading() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50 flex items-center justify-center">
      <div className="flex flex-col items-center gap-3 text-slate-500">
        <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
        <p className="text-sm">Loading...</p>
      </div>
    </div>
  );
}

// Main Page Component with Suspense wrapper
export default function ClassificationTracesPage() {
  return (
    <Suspense fallback={<ClassificationTracesLoading />}>
      <ClassificationTracesContent />
    </Suspense>
  );
}
