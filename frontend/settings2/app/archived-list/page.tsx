"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Archive,
  Calendar,
  ChevronDown,
  ExternalLink,
  Loader2,
  RefreshCw,
} from "lucide-react";

import { ApiError, SettingsApi, TagsApi } from "@/lib/api";
import type { ArchivedConversationsResponse } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MENU_ITEMS } from "../template-config/constants/template-config.constants";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

// Generate last 30 days for dropdown
function generateDateOptions(): { value: string; label: string }[] {
  const options: { value: string; label: string }[] = [];
  const today = new Date();

  for (let i = 0; i < 30; i++) {
    const date = new Date(today);
    date.setDate(today.getDate() - i);
    const isoDate = date.toISOString().slice(0, 10);
    const label = i === 0
      ? `Today (${isoDate})`
      : i === 1
        ? `Yesterday (${isoDate})`
        : date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
    options.push({ value: isoDate, label });
  }

  return options;
}

const defaultDate = () => new Date().toISOString().slice(0, 10);

export default function ArchivedListPage() {
  const [user, setUser] = useState<string>("Admin");
  const [selectedDate, setSelectedDate] = useState(defaultDate());
  const [result, setResult] = useState<ArchivedConversationsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [dateOptions] = useState(generateDateOptions);

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
        // Auto-fetch for today on page load
        const todayDate = defaultDate();
        setLoading(true);
        try {
          const response = await TagsApi.getArchivedConversations(todayDate);
          if (mounted) {
            setResult(response);
          }
        } catch (err) {
          if (mounted) {
            if (err instanceof ApiError) {
              setError(err.message);
            } else {
              setError("An unexpected error occurred");
            }
          }
        } finally {
          if (mounted) {
            setLoading(false);
          }
        }
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

  const fetchArchivedConversations = async (date: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await TagsApi.getArchivedConversations(date);
      setResult(response);
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
  };

  const handleDateChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newDate = e.target.value;
    setSelectedDate(newDate);
    fetchArchivedConversations(newDate);
  };

  const handleRefresh = () => {
    fetchArchivedConversations(selectedDate);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      {/* Navigation Header */}
      <header className="sticky top-0 z-30 backdrop-blur-md bg-white/70 border-b border-slate-200/60">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
          <nav className="flex items-center gap-1 text-sm font-medium">
            {MENU_ITEMS.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-lg px-3 py-1.5 text-slate-600 hover:bg-slate-100 hover:text-slate-900 transition-colors"
              >
                <span className="mr-1">{item.icon}</span>
                {item.label}
              </Link>
            ))}
            <span className="rounded-lg px-3 py-1.5 bg-indigo-50 text-indigo-700 font-semibold">
              <span className="mr-1">📂</span>
              Archived List
            </span>
          </nav>
          <div className="flex items-center gap-3 text-sm text-slate-500">
            <span>Logged in as <strong className="text-slate-700">{user}</strong></span>
          </div>
        </div>
      </header>

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
              <Archive className="h-8 w-8 text-indigo-600" />
              Archived Conversations
            </h1>
            <p className="mt-2 text-slate-600">
              View all conversations that have been automatically archived by the system.
            </p>
          </div>

          {/* Controls Card */}
          <Card className="mb-6">
            <CardHeader className="pb-4">
              <CardTitle className="text-lg flex items-center gap-2">
                <Calendar className="h-5 w-5 text-slate-500" />
                Select Date
              </CardTitle>
              <CardDescription>
                Choose a day to view archived conversations
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="flex items-center gap-4">
                <div className="relative flex-1 max-w-xs">
                  <select
                    value={selectedDate}
                    onChange={handleDateChange}
                    disabled={loading}
                    className="w-full appearance-none rounded-lg border border-slate-300 bg-white px-4 py-2.5 pr-10 text-sm font-medium text-slate-700 shadow-sm transition-colors hover:border-slate-400 focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 disabled:opacity-50"
                  >
                    {dateOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                </div>
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
            </CardContent>
          </Card>

          {/* Error State */}
          {error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="mb-6 rounded-lg border border-rose-200 bg-rose-50 p-4 text-rose-700"
            >
              <p className="font-medium">Error loading archived conversations</p>
              <p className="text-sm mt-1">{error}</p>
            </motion.div>
          )}

          {/* Loading State */}
          {loading && (
            <Card>
              <CardContent className="py-12">
                <div className="flex flex-col items-center justify-center gap-3 text-slate-500">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                  <p className="text-sm">Loading archived conversations...</p>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Results Table */}
          {!loading && result && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <ArchivedConversationsTable result={result} />
            </motion.div>
          )}
        </motion.div>
      </main>
    </div>
  );
}

function ArchivedConversationsTable({ result }: { result: ArchivedConversationsResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl flex items-center gap-3">
          <Archive className="h-6 w-6 text-indigo-600" />
          Archived on {result.date}
        </CardTitle>
        <CardDescription>
          {result.total_archived} conversation{result.total_archived !== 1 ? "s" : ""} automatically archived.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {result.conversations.length === 0 && (
          <div className="py-12 text-center">
            <Archive className="mx-auto h-12 w-12 text-slate-300" />
            <p className="mt-4 text-sm text-slate-500">No archived conversations found for this date.</p>
          </div>
        )}

        {result.conversations.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-left font-semibold">Conversation ID</th>
                  <th className="px-4 py-3 text-left font-semibold">Subject</th>
                  <th className="px-4 py-3 text-left font-semibold">Sender</th>
                  <th className="px-4 py-3 text-left font-semibold">Created</th>
                  <th className="px-4 py-3 text-left font-semibold">Archived</th>
                  <th className="px-4 py-3 text-left font-semibold">Tags</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                {result.conversations.map((conv) => (
                  <tr key={conv.conversation_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs">
                      <a
                        href={`https://app.frontapp.com/open/${conv.conversation_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 text-indigo-600 hover:text-indigo-800 hover:underline"
                      >
                        {conv.conversation_id}
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate">
                      {conv.subject || <span className="text-slate-400 italic">No subject</span>}
                    </td>
                    <td className="px-4 py-3 text-xs">{conv.sender}</td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap">
                      {new Date(conv.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-xs whitespace-nowrap">
                      {new Date(conv.archived_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {conv.tags_applied.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {conv.tags_applied.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 border border-emerald-200 text-xs"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-slate-400 italic">No tags</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
