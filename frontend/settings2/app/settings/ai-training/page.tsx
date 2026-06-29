"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Brain,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Filter,
  Loader2,
  RefreshCw,
  Tag,
  X,
} from "lucide-react";

import { ApiError, SettingsApi, TagsApi } from "@/lib/api";
import type { AITrainingConversationsResponse, AITrainingConversation } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Header } from "@/components/layout/Header";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

const DAYS_OPTIONS = [
  { value: 7, label: "Last 7 days" },
  { value: 14, label: "Last 14 days" },
  { value: 30, label: "Last 30 days" },
  { value: 60, label: "Last 60 days" },
  { value: 90, label: "Last 90 days" },
];

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

export default function AITrainingPage() {
  const [user, setUser] = useState<string>("Admin");
  const [result, setResult] = useState<AITrainingConversationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Filters
  const [days, setDays] = useState(14);
  const [pageSize, setPageSize] = useState(20);
  const [currentPage, setCurrentPage] = useState(1);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [showTagFilter, setShowTagFilter] = useState(false);

  const fetchConversations = useCallback(async (page: number = 1) => {
    setLoading(true);
    setError(null);
    try {
      const response = await TagsApi.getAITrainingConversations({
        page,
        pageSize,
        days,
        filterTags: selectedTags,
      });
      setResult(response);
      setCurrentPage(page);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("An unexpected error occurred");
      }
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [days, pageSize, selectedTags]);

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
        // Fetch initial data
        await fetchConversations(1);
      } catch (err) {
        if (!mounted) return;
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
          return;
        }
        console.error("Failed to bootstrap auth", err);
      }
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  // Refetch when filters change
  useEffect(() => {
    fetchConversations(1);
  }, [days, pageSize, selectedTags, fetchConversations]);

  const handleDaysChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setDays(Number(e.target.value));
  };

  const handlePageSizeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setPageSize(Number(e.target.value));
  };

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const clearTagFilters = () => {
    setSelectedTags([]);
  };

  const handleRefresh = () => {
    fetchConversations(currentPage);
  };

  const goToPage = (page: number) => {
    if (page >= 1 && page <= (result?.total_pages || 1)) {
      fetchConversations(page);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header user={user} currentPage={{ label: "AI Training", icon: "🧠" }} />

      {/* Main Content */}
      <main className="mx-auto max-w-7xl px-6 py-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
        >
          {/* Page Header */}
          <div className="mb-8">
            <h1 className="text-3xl font-bold text-slate-900 flex items-center gap-3">
              <Brain className="h-8 w-8 text-indigo-600" />
              AI Training Conversations
            </h1>
            <p className="mt-2 text-slate-600">
              View and manage conversations tagged with AI:Training for classification training purposes.
            </p>
          </div>

          {/* Controls Card */}
          <Card className="mb-6">
            <CardHeader className="pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <Filter className="h-5 w-5 text-slate-500" />
                Filters
              </CardTitle>
              <CardDescription>
                Filter conversations by time range and tags
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-center gap-4">
                {/* Days Filter */}
                <div className="relative">
                  <label className="block text-xs font-medium text-slate-500 mb-1">Time Range</label>
                  <div className="relative">
                    <select
                      value={days}
                      onChange={handleDaysChange}
                      disabled={loading}
                      className="appearance-none rounded-lg border border-slate-300 bg-white px-4 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-50"
                    >
                      {DAYS_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  </div>
                </div>

                {/* Page Size */}
                <div className="relative">
                  <label className="block text-xs font-medium text-slate-500 mb-1">Per Page</label>
                  <div className="relative">
                    <select
                      value={pageSize}
                      onChange={handlePageSizeChange}
                      disabled={loading}
                      className="appearance-none rounded-lg border border-slate-300 bg-white px-4 py-2 pr-10 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-50"
                    >
                      {PAGE_SIZE_OPTIONS.map((size) => (
                        <option key={size} value={size}>
                          {size}
                        </option>
                      ))}
                    </select>
                    <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                  </div>
                </div>

                {/* Tag Filter Toggle */}
                <div className="relative">
                  <label className="block text-xs font-medium text-slate-500 mb-1">Filter by Tags</label>
                  <Button
                    onClick={() => setShowTagFilter(!showTagFilter)}
                    variant="ghost"
                    className="gap-2 border border-slate-300"
                    disabled={loading}
                  >
                    <Tag className="h-4 w-4" />
                    {selectedTags.length > 0 ? `${selectedTags.length} selected` : "Select tags"}
                    <ChevronDown className={`h-4 w-4 transition-transform ${showTagFilter ? "rotate-180" : ""}`} />
                  </Button>
                </div>

                {/* Refresh Button */}
                <div className="relative">
                  <label className="block text-xs font-medium text-slate-500 mb-1">&nbsp;</label>
                  <Button
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
                </div>
              </div>

              {/* Tag Filter Dropdown */}
              {showTagFilter && result?.available_tags && result.available_tags.length > 0 && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  className="mt-4 p-4 bg-slate-50 rounded-lg border border-slate-200"
                >
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-sm font-medium text-slate-700">Available Tags</span>
                    {selectedTags.length > 0 && (
                      <Button
                        onClick={clearTagFilters}
                        variant="ghost"
                        className="h-auto py-1 px-2 text-xs text-slate-500 hover:text-slate-700"
                      >
                        <X className="h-3 w-3 mr-1" />
                        Clear all
                      </Button>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {result.available_tags.map((tag) => (
                      <button
                        key={tag}
                        onClick={() => handleTagToggle(tag)}
                        className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
                          selectedTags.includes(tag)
                            ? "bg-indigo-600 text-white"
                            : "bg-white text-slate-700 border border-slate-300 hover:bg-slate-100"
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}

              {/* Selected Tags Display */}
              {selectedTags.length > 0 && (
                <div className="mt-4 flex items-center gap-2">
                  <span className="text-sm text-slate-500">Filtering by:</span>
                  <div className="flex flex-wrap gap-1">
                    {selectedTags.map((tag) => (
                      <span
                        key={tag}
                        className="inline-flex items-center gap-1 rounded-full bg-indigo-100 px-2.5 py-0.5 text-xs font-medium text-indigo-700"
                      >
                        {tag}
                        <button
                          onClick={() => handleTagToggle(tag)}
                          className="hover:text-indigo-900"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Error State */}
          {error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mb-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700"
            >
              <p className="font-medium">Error loading conversations</p>
              <p className="text-sm mt-1">{error}</p>
            </motion.div>
          )}

          {/* Loading State */}
          {loading && !result && (
            <Card>
              <CardContent className="py-12">
                <div className="flex flex-col items-center justify-center gap-3 text-slate-500">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                  <p className="text-sm">Loading AI training conversations...</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Results Table */}
          {result && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <ConversationsTable
                result={result}
                loading={loading}
                currentPage={currentPage}
                onPageChange={goToPage}
              />
            </motion.div>
          )}
        </motion.div>
      </main>
    </div>
  );
}

function ConversationsTable({
  result,
  loading,
  currentPage,
  onPageChange,
}: {
  result: AITrainingConversationsResponse;
  loading: boolean;
  currentPage: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl flex items-center gap-3">
          <Brain className="h-6 w-6 text-indigo-600" />
          AI:Training Conversations
        </CardTitle>
        <CardDescription>
          {result.total} conversation{result.total !== 1 ? "s" : ""} found in the last {result.days} days
          {result.filter_tags.length > 0 && (
            <span className="text-indigo-600"> (filtered by: {result.filter_tags.join(", ")})</span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {result.conversations.length === 0 && (
          <div className="py-12 text-center">
            <Brain className="mx-auto h-12 w-12 text-slate-300" />
            <p className="mt-4 text-sm text-slate-500">
              No AI training conversations found matching your filters.
            </p>
          </div>
        )}

        {result.conversations.length > 0 && (
          <>
            <div className="overflow-x-auto rounded-xl border border-slate-200">
              <table className="min-w-full divide-y divide-slate-200 text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-4 py-3 text-left font-semibold">Conversation ID</th>
                    <th className="px-4 py-3 text-left font-semibold">Subject</th>
                    <th className="px-4 py-3 text-left font-semibold">Recipient</th>
                    <th className="px-4 py-3 text-left font-semibold">Created</th>
                    <th className="px-4 py-3 text-left font-semibold">Status</th>
                    <th className="px-4 py-3 text-left font-semibold">Tags</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                  {result.conversations.map((conv) => (
                    <ConversationRow key={conv.conversation_id} conversation={conv} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            {result.total_pages > 1 && (
              <div className="flex items-center justify-between pt-4">
                <div className="text-sm text-slate-500">
                  Page {currentPage} of {result.total_pages} ({result.total} total)
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    onClick={() => onPageChange(currentPage - 1)}
                    disabled={currentPage <= 1 || loading}
                    variant="ghost"
                    className="h-9 w-9 p-0 border border-slate-300"
                  >
                    <ChevronLeft className="h-4 w-4" />
                  </Button>

                  {/* Page number buttons */}
                  {generatePageNumbers(currentPage, result.total_pages).map((pageNum, idx) => (
                    pageNum === "..." ? (
                      <span key={`ellipsis-${idx}`} className="px-2 text-slate-400">...</span>
                    ) : (
                      <Button
                        key={pageNum}
                        onClick={() => onPageChange(pageNum as number)}
                        disabled={loading}
                        variant={currentPage === pageNum ? "primary" : "ghost"}
                        className={`h-9 w-9 p-0 ${
                          currentPage === pageNum
                            ? "bg-indigo-600 text-white hover:bg-indigo-700"
                            : "border border-slate-300"
                        }`}
                      >
                        {pageNum}
                      </Button>
                    )
                  ))}

                  <Button
                    onClick={() => onPageChange(currentPage + 1)}
                    disabled={currentPage >= result.total_pages || loading}
                    variant="ghost"
                    className="h-9 w-9 p-0 border border-slate-300"
                  >
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ConversationRow({ conversation }: { conversation: AITrainingConversation }) {
  // Filter out AI:Training from displayed tags since it's implied
  const displayTags = conversation.tags.filter(
    (tag) => tag.toLowerCase() !== "ai:training"
  );

  return (
    <tr className="hover:bg-slate-50 transition-colors">
      <td className="px-4 py-3 font-mono text-xs">
        <a
          href={conversation.front_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 hover:underline"
        >
          {conversation.conversation_id}
          <ExternalLink className="h-3 w-3" />
        </a>
      </td>
      <td className="px-4 py-3 max-w-xs truncate">
        {conversation.subject || <span className="text-slate-400 italic">No subject</span>}
      </td>
      <td className="px-4 py-3 text-xs">
        {conversation.recipient || <span className="text-slate-400">-</span>}
      </td>
      <td className="px-4 py-3 text-xs whitespace-nowrap">
        {conversation.created_at
          ? new Date(conversation.created_at).toLocaleString()
          : "-"}
      </td>
      <td className="px-4 py-3 text-xs">
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-medium ${
            conversation.status === "archived"
              ? "bg-slate-100 text-slate-600"
              : conversation.status === "assigned"
              ? "bg-blue-50 text-blue-700"
              : conversation.status === "unassigned"
              ? "bg-amber-50 text-amber-700"
              : "bg-slate-100 text-slate-600"
          }`}
        >
          {conversation.status}
        </span>
      </td>
      <td className="px-4 py-3 text-xs">
        {displayTags.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {displayTags.map((tag, idx) => (
              <span
                key={`${tag}-${idx}`}
                className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 border border-emerald-200 text-xs"
              >
                {tag}
              </span>
            ))}
          </div>
        ) : (
          <span className="text-slate-400 italic">AI:Training only</span>
        )}
      </td>
    </tr>
  );
}

function generatePageNumbers(current: number, total: number): (number | string)[] {
  if (total <= 7) {
    return Array.from({ length: total }, (_, i) => i + 1);
  }

  const pages: (number | string)[] = [];

  // Always show first page
  pages.push(1);

  if (current > 3) {
    pages.push("...");
  }

  // Show pages around current
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);

  for (let i = start; i <= end; i++) {
    if (!pages.includes(i)) {
      pages.push(i);
    }
  }

  if (current < total - 2) {
    pages.push("...");
  }

  // Always show last page
  if (!pages.includes(total)) {
    pages.push(total);
  }

  return pages;
}
