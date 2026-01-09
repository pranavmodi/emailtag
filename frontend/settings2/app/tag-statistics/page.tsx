"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Calendar,
  CheckCircle2,
  Loader2,
  RefreshCw,
  Search,
  Tag,
  Zap,
} from "lucide-react";

import { ApiError, SettingsApi, TagsApi } from "@/lib/api";
import type {
  AllTagsStatisticsResponse,
  ArchivedConversationsResponse,
  EvalClassificationEntry,
  EvalClassificationResponse,
  TagStatisticsResponse,
} from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { MENU_ITEMS } from "../template-config/constants/template-config.constants";

const TAG_GROUPS: Array<{ label: string; options: string[] }> = [
  {
    label: "Scheduling > RX",
    options: [
      "Order Pending",
      "Order Entered",
      "Incomplete",
      "RX",
      "Apt status req",
      "No Show",
      "Cash Patient",
    ],
  },
  {
    label: "Scheduling",
    options: ["Cancelled", "Reschedule Request", "Schedule Request", "Will contact patient"],
  },
  {
    label: "Medical Records & Images",
    options: [
      "Release of Records",
      "Image Request",
      "CD Requests",
      "Reports Request",
      "US Tech Sheet",
      "Portal Requests",
      "Referral pad request",
      "Incorrect patient info",
      "Incorrect study info",
    ],
  },
  {
    label: "Accounts Receivable > Billing",
    options: ["Bill or balance Request"],
  },
  {
    label: "Accounts Receivable > Liens",
    options: ["Missing Lien Request"],
  },
  {
    label: "Accounts Receivable > PSL",
    options: ["Rad Lien (PSL)", "Tech Lien (PSL)", "Lien Modified (PSL)"],
  },
  {
    label: "Accounts Receivable > ASL",
    options: ["Rad Lien (ASL)", "Tech Lien (ASL)", "Lien Modified (ASL)"],
  },
  {
    label: "Accounts Receivable > Negotiations",
    options: ["Bill Offer", "Pending Approval", "Offer Approved", "Counter Offer Sent"],
  },
  {
    label: "Accounts Receivable > Case Updates",
    options: [
      "New Attorney",
      "Drop Letter",
      "Drop Pending",
      "Promise to send payment",
      "Waiting to clear liability",
      "Waiting on settlement check",
      "Sent payment but not received",
      "Refund Request",
      "Payment on way",
    ],
  },
  {
    label: "Accounts Receivable > Collections",
    options: ["To send to collections"],
  },
];

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

const defaultDate = () => new Date().toISOString().slice(0, 10);

const STAT_BADGE = {
  success: "bg-emerald-50 text-emerald-600 border-emerald-200",
  warn: "bg-amber-50 text-amber-700 border-amber-200",
  danger: "bg-rose-50 text-rose-600 border-rose-200",
} as const;

const percent = (value?: number) => `${value?.toFixed(1) ?? "0.0"}%`;

export default function TagStatisticsPage() {
  const [user, setUser] = useState<string>("Admin");
  const [mode, setMode] = useState<"statistics" | "eval" | "archive">("statistics");
  const [analysisType, setAnalysisType] = useState<"single" | "all">("single");
  const [tagName, setTagName] = useState("");
  const [date, setDate] = useState(defaultDate());
  const [hour, setHour] = useState<string>("");
  const [singleResult, setSingleResult] = useState<TagStatisticsResponse | null>(null);
  const [allResult, setAllResult] = useState<AllTagsStatisticsResponse | null>(null);
  const [statisticsError, setStatisticsError] = useState<string | null>(null);
  const [statisticsLoading, setStatisticsLoading] = useState(false);
  const [analysisProgress, setAnalysisProgress] = useState<{
    stage?: string;
    message?: string;
    progress?: number;
    total?: number;
    current?: number;
  } | null>(null);

  const [evalConversationId, setEvalConversationId] = useState("");
  const [evalDate, setEvalDate] = useState(defaultDate());
  const [evalResult, setEvalResult] = useState<EvalClassificationResponse | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);

  const [archiveDate, setArchiveDate] = useState(defaultDate());
  const [archiveHour, setArchiveHour] = useState<string>("");
  const [archiveResult, setArchiveResult] = useState<ArchivedConversationsResponse | null>(null);
  const [archiveError, setArchiveError] = useState<string | null>(null);
  const [archiveLoading, setArchiveLoading] = useState(false);

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
      } catch (error) {
        if (!mounted) return;
        if (error instanceof ApiError && error.status === 401) {
          window.location.href = "/login";
          return;
        }
        console.error("Failed to bootstrap auth", error);
      }
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  const resetResults = () => {
    setSingleResult(null);
    setAllResult(null);
    setStatisticsError(null);
  };

  const pollAnalysisStatus = async (taskId: string, maxAttempts = 300) => {
    let attempts = 0;

    const poll = async (): Promise<void> => {
      try {
        const statusResponse = await TagsApi.getAnalysisStatus(taskId);

        if (statusResponse.status === "SUCCESS" && statusResponse.result) {
          setAllResult(statusResponse.result);
          setAnalysisProgress(null);
          setStatisticsLoading(false);
          return;
        } else if (statusResponse.status === "PROGRESS") {
          setAnalysisProgress({
            stage: statusResponse.stage,
            message: statusResponse.message,
            progress: statusResponse.progress,
            total: statusResponse.total,
            current: statusResponse.current,
          });
        } else if (statusResponse.status === "FAILURE") {
          setStatisticsError(statusResponse.error || "Analysis failed");
          setAnalysisProgress(null);
          setStatisticsLoading(false);
          return;
        }

        if (attempts >= maxAttempts) {
          console.error(`Analysis task timeout after 10 minutes`);
          setStatisticsError("Analysis timed out. Please try again.");
          setAnalysisProgress(null);
          setStatisticsLoading(false);
          return;
        }

        attempts++;
        setTimeout(() => poll(), 2000);
      } catch (error) {
        console.error("Error polling analysis status:", error);
        setStatisticsError("Failed to check analysis status");
        setAnalysisProgress(null);
        setStatisticsLoading(false);
      }
    };

    await poll();
  };

  const runStatistics = async () => {
    if (!date) {
      setStatisticsError("Select a date to analyze.");
      return;
    }

    if (analysisType === "single" && !tagName) {
      setStatisticsError("Select a tag to analyze.");
      return;
    }

    if (analysisType === "all" && hour !== "") {
      const parsed = Number(hour);
      if (Number.isNaN(parsed) || parsed < 0 || parsed > 23) {
        setStatisticsError("Hour must be between 0 and 23.");
        return;
      }
    }

    setStatisticsLoading(true);
    setStatisticsError(null);
    setAnalysisProgress(null);
    try {
      if (analysisType === "single") {
        const result = await TagsApi.getTagStatistics(tagName, date);
        setSingleResult(result);
        setAllResult(null);
        setStatisticsLoading(false);
      } else {
        // For "all tags" analysis, use async mode with progress tracking
        const parsedHour = hour !== "" ? Number(hour) : undefined;
        const response: any = await TagsApi.getAllTagsStatistics(date, parsedHour);

        if (response.task_id) {
          // Async mode: poll for progress
          setAnalysisProgress({
            stage: "queued",
            message: "Analysis queued, starting...",
            progress: 0,
          });
          await pollAnalysisStatus(response.task_id);
        } else {
          // Sync mode (shouldn't happen with async_mode=true by default)
          setAllResult(response);
          setStatisticsLoading(false);
        }
        setSingleResult(null);
      }
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch tag statistics. Try again.";
      setStatisticsError(message);
      setSingleResult(null);
      setAllResult(null);
      setAnalysisProgress(null);
      setStatisticsLoading(false);
    }
  };

  const runEval = async () => {
    if (!evalConversationId && !evalDate) {
      setEvalError("Enter a conversation ID or select a date.");
      return;
    }

    setEvalLoading(true);
    setEvalError(null);
    try {
      const response = await TagsApi.evalClassification({
        conversationId: evalConversationId || undefined,
        date: evalConversationId ? undefined : evalDate,
      });
      setEvalResult(response);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to run eval classification.";
      setEvalError(message);
      setEvalResult(null);
    } finally {
      setEvalLoading(false);
    }
  };

  const runArchiveQuery = async () => {
    if (!archiveDate) {
      setArchiveError("Select a date to query.");
      return;
    }

    if (archiveHour !== "") {
      const parsed = Number(archiveHour);
      if (Number.isNaN(parsed) || parsed < 0 || parsed > 23) {
        setArchiveError("Hour must be between 0 and 23.");
        return;
      }
    }

    setArchiveLoading(true);
    setArchiveError(null);
    try {
      const parsedHour = archiveHour !== "" ? Number(archiveHour) : undefined;
      const response = await TagsApi.getArchivedConversations(archiveDate, parsedHour);
      setArchiveResult(response);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Failed to fetch archived conversations.";
      setArchiveError(message);
      setArchiveResult(null);
    } finally {
      setArchiveLoading(false);
    }
  };

  const summaryCards = useMemo(() => {
    if (singleResult) {
      return [
        {
          label: "Total Conversations",
          value: singleResult.total_conversations,
          icon: <BarChart3 className="h-5 w-5" />,
        },
        {
          label: "Still Tagged",
          value: singleResult.still_tagged,
          pill: percent(singleResult.still_tagged_percentage),
          tone: STAT_BADGE.success,
        },
        {
          label: "Re-Tagged",
          value: singleResult.re_tagged,
          pill: percent(singleResult.re_tagged_percentage),
          tone: STAT_BADGE.warn,
        },
        {
          label: "Fetch Errors",
          value: singleResult.fetch_failed,
          tone: STAT_BADGE.danger,
        },
      ];
    }

    if (allResult) {
      // Calculate overall statistics across all tags
      const totalTagApplications = allResult.tag_statistics.reduce(
        (sum, tag) => sum + tag.total_conversations, 0
      );
      const totalStillTagged = allResult.tag_statistics.reduce(
        (sum, tag) => sum + tag.still_tagged, 0
      );
      const totalReTagged = allResult.tag_statistics.reduce(
        (sum, tag) => sum + tag.re_tagged, 0
      );
      const totalFetchFailed = allResult.tag_statistics.reduce(
        (sum, tag) => sum + tag.fetch_failed, 0
      );
      const overallRetentionPct = totalTagApplications > 0
        ? (totalStillTagged / totalTagApplications) * 100
        : 0;

      return [
        {
          label: "Unique Conversations",
          value: allResult.total_conversations,
          icon: <Activity className="h-5 w-5" />,
        },
        {
          label: "Tags Evaluated",
          value: allResult.total_tags,
          icon: <Tag className="h-5 w-5" />,
        },
        {
          label: "Total Tag Applications",
          value: totalTagApplications,
          icon: <BarChart3 className="h-5 w-5" />,
        },
        {
          label: "Still Tagged (Overall)",
          value: totalStillTagged,
          pill: percent(overallRetentionPct),
          tone: STAT_BADGE.success,
        },
        {
          label: "Re-Tagged (Overall)",
          value: totalReTagged,
          pill: percent((totalReTagged / totalTagApplications) * 100),
          tone: STAT_BADGE.warn,
        },
        {
          label: "Fetch Errors (Overall)",
          value: totalFetchFailed,
          tone: STAT_BADGE.danger,
        },
      ];
    }

    return [];
  }, [singleResult, allResult]);

  const logout = async () => {
    try {
      await SettingsApi.logout();
    } catch (error) {
      console.error("logout failed", error);
    } finally {
      window.location.href = "/login";
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
      <nav className="grid gap-3 rounded-3xl border border-white/60 bg-white/80 p-3 shadow-xl shadow-slate-900/5 backdrop-blur lg:grid-cols-4">
        {MENU_ITEMS.map((item) => {
          const isActive = item.href === "/tag-statistics";
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-2xl border p-4 transition hover:-translate-y-1 hover:shadow-lg ${
                isActive
                  ? "border-slate-900 bg-slate-900 text-white shadow-lg"
                  : "border-slate-200 bg-white text-slate-700"
              }`}
            >
              <div className="flex items-center gap-3 text-lg font-semibold">
                <span>{item.icon}</span>
                {item.label}
              </div>
              <p
                className={`mt-1 text-sm ${
                  isActive ? "text-white/80" : "text-slate-500"
                }`}
              >
                {item.description}
              </p>
            </Link>
          );
        })}
      </nav>

      <motion.section
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={easing}
        className="rounded-3xl border border-white/40 bg-gradient-to-br from-indigo-500 via-purple-500 to-sky-500 p-8 text-white shadow-2xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-white/80">EmailTag Insights</p>
            <h1 className="text-3xl font-semibold">Tag Retention & Eval Mode</h1>
            <p className="text-white/80">
              Compare the tags we applied against what still lives in Front & stress test new model
              changes without writing SQL.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl bg-white/10 px-4 py-2 text-sm backdrop-blur">
            <span className="font-medium">{user}</span>
            <span className="text-white/60">•</span>
            <Button
              variant="ghost"
              onClick={logout}
              className="border-white/30 text-white/90 hover:bg-white/10 hover:text-white"
            >
              Logout
            </Button>
          </div>
        </div>

        <div className="mt-6 flex flex-wrap items-center gap-4">
          <span className="text-sm font-semibold uppercase tracking-[0.3em] text-white/70">
            Page Mode
          </span>
          <div className="rounded-full bg-white/20 p-1 text-slate-900 backdrop-blur">
            <div className="flex gap-2">
              {[
                { key: "statistics", label: "📊 Retention" },
                { key: "eval", label: "🧪 Eval Mode" },
                { key: "archive", label: "📁 Archive View" },
              ].map((item) => (
                <button
                  key={item.key}
                  onClick={() => setMode(item.key as typeof mode)}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    mode === item.key
                      ? "bg-white text-slate-900 shadow"
                      : "text-white/80 hover:text-white"
                  }`}
                >
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </motion.section>

      {mode === "statistics" && (
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.05 }}
          className="space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl">
                <BarChart3 className="h-6 w-6 text-brand.indigo" /> Query Parameters
              </CardTitle>
              <CardDescription>
                Analyze how many Front conversations kept their tag vs. were re-tagged.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                  <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
                    Analysis Mode
                  </p>
                  <p className="text-lg font-semibold text-slate-900">
                    {analysisType === "single" ? "Single Tag" : "All Tags on Date"}
                  </p>
                </div>
                <div className="flex items-center gap-3 text-sm font-semibold uppercase tracking-wide text-slate-500">
                  Single Tag
                  <Switch
                    checked={analysisType === "all"}
                    onCheckedChange={(value) => {
                      setAnalysisType(value ? "all" : "single");
                      resetResults();
                    }}
                  />
                  All Tags
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-2">
                {analysisType === "single" && (
                  <label className="space-y-2 text-sm font-medium text-slate-700">
                    Tag Name (leaf nodes only)
                    <select
                      value={tagName}
                      onChange={(event) => setTagName(event.target.value)}
                      className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                    >
                      <option value="">-- Select a tag --</option>
                      {TAG_GROUPS.map((group) => (
                        <optgroup key={group.label} label={group.label}>
                          {group.options.map((option) => (
                            <option key={`${group.label}-${option}`} value={option}>
                              {option}
                            </option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </label>
                )}

                <label className="space-y-2 text-sm font-medium text-slate-700">
                  Target Date
                  <input
                    type="date"
                    value={date}
                    onChange={(event) => setDate(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                  />
                </label>

                {analysisType === "all" && (
                  <label className="space-y-2 text-sm font-medium text-slate-700">
                    Hour (optional)
                    <input
                      type="number"
                      min="0"
                      max="23"
                      placeholder="0-23"
                      value={hour}
                      onChange={(event) => setHour(event.target.value)}
                      className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                    />
                  </label>
                )}
              </div>

              <Button
                onClick={runStatistics}
                disabled={statisticsLoading}
                className="w-full justify-center bg-slate-900 text-white"
              >
                {statisticsLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Gathering stats
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" /> Run Analysis
                  </>
                )}
              </Button>

              {analysisProgress && (
                <div className="space-y-3 rounded-2xl border border-indigo-200 bg-indigo-50 p-4">
                  <div className="flex items-center justify-between text-sm">
                    <span className="font-medium text-indigo-900">
                      {analysisProgress.message || "Processing..."}
                    </span>
                    {analysisProgress.progress !== undefined && (
                      <span className="text-indigo-700 font-semibold">
                        {analysisProgress.progress}%
                      </span>
                    )}
                  </div>

                  {/* Progress bar */}
                  <div className="h-2 w-full overflow-hidden rounded-full bg-indigo-100">
                    <div
                      className="h-full bg-indigo-600 transition-all duration-300 ease-out"
                      style={{ width: `${analysisProgress.progress || 0}%` }}
                    />
                  </div>

                  {/* Detailed info */}
                  {analysisProgress.stage && (
                    <div className="text-xs text-indigo-600">
                      Stage: <span className="font-medium">{analysisProgress.stage}</span>
                      {analysisProgress.current && analysisProgress.total && (
                        <span className="ml-2">
                          ({analysisProgress.current}/{analysisProgress.total} conversations)
                        </span>
                      )}
                    </div>
                  )}
                </div>
              )}

              {statisticsError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {statisticsError}
                </div>
              )}
            </CardContent>
          </Card>

          {(singleResult || allResult) && (
            <div className="grid gap-4 md:grid-cols-2">
              {summaryCards.map((card) => (
                <Card key={card.label}>
                  <CardContent className="flex flex-col gap-1 pt-6">
                    <p className="text-sm font-semibold uppercase tracking-wide text-slate-500">
                      {card.label}
                    </p>
                    <p className="text-3xl font-bold text-slate-900">{card.value}</p>
                    {card.pill && (
                      <Badge className={card.tone ?? STAT_BADGE.success}>{card.pill}</Badge>
                    )}
                    {card.icon && <div className="text-slate-400">{card.icon}</div>}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}

          {singleResult && <SingleTagResult result={singleResult} />}
          {allResult && <AllTagsResult result={allResult} />}
        </motion.section>
      )}

      {mode === "eval" && (
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.05 }}
          className="space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl">
                <Zap className="h-6 w-6 text-brand.indigo" /> Eval Mode
              </CardTitle>
              <CardDescription>
                Run the classifier in “shadow” to compare predictions vs. the tags that ultimately
                landed in Front.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm font-medium text-slate-700">
                  Conversation ID
                  <input
                    type="text"
                    placeholder="conv_123..."
                    value={evalConversationId}
                    onChange={(event) => setEvalConversationId(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                  />
                </label>
                <label className="space-y-2 text-sm font-medium text-slate-700">
                  Date (evaluates all conversations on date when ID not provided)
                  <input
                    type="date"
                    value={evalDate}
                    onChange={(event) => setEvalDate(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                  />
                </label>
              </div>

              <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
                Supplying a conversation ID runs eval for that single conversation. Leaving it blank
                evaluates every conversation created on the selected date. Document analysis is
                skipped to keep the run fast.
              </div>

              <Button
                onClick={runEval}
                disabled={evalLoading}
                className="w-full justify-center bg-slate-900 text-white"
              >
                {evalLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Running eval
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" /> Compare predictions
                  </>
                )}
              </Button>

              {evalError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {evalError}
                </div>
              )}
            </CardContent>
          </Card>

          {evalResult && <EvalResults result={evalResult} />}
        </motion.section>
      )}

      {mode === "archive" && (
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.05 }}
          className="space-y-6"
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl">
                <Activity className="h-6 w-6 text-brand.indigo" /> Archived Conversations
              </CardTitle>
              <CardDescription>
                View all conversations that were automatically archived on a specific date.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-4 md:grid-cols-2">
                <label className="space-y-2 text-sm font-medium text-slate-700">
                  Target Date
                  <input
                    type="date"
                    value={archiveDate}
                    onChange={(event) => setArchiveDate(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                  />
                </label>

                <label className="space-y-2 text-sm font-medium text-slate-700">
                  Hour (optional)
                  <input
                    type="number"
                    min="0"
                    max="23"
                    placeholder="0-23"
                    value={archiveHour}
                    onChange={(event) => setArchiveHour(event.target.value)}
                    className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                  />
                </label>
              </div>

              <Button
                onClick={runArchiveQuery}
                disabled={archiveLoading}
                className="w-full justify-center bg-slate-900 text-white"
              >
                {archiveLoading ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" /> Loading archives
                  </>
                ) : (
                  <>
                    <Search className="h-4 w-4" /> View Archived Conversations
                  </>
                )}
              </Button>

              {archiveError && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {archiveError}
                </div>
              )}
            </CardContent>
          </Card>

          {archiveResult && <ArchivedConversationsTable result={archiveResult} />}
        </motion.section>
      )}
    </div>
  );
}

function SingleTagResult({ result }: { result: TagStatisticsResponse }) {
  const [evalResults, setEvalResults] = useState<Record<string, EvalClassificationEntry>>({});
  const [evalLoading, setEvalLoading] = useState<Record<string, boolean>>({});
  const [bulkEvalLoading, setBulkEvalLoading] = useState(false);

  const pollTaskStatus = async (taskId: string, conversationId: string, maxAttempts = 150) => {
    let attempts = 0;

    const poll = async () => {
      try {
        const statusResponse = await TagsApi.getEvalStatus(taskId);

        if (statusResponse.status === "SUCCESS" && statusResponse.result) {
          // Task completed successfully
          setEvalResults((prev) => ({ ...prev, [conversationId]: statusResponse.result! }));
          setEvalLoading((prev) => ({ ...prev, [conversationId]: false }));
          return true;
        } else if (statusResponse.status === "FAILURE") {
          // Task failed
          console.error(`Eval task failed for ${conversationId}:`, statusResponse.error);
          setEvalLoading((prev) => ({ ...prev, [conversationId]: false }));
          return true;
        } else if (attempts >= maxAttempts) {
          // Timeout after 5 minutes (150 attempts × 2 seconds)
          console.error(`Eval task timeout for ${conversationId} after ${maxAttempts * 2 / 60} minutes`);
          setEvalLoading((prev) => ({ ...prev, [conversationId]: false }));
          return true;
        }

        // Still pending/running, poll again after 2 seconds
        attempts++;
        setTimeout(() => poll(), 2000);
        return false;
      } catch (error) {
        console.error(`Error polling task status for ${conversationId}:`, error);
        setEvalLoading((prev) => ({ ...prev, [conversationId]: false }));
        return true;
      }
    };

    await poll();
  };

  const runEval = async (conversationId: string) => {
    setEvalLoading((prev) => ({ ...prev, [conversationId]: true }));
    try {
      const response = await TagsApi.evalClassification({ conversationId });

      // Response now contains task_id instead of results
      if (response.task_id) {
        // Start polling for results
        await pollTaskStatus(response.task_id, conversationId);
      } else if (response.results && response.results.length > 0) {
        // Fallback for sync mode (if still supported)
        setEvalResults((prev) => ({ ...prev, [conversationId]: response.results[0] }));
        setEvalLoading((prev) => ({ ...prev, [conversationId]: false }));
      }
    } catch (error) {
      console.error(`Failed to eval conversation ${conversationId}:`, error);
      setEvalLoading((prev) => ({ ...prev, [conversationId]: false }));
    }
  };

  const runBulkEval = async () => {
    setBulkEvalLoading(true);
    try {
      // Queue eval tasks sequentially (one at a time, in order)
      for (const conv of result.conversations) {
        try {
          // Mark this conversation as loading
          setEvalLoading((prev) => ({ ...prev, [conv.conversation_id]: true }));

          const response = await TagsApi.evalClassification({ conversationId: conv.conversation_id });

          if (response.task_id) {
            // Poll for this task's results
            await pollTaskStatus(response.task_id, conv.conversation_id);
          } else if (response.results && response.results.length > 0) {
            setEvalResults((prev) => ({ ...prev, [conv.conversation_id]: response.results[0] }));
            setEvalLoading((prev) => ({ ...prev, [conv.conversation_id]: false }));
          }
        } catch (error) {
          console.error(`Failed to eval ${conv.conversation_id}:`, error);
          setEvalLoading((prev) => ({ ...prev, [conv.conversation_id]: false }));
        }
      }
    } finally {
      setBulkEvalLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-2xl">Retention for {result.tag_name}</CardTitle>
            <CardDescription>Tag impressions originally applied on {result.date}</CardDescription>
          </div>
          <Button
            onClick={runBulkEval}
            disabled={bulkEvalLoading}
            variant="ghost"
            className="border border-indigo-200 text-indigo-600 hover:bg-indigo-50"
          >
            {bulkEvalLoading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Evaluating...
              </>
            ) : (
              <>
                <Zap className="h-4 w-4" />
                Run Bulk Eval
              </>
            )}
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto rounded-2xl border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left">Conversation ID</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Current Tags</th>
                <th className="px-4 py-3 text-left">Eval</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
              {result.conversations.map((conversation) => {
                const evalResult = evalResults[conversation.conversation_id];
                return (
                  <tr key={conversation.conversation_id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono text-xs">
                      <a
                        href={`https://app.frontapp.com/open/${conversation.conversation_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-600 hover:text-indigo-800 hover:underline"
                      >
                        {conversation.conversation_id}
                      </a>
                    </td>
                    <td className="px-4 py-3">
                      <Badge
                        className={
                          conversation.still_has_tag ? STAT_BADGE.success : STAT_BADGE.warn
                        }
                      >
                        {conversation.still_has_tag ? "Still tagged" : "Re-tagged"}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {conversation.current_tags.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {conversation.current_tags.map((tag) => (
                            <span
                              key={`${conversation.conversation_id}-${tag}`}
                              className="rounded-full bg-slate-100 px-2 py-0.5"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-slate-400">No tags returned</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {evalResult ? (
                        <div className="space-y-2">
                          {evalResult.predicted_tags && evalResult.predicted_tags.length > 0 ? (
                            <div className="text-xs text-slate-600">
                              <div className="text-slate-400">Predicted tags</div>
                              <div className="mt-1 flex flex-wrap gap-1">
                                {evalResult.predicted_tags.map((tag: string) => (
                                  <span
                                    key={tag}
                                    className="rounded-full bg-indigo-100 px-2 py-0.5 text-indigo-700"
                                  >
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <span className="text-xs text-slate-400">No prediction returned</span>
                          )}
                          <Button
                            onClick={() => runEval(conversation.conversation_id)}
                            disabled={evalLoading[conversation.conversation_id]}
                            variant="ghost"
                            className="h-6 px-2 text-xs text-slate-500 hover:text-slate-700"
                          >
                            {evalLoading[conversation.conversation_id] ? (
                              <>
                                <Loader2 className="h-3 w-3 animate-spin" />
                                ...
                              </>
                            ) : (
                              <>
                                <RefreshCw className="h-3 w-3" />
                                Re-run
                              </>
                            )}
                          </Button>
                        </div>
                      ) : (
                        <Button
                          onClick={() => runEval(conversation.conversation_id)}
                          disabled={evalLoading[conversation.conversation_id]}
                          variant="ghost"
                          className="border border-slate-300 px-2 py-1 text-xs"
                        >
                          {evalLoading[conversation.conversation_id] ? (
                            <>
                              <Loader2 className="h-3 w-3 animate-spin" />
                              ...
                            </>
                          ) : (
                            <>
                              <Zap className="h-3 w-3" />
                              Eval
                            </>
                          )}
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function AllTagsResult({ result }: { result: AllTagsStatisticsResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">All tags applied on {result.date}</CardTitle>
        <CardDescription>
          One pass across every conversation for the selected day/hour (deduplicated API hits).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto rounded-2xl border border-slate-200">
          <table className="min-w-full divide-y divide-slate-200 text-sm text-slate-700">
            <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3 text-left">Tag</th>
                <th className="px-4 py-3 text-left">Conversations</th>
                <th className="px-4 py-3 text-left">Still tagged</th>
                <th className="px-4 py-3 text-left">Re-tagged</th>
                <th className="px-4 py-3 text-left">Fetch failed</th>
                <th className="px-4 py-3 text-left">% retained</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {result.tag_statistics.map((tagStat) => (
                <tr key={tagStat.tag_name}>
                  <td className="px-4 py-3 font-semibold text-slate-900">{tagStat.tag_name}</td>
                  <td className="px-4 py-3">{tagStat.total_conversations}</td>
                  <td className="px-4 py-3">{tagStat.still_tagged}</td>
                  <td className="px-4 py-3">{tagStat.re_tagged}</td>
                  <td className="px-4 py-3">{tagStat.fetch_failed}</td>
                  <td className="px-4 py-3">
                    <Badge className={STAT_BADGE.success}>
                      {percent(tagStat.still_tagged_percentage)}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function EvalResults({ result }: { result: EvalClassificationResponse }) {
  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-wrap items-center justify-between gap-4 pt-6">
          <div>
            <p className="text-sm font-semibold text-slate-500 uppercase tracking-wide">
              Summary
            </p>
            <p className="text-3xl font-bold text-slate-900">{result.summary.total} Conversations</p>
            <p className="text-sm text-slate-500">
              Accuracy {result.summary.accuracy}% • Exact matches {result.summary.exact_matches}
            </p>
          </div>
          <div className="flex gap-2">
            <Badge className={STAT_BADGE.success}>
              Exact {result.summary.exact_matches}
            </Badge>
            <Badge className={STAT_BADGE.warn}>
              Partial {result.summary.partial_matches}
            </Badge>
            <Badge className={STAT_BADGE.danger}>
              Missed {result.summary.no_matches}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Per-conversation Breakdown</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {result.results.length === 0 && (
            <p className="text-sm text-slate-500">No conversations evaluated.</p>
          )}
          {result.results.map((entry) => (
            <div
              key={entry.conversation_id}
              className="rounded-2xl border border-slate-200 p-4 text-sm text-slate-600"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-400">Conversation</p>
                  <p className="font-mono text-xs text-slate-700">{entry.conversation_id}</p>
                </div>
                <Badge
                  className={
                    entry.exact_match
                      ? STAT_BADGE.success
                      : entry.partial_match
                      ? STAT_BADGE.warn
                      : STAT_BADGE.danger
                  }
                >
                  {entry.exact_match
                    ? "Exact match"
                    : entry.partial_match
                    ? "Partial overlap"
                    : "No overlap"}
                </Badge>
                <span className="text-xs font-semibold text-slate-500">
                  Accuracy {entry.accuracy}%
                </span>
              </div>
              <div className="mt-3 grid gap-3 md:grid-cols-3">
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-400">Predicted tags</p>
                  <TagList tags={entry.predicted_tags} />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-400">Actual tags</p>
                  <TagList tags={entry.actual_tags} />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-wide text-slate-400">Overlap</p>
                  <TagList tags={entry.matching_tags ?? []} placeholder="No matching tags" />
                </div>
              </div>
              {(entry.missing_tags?.length || entry.extra_tags?.length) && (
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  {entry.missing_tags && entry.missing_tags.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wide text-rose-400">
                        Missing (actual not predicted)
                      </p>
                      <TagList tags={entry.missing_tags} />
                    </div>
                  )}
                  {entry.extra_tags && entry.extra_tags.length > 0 && (
                    <div>
                      <p className="text-xs uppercase tracking-wide text-amber-500">
                        Extra (predicted only)
                      </p>
                      <TagList tags={entry.extra_tags} />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

function TagList({ tags, placeholder }: { tags: string[]; placeholder?: string }) {
  if (!tags || tags.length === 0) {
    return <p className="text-xs text-slate-400">{placeholder ?? "No tags"}</p>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {tags.map((tag) => (
        <span key={tag} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
          {tag}
        </span>
      ))}
    </div>
  );
}

function ArchivedConversationsTable({ result }: { result: ArchivedConversationsResponse }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-2xl">
          Archived on {result.date}
          {result.hour !== null && ` (Hour ${result.hour})`}
        </CardTitle>
        <CardDescription>
          {result.total_archived} conversation{result.total_archived !== 1 ? "s" : ""} automatically archived.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {result.conversations.length === 0 && (
          <p className="text-sm text-slate-500">No archived conversations found for this date.</p>
        )}

        {result.conversations.length > 0 && (
          <div className="overflow-x-auto rounded-2xl border border-slate-200">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-3 text-left">Conversation ID</th>
                  <th className="px-4 py-3 text-left">Subject</th>
                  <th className="px-4 py-3 text-left">Sender</th>
                  <th className="px-4 py-3 text-left">Created</th>
                  <th className="px-4 py-3 text-left">Archived</th>
                  <th className="px-4 py-3 text-left">Tags</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 bg-white text-slate-700">
                {result.conversations.map((conv) => (
                  <tr key={conv.conversation_id} className="hover:bg-slate-50">
                    <td className="px-4 py-3 font-mono text-xs">
                      <a
                        href={`https://app.frontapp.com/open/${conv.conversation_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-indigo-600 hover:text-indigo-800 hover:underline"
                      >
                        {conv.conversation_id}
                      </a>
                    </td>
                    <td className="px-4 py-3 max-w-xs truncate">
                      {conv.subject || <span className="text-slate-400">No subject</span>}
                    </td>
                    <td className="px-4 py-3 text-xs">{conv.sender}</td>
                    <td className="px-4 py-3 text-xs">
                      {new Date(conv.created_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {new Date(conv.archived_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3 text-xs">
                      {conv.tags_applied.length > 0 ? (
                        <div className="flex flex-wrap gap-1">
                          {conv.tags_applied.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-700 border border-emerald-200"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-slate-400">No tags</span>
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
