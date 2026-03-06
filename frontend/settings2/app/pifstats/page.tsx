"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Building2,
  Search,
  Calendar,
  Loader2,
  Mail,
  Phone,
  Globe,
  MapPin,
  Users,
  MessageSquare,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Trash2,
  LogOut,
  Eye,
  Sparkles,
  Linkedin,
  Award,
  Briefcase,
  ArrowUpDown,
  Copy,
  Check,
  BarChart2,
} from "lucide-react";

import { ApiError, PifApi } from "@/lib/api";
import type { PifInfoResponse, PifInfoListResponse, ProcessDayResponse, ResearchStatusResponse, OutreachMessageResult, FirmLookupResponse, FirmLookupConversation, FirmLookupCreateResponse, AnalyticsSummary } from "@/lib/types";
import { ResearchModal } from "./ResearchModal";
import { BehavioralSection } from "./BehavioralSection";
import { PipelineSection } from "./PipelineSection";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Header } from "@/components/layout/Header";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

// Helper to check if a string is a valid LinkedIn URL
const isValidLinkedInUrl = (url: string | null | undefined): boolean => {
  if (!url) return false;
  const lower = url.toLowerCase();
  return lower.startsWith("https://linkedin.com") ||
         lower.startsWith("https://www.linkedin.com") ||
         lower.startsWith("http://linkedin.com") ||
         lower.startsWith("http://www.linkedin.com") ||
         lower.startsWith("linkedin.com") ||
         lower.startsWith("www.linkedin.com");
};

// Simple auth for pifstats page only
const PIFSTATS_AUTH_KEY = "pifstats_authenticated";
const VALID_USERNAME = "user";
const VALID_PASSWORD = "user123";

export default function PifListPage() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);
  const [loginUsername, setLoginUsername] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);

  const [user, setUser] = useState<string>("user");
  const [data, setData] = useState<PifInfoListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(20);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<string>("updated_at");
  const [tierFilter, setTierFilter] = useState<string>("");
  const [researchModalFirm, setResearchModalFirm] = useState<PifInfoResponse | null>(null);

  // Analytics summary state
  const [analyticsSummary, setAnalyticsSummary] = useState<AnalyticsSummary | null>(null);
  const [analyticsExpanded, setAnalyticsExpanded] = useState(false);
  const [isBatchAnalyzing, setIsBatchAnalyzing] = useState(false);
  const [isBatchScoring, setIsBatchScoring] = useState(false);
  const [batchMsg, setBatchMsg] = useState<string | null>(null);

  // Process day state
  const [processDate, setProcessDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<ProcessDayResponse | null>(null);


  // Tab state
  const [activeTab, setActiveTab] = useState<"pif" | "lookup" | "outreach" | "outgen">("pif");

  // Outreach state
  const [outreachFirmId, setOutreachFirmId] = useState<string>("");
  const [caseStudyUrl, setCaseStudyUrl] = useState("https://getpossibleminds.com/healthcare-case-study");
  const [clientDescription, setClientDescription] = useState("");
  const [outreachMessages, setOutreachMessages] = useState<OutreachMessageResult[] | null>(null);
  const [isGeneratingOutreach, setIsGeneratingOutreach] = useState(false);
  const [outreachError, setOutreachError] = useState<string | null>(null);

  // Outgen state
  const [outgenFirmId, setOutgenFirmId] = useState<string>("");
  const [outgenCaseStudyUrl, setOutgenCaseStudyUrl] = useState("https://getpossibleminds.com/healthcare-case-study");
  const [outgenInstructions, setOutgenInstructions] = useState("");
  const [outgenMutualApproved, setOutgenMutualApproved] = useState(false);

  // All researched firms (for dropdowns, not paginated)
  const [allResearchedFirms, setAllResearchedFirms] = useState<PifInfoResponse[]>([]);

  // Check if already authenticated on mount
  useEffect(() => {
    const authStatus = localStorage.getItem(PIFSTATS_AUTH_KEY);
    if (authStatus === "true") {
      setIsAuthenticated(true);
    }
    setAuthChecked(true);
  }, []);

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setLoginError(null);

    if (loginUsername === VALID_USERNAME && loginPassword === VALID_PASSWORD) {
      localStorage.setItem(PIFSTATS_AUTH_KEY, "true");
      setIsAuthenticated(true);
      setUser(loginUsername);
    } else {
      setLoginError("Invalid username or password");
    }
  };

  const handleLogout = () => {
    localStorage.removeItem(PIFSTATS_AUTH_KEY);
    setIsAuthenticated(false);
    setLoginUsername("");
    setLoginPassword("");
  };

  const fetchData = useCallback(async () => {
    try {
      const payload = await PifApi.list({
        search: searchTerm || undefined,
        page: currentPage,
        pageSize,
        sortBy: sortBy || undefined,
      });
      setData(payload);
      setError(null);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        // API needs auth - but we handle separately for this page
        const message = err instanceof Error ? err.message : "API authentication required";
        setError(message);
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to load PIF data";
      setError(message);
    }
  }, [searchTerm, currentPage, pageSize, sortBy]);

  const fetchResearchedFirms = useCallback(async () => {
    try {
      // Fetch firms with max page size (100 is the backend limit)
      const payload = await PifApi.list({ pageSize: 100 });
      const researched = payload.items
        .filter((f) => f.research_status === "completed")
        .sort((a, b) => {
          const dateA = a.last_researched_at ? new Date(a.last_researched_at).getTime() : 0;
          const dateB = b.last_researched_at ? new Date(b.last_researched_at).getTime() : 0;
          return dateB - dateA;
        });
      setAllResearchedFirms(researched);
    } catch (err) {
      console.error("Failed to fetch researched firms:", err);
    }
  }, []);

  const fetchAnalytics = useCallback(async () => {
    try {
      const summary = await PifApi.getAnalyticsSummary();
      setAnalyticsSummary(summary);
    } catch {
      // Analytics are optional — don't block the page
    }
  }, []);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      if (!isAuthenticated) {
        setIsLoading(false);
        return;
      }

      try {
        await Promise.all([fetchData(), fetchResearchedFirms(), fetchAnalytics()]);
      } catch (err) {
        if (!mounted) return;
        const message = err instanceof Error ? err.message : "Unexpected error occurred";
        setError(message);
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    if (authChecked) {
      bootstrap();
    }
    return () => {
      mounted = false;
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, authChecked]);

  // Re-fetch when page or sort changes
  useEffect(() => {
    if (!isLoading) {
      fetchData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage, sortBy]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    fetchData();
  };

  const handleAnalyzeAll = async () => {
    setIsBatchAnalyzing(true);
    setBatchMsg(null);
    try {
      const result = await PifApi.analyzeBehaviorBatch();
      setBatchMsg(`Batch analysis queued for ${result.total ?? "all"} firms (task: ${result.task_id})`);
    } catch (err) {
      setBatchMsg(err instanceof Error ? err.message : "Batch analyze failed");
    } finally {
      setIsBatchAnalyzing(false);
    }
  };

  const handleScoreAll = async () => {
    setIsBatchScoring(true);
    setBatchMsg(null);
    try {
      const result = await PifApi.scoreBatch();
      setBatchMsg(`Batch scoring queued (task: ${result.task_id})`);
    } catch (err) {
      setBatchMsg(err instanceof Error ? err.message : "Batch score failed");
    } finally {
      setIsBatchScoring(false);
    }
  };

  const handleProcessDay = async () => {
    setIsProcessing(true);
    setProcessResult(null);
    setError(null);

    try {
      const result = await PifApi.processDay(processDate);
      setProcessResult(result);
      // Refresh the list after processing
      await fetchData();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to process day";
      setError(message);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDelete = async (pifId: string, firmName: string) => {
    if (!confirm(`Are you sure you want to delete "${firmName}"?`)) {
      return;
    }

    try {
      await PifApi.delete(pifId);
      await fetchData();
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to delete";
      setError(message);
    }
  };

  const toggleExpand = (id: string) => {
    setExpandedId(expandedId === id ? null : id);
  };

  // Show loading while checking auth
  if (!authChecked) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16 bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="rounded-3xl border border-slate-200/80 bg-white/80 px-10 py-12 text-center shadow-2xl"
        >
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-indigo-600" />
          <p className="mt-4 text-base font-medium text-slate-500">Loading...</p>
        </motion.div>
      </section>
    );
  }

  // Show login form if not authenticated
  if (!isAuthenticated) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16 bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="w-full max-w-md"
        >
          <Card className="rounded-2xl border border-slate-200/70 bg-white/90 shadow-xl">
            <CardContent className="pt-6">
              <form onSubmit={handleLogin} className="space-y-4">
                {loginError && (
                  <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                    {loginError}
                  </div>
                )}
                <div className="space-y-2">
                  <label htmlFor="username" className="text-sm font-medium text-slate-700">
                    Username
                  </label>
                  <input
                    type="text"
                    id="username"
                    value={loginUsername}
                    onChange={(e) => setLoginUsername(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    placeholder="Enter username"
                    autoComplete="username"
                    required
                  />
                </div>
                <div className="space-y-2">
                  <label htmlFor="password" className="text-sm font-medium text-slate-700">
                    Password
                  </label>
                  <input
                    type="password"
                    id="password"
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    className="w-full rounded-lg border border-slate-200 px-4 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    placeholder="Enter password"
                    autoComplete="current-password"
                    required
                  />
                </div>
                <Button type="submit" className="w-full">
                  Sign In
                </Button>
              </form>
            </CardContent>
          </Card>
        </motion.div>
      </section>
    );
  }

  if (isLoading) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16 bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="rounded-3xl border border-slate-200/80 bg-white/80 px-10 py-12 text-center shadow-2xl"
        >
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-indigo-600" />
          <p className="mt-4 text-base font-medium text-slate-500">Loading...</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header user={user} currentPage={{ label: "PIF Stats", icon: "🏢" }} extraAction={
        <Button
          variant="ghost"
          onClick={handleLogout}
          className="text-slate-600 hover:text-slate-800 px-3 py-1.5 text-sm"
        >
          <LogOut className="h-4 w-4 mr-1" />
          Logout
        </Button>
      } />

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10">
        {/* Tab Navigation */}
        <div className="flex gap-1 rounded-lg bg-slate-100 p-1 w-fit">
          <button
            onClick={() => setActiveTab("pif")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "pif"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Building2 className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />
            PIF Data
          </button>
          <button
            onClick={() => setActiveTab("lookup")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "lookup"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Search className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />
            Lookup
          </button>
          <button
            onClick={() => setActiveTab("outreach")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "outreach"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <MessageSquare className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />
            Outreach
          </button>
          <button
            onClick={() => setActiveTab("outgen")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "outgen"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Copy className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />
            OutGen
          </button>
        </div>

        {activeTab === "pif" && (
          <>
            {/* Analytics Summary */}
            <motion.section
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <div className="rounded-2xl border border-slate-200/70 bg-white/90 px-5 py-4">
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    className="flex items-center gap-2 text-sm font-medium text-slate-700"
                    onClick={() => {
                      setAnalyticsExpanded(!analyticsExpanded);
                      if (!analyticsSummary) fetchAnalytics();
                    }}
                  >
                    <BarChart2 className="h-4 w-4 text-indigo-500" />
                    Analytics
                    {analyticsExpanded ? (
                      <ChevronUp className="h-4 w-4 text-slate-400" />
                    ) : (
                      <ChevronDown className="h-4 w-4 text-slate-400" />
                    )}
                  </button>

                  {analyticsSummary && !analyticsExpanded && (
                    <div className="flex flex-wrap gap-2">
                      {(["A","B","C","D"] as const).map((tier) => {
                        const count = analyticsSummary.firms_by_tier[tier] ?? 0;
                        const colors = { A: "emerald", B: "indigo", C: "amber", D: "slate" };
                        const c = colors[tier];
                        return (
                          <span key={tier} className={`rounded-full bg-${c}-100 text-${c}-700 px-2.5 py-0.5 text-xs font-medium`}>
                            {tier}: {count}
                          </span>
                        );
                      })}
                      {analyticsSummary.firms_needing_recontact > 0 && (
                        <span className="rounded-full bg-rose-100 text-rose-700 px-2.5 py-0.5 text-xs font-medium">
                          {analyticsSummary.firms_needing_recontact} need recontact
                        </span>
                      )}
                    </div>
                  )}

                  <div className="ml-auto flex gap-2">
                    <Button
                      variant="ghost"
                      onClick={handleAnalyzeAll}
                      disabled={isBatchAnalyzing}
                      className="h-8 text-xs text-indigo-600 hover:bg-indigo-50"
                    >
                      {isBatchAnalyzing ? (
                        <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Analyzing...</>
                      ) : "Analyze All"}
                    </Button>
                    <Button
                      variant="ghost"
                      onClick={handleScoreAll}
                      disabled={isBatchScoring}
                      className="h-8 text-xs text-purple-600 hover:bg-purple-50"
                    >
                      {isBatchScoring ? (
                        <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Scoring...</>
                      ) : "Score All"}
                    </Button>
                  </div>
                </div>

                {batchMsg && (
                  <div className="mt-2 text-xs text-emerald-600">{batchMsg}</div>
                )}

                {analyticsExpanded && analyticsSummary && (
                  <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4 border-t border-slate-100 pt-4">
                    <div>
                      <p className="text-xs text-slate-500 mb-2">Firms by Tier</p>
                      <div className="space-y-1">
                        {(["A","B","C","D"] as const).map((tier) => {
                          const count = analyticsSummary.firms_by_tier[tier] ?? 0;
                          const colors = { A: "bg-emerald-400", B: "bg-indigo-400", C: "bg-amber-400", D: "bg-slate-400" };
                          return (
                            <div key={tier} className="flex items-center gap-2">
                              <span className={`w-2 h-2 rounded-full ${colors[tier]}`} />
                              <span className="text-xs text-slate-700">Tier {tier}</span>
                              <span className="ml-auto text-xs font-medium text-slate-600">{count}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-2">Top Pain Points</p>
                      <div className="space-y-1">
                        {analyticsSummary.top_pain_points.slice(0, 3).map((p) => (
                          <div key={p.pain_point} className="flex items-center gap-1">
                            <span className="text-xs text-slate-600 truncate">{p.pain_point.replace(/_/g, " ")}</span>
                            <span className="ml-auto text-xs text-slate-400">{p.count}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-2">Pipeline Funnel</p>
                      <div className="space-y-1">
                        {Object.entries(analyticsSummary.pipeline_funnel).map(([status, count]) => (
                          <div key={status} className="flex items-center gap-1">
                            <span className="text-xs text-slate-600">{status.replace(/_/g, " ")}</span>
                            <span className="ml-auto text-xs text-slate-400">{count}</span>
                          </div>
                        ))}
                        {Object.keys(analyticsSummary.pipeline_funnel).length === 0 && (
                          <span className="text-xs text-slate-400">No outreach yet</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <p className="text-xs text-slate-500 mb-2">Activity</p>
                      <div className="space-y-1">
                        <div className="text-xs text-slate-600">
                          Contacted last 30d: <span className="font-medium">{analyticsSummary.firms_contacted_last_30_days}</span>
                        </div>
                        <div className="text-xs text-rose-600">
                          Need recontact: <span className="font-medium">{analyticsSummary.firms_needing_recontact}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </motion.section>

            {/* Process Day Card */}
            <motion.section
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
                <CardHeader className="pb-4">
                  <CardTitle className="flex items-center gap-3 text-xl">
                    <Calendar className="h-5 w-5 text-indigo-600" />
                    Process Day&apos;s Conversations
                  </CardTitle>
                  <CardDescription>
                    Extract firm information from all conversations on a specific date
                  </CardDescription>
                </CardHeader>
            <CardContent>
              <div className="flex flex-wrap items-end gap-4">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="processDate" className="text-sm font-medium text-slate-700">
                    Select Date
                  </label>
                  <input
                    type="date"
                    id="processDate"
                    value={processDate}
                    onChange={(e) => setProcessDate(e.target.value)}
                    className="rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
                <Button
                  onClick={handleProcessDay}
                  disabled={isProcessing}
                  className="flex items-center gap-2"
                >
                  {isProcessing ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <Building2 className="h-4 w-4" />
                      Process Day
                    </>
                  )}
                </Button>
              </div>

              {processResult && (
                <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <h4 className="font-medium text-emerald-800">Processing Complete</h4>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-sm text-emerald-700 sm:grid-cols-3 md:grid-cols-6">
                    <div>
                      <span className="text-emerald-600">Total:</span>{" "}
                      {processResult.total_conversations}
                    </div>
                    <div>
                      <span className="text-emerald-600">Processed:</span>{" "}
                      {processResult.processed}
                    </div>
                    <div>
                      <span className="text-emerald-600">Firms Found:</span>{" "}
                      {processResult.firms_found}
                    </div>
                    <div>
                      <span className="text-emerald-600">Created:</span>{" "}
                      {processResult.firms_created}
                    </div>
                    <div>
                      <span className="text-emerald-600">Updated:</span>{" "}
                      {processResult.firms_updated}
                    </div>
                    <div>
                      <span className="text-emerald-600">Errors:</span>{" "}
                      {processResult.errors.length}
                    </div>
                  </div>
                  {processResult.errors.length > 0 && (
                    <div className="mt-2 text-xs text-rose-600">
                      {processResult.errors.slice(0, 3).map((err, i) => (
                        <div key={i}>{err}</div>
                      ))}
                      {processResult.errors.length > 3 && (
                        <div>...and {processResult.errors.length - 3} more errors</div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </motion.section>

          {/* Search and List Card */}
          <motion.section
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...easing, delay: 0.1 }}
          >
            <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-3 text-xl">
                  <Building2 className="h-5 w-5 text-indigo-600" />
                  Personal Injury Firms
                  {data && (
                    <Badge className="ml-2 bg-slate-100 text-slate-600">
                      {data.total} firms
                    </Badge>
                  )}
                </CardTitle>
                <CardDescription>
                  View and search extracted firm information from email conversations
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {error && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                    {error}
                  </div>
                )}

                {/* Search Form and Sort */}
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <form onSubmit={handleSearch} className="flex gap-2 flex-1">
                    <div className="relative flex-1">
                      <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                      <input
                        type="text"
                        placeholder="Search by firm name, email, or website..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="w-full rounded-lg border border-slate-200 py-2 pl-10 pr-4 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                      />
                    </div>
                    <Button type="submit">Search</Button>
                  </form>

                  {/* Sort + Tier Filter */}
                  <div className="flex items-center gap-2">
                    <select
                      value={tierFilter}
                      onChange={(e) => {
                        setTierFilter(e.target.value);
                        setCurrentPage(1);
                      }}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="">All Tiers</option>
                      <option value="A">Tier A</option>
                      <option value="B">Tier B</option>
                      <option value="C">Tier C</option>
                      <option value="D">Tier D</option>
                    </select>
                    <ArrowUpDown className="h-4 w-4 text-slate-400" />
                    <select
                      value={sortBy}
                      onChange={(e) => {
                        setSortBy(e.target.value);
                        setCurrentPage(1);
                      }}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                    >
                      <option value="updated_at">Recently Updated</option>
                      <option value="conversation_count">Most Conversations</option>
                      <option value="firm_name">Firm Name (A-Z)</option>
                    </select>
                  </div>
                </div>

                {/* Firms List */}
                {data && data.items.length > 0 ? (
                  <div className="space-y-3">
                    {data.items.map((firm) => (
                      <FirmCard
                        key={firm.id}
                        firm={firm}
                        isExpanded={expandedId === firm.id}
                        onToggle={() => toggleExpand(firm.id)}
                        onDelete={() => handleDelete(firm.id, firm.firm_name)}
                        onViewResearch={() => setResearchModalFirm(firm)}
                        onResearchComplete={(result) => {
                          // Update the firm in the list with research data
                          setData((prev) => {
                            if (!prev) return prev;
                            return {
                              ...prev,
                              items: prev.items.map((f) =>
                                f.id === result.pif_id
                                  ? {
                                      ...f,
                                      leadership: result.leadership || null,
                                      research_data: result.research_data || null,
                                      research_status: result.status,
                                      last_researched_at: new Date().toISOString(),
                                    }
                                  : f
                              ),
                            };
                          });
                          // Refresh the researched firms list for dropdowns
                          fetchResearchedFirms();
                        }}
                      />
                    ))}
                  </div>
                ) : (
                  <div className="py-12 text-center text-slate-500">
                    {searchTerm ? "No firms found matching your search" : "No firms extracted yet"}
                  </div>
                )}

                {/* Pagination */}
                {data && data.total_pages > 1 && (
                  <div className="flex items-center justify-between border-t border-slate-100 pt-4">
                    <div className="text-sm text-slate-500">
                      Page {data.page} of {data.total_pages}
                    </div>
                    <div className="flex gap-2">
                      <Button
                        variant="ghost"
                        onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        disabled={currentPage === 1}
                      >
                        Previous
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={() => setCurrentPage((p) => Math.min(data.total_pages, p + 1))}
                        disabled={currentPage === data.total_pages}
                      >
                        Next
                      </Button>
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.section>
        </>
        )}

        {activeTab === "lookup" && (
          <FirmLookupTab
            onFirmCreated={() => {
              fetchData();
              fetchResearchedFirms();
            }}
          />
        )}

        {activeTab === "outreach" && (
          <OutreachTab
            researchedFirms={allResearchedFirms}
            outreachFirmId={outreachFirmId}
            setOutreachFirmId={setOutreachFirmId}
            caseStudyUrl={caseStudyUrl}
            setCaseStudyUrl={setCaseStudyUrl}
            clientDescription={clientDescription}
            setClientDescription={setClientDescription}
            outreachMessages={outreachMessages}
            setOutreachMessages={setOutreachMessages}
            isGeneratingOutreach={isGeneratingOutreach}
            setIsGeneratingOutreach={setIsGeneratingOutreach}
            outreachError={outreachError}
            setOutreachError={setOutreachError}
          />
        )}

        {activeTab === "outgen" && (
          <OutgenTab
            researchedFirms={allResearchedFirms}
            outgenFirmId={outgenFirmId}
            setOutgenFirmId={setOutgenFirmId}
            outgenCaseStudyUrl={outgenCaseStudyUrl}
            setOutgenCaseStudyUrl={setOutgenCaseStudyUrl}
            outgenInstructions={outgenInstructions}
            setOutgenInstructions={setOutgenInstructions}
            outgenMutualApproved={outgenMutualApproved}
            setOutgenMutualApproved={setOutgenMutualApproved}
          />
        )}

      </main>

      {/* Research Modal */}
      {researchModalFirm && (
        <ResearchModal
          firm={researchModalFirm}
          isOpen={!!researchModalFirm}
          onClose={() => setResearchModalFirm(null)}
        />
      )}
    </div>
  );
}

function FirmCard({
  firm,
  isExpanded,
  onToggle,
  onDelete,
  onViewResearch,
  onResearchComplete,
}: {
  firm: PifInfoResponse;
  isExpanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onViewResearch: () => void;
  onResearchComplete: (result: ResearchStatusResponse) => void;
}) {
  const [isResearching, setIsResearching] = useState(false);
  const [researchError, setResearchError] = useState<string | null>(null);
  const [researchStatus, setResearchStatus] = useState<string | null>(null);

  const pollResearchStatus = async (taskId: string) => {
    const maxAttempts = 120; // 10 minutes max (5 second intervals)
    let attempts = 0;

    const poll = async (): Promise<void> => {
      attempts++;
      try {
        const status = await PifApi.getResearchStatus(taskId);
        setResearchStatus(status.status);

        if (status.status === "completed") {
          setIsResearching(false);
          onResearchComplete(status);
        } else if (status.status === "failed") {
          setIsResearching(false);
          setResearchError(status.message || "Research failed");
        } else if (attempts < maxAttempts) {
          // Continue polling
          setTimeout(poll, 5000);
        } else {
          setIsResearching(false);
          setResearchError("Research timed out");
        }
      } catch (err) {
        setIsResearching(false);
        const message = err instanceof Error ? err.message : "Failed to check research status";
        setResearchError(message);
      }
    };

    await poll();
  };

  const handleResearch = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsResearching(true);
    setResearchError(null);
    setResearchStatus("starting");

    try {
      const result = await PifApi.startResearch(firm.id);
      setResearchStatus("queued");
      // Start polling for status
      await pollResearchStatus(result.task_id);
    } catch (err) {
      setIsResearching(false);
      const message = err instanceof Error ? err.message : "Failed to start research";
      setResearchError(message);
    }
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white transition-shadow hover:shadow-md">
      {/* Header - Always visible */}
      <div
        className="flex cursor-pointer items-center justify-between p-4"
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50">
            <Building2 className="h-5 w-5 text-indigo-600" />
          </div>
          <div>
            <h3 className="font-semibold text-slate-800">{firm.firm_name}</h3>
            <div className="flex flex-wrap gap-2 text-xs text-slate-500">
              {firm.website && (
                <span className="flex items-center gap-1">
                  <Globe className="h-3 w-3" />
                  {firm.website}
                </span>
              )}
              <span className="flex items-center gap-1">
                <MessageSquare className="h-3 w-3" />
                {firm.conversation_ids.length} conversations
              </span>
              {firm.research_status === "completed" && (
                <span className="flex items-center gap-1 text-emerald-600">
                  <Sparkles className="h-3 w-3" />
                  Researched
                </span>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge className="bg-slate-100 text-slate-600">
            {firm.emails.length} emails
          </Badge>
          <Badge className="bg-slate-100 text-slate-600">
            {firm.phones.length} phones
          </Badge>
          {firm.icp_tier && (() => {
            const tierColors: Record<string, string> = { A: "bg-emerald-100 text-emerald-700", B: "bg-indigo-100 text-indigo-700", C: "bg-amber-100 text-amber-700", D: "bg-slate-100 text-slate-600" };
            return (
              <Badge className={tierColors[firm.icp_tier] ?? "bg-slate-100 text-slate-600"}>
                Tier {firm.icp_tier} · {firm.icp_score}
              </Badge>
            );
          })()}
          {firm.leadership && firm.leadership.length > 0 && (
            <Badge className="bg-emerald-100 text-emerald-700">
              {firm.leadership.length} leaders
            </Badge>
          )}
          {firm.research_status === "completed" && (
            <Button
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                onViewResearch();
              }}
              className="h-8 px-2 text-sm text-indigo-600 hover:bg-indigo-50 hover:text-indigo-700"
            >
              <Eye className="h-4 w-4 mr-1" />
              View
            </Button>
          )}
          <Button
            variant="ghost"
            onClick={handleResearch}
            disabled={isResearching}
            className="h-8 px-2 text-sm text-amber-600 hover:bg-amber-50 hover:text-amber-700"
          >
            {isResearching ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                {researchStatus === "queued" && "Queued..."}
                {researchStatus === "in_progress" && "Researching..."}
                {researchStatus === "starting" && "Starting..."}
                {!researchStatus && "Researching..."}
              </>
            ) : (
              <>
                <Sparkles className="mr-2 h-4 w-4" />
                {firm.research_status === "completed" ? "Re-Research" : "Research"}
              </>
            )}
          </Button>
          {isExpanded ? (
            <ChevronUp className="h-5 w-5 text-slate-400" />
          ) : (
            <ChevronDown className="h-5 w-5 text-slate-400" />
          )}
        </div>
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-slate-100 p-4">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Emails */}
            {firm.emails.length > 0 && (
              <div>
                <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Mail className="h-4 w-4 text-indigo-500" />
                  Email Addresses
                </h4>
                <div className="space-y-1">
                  {firm.emails.map((email, i) => (
                    <div key={i} className="text-sm text-slate-600">
                      <a
                        href={`mailto:${email}`}
                        className="hover:text-indigo-600 hover:underline"
                      >
                        {email}
                      </a>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Phones */}
            {firm.phones.length > 0 && (
              <div>
                <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Phone className="h-4 w-4 text-indigo-500" />
                  Phone Numbers
                </h4>
                <div className="space-y-1">
                  {firm.phones.map((phone, i) => (
                    <div key={i} className="text-sm text-slate-600">
                      {phone}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Fax */}
            {firm.fax && (
              <div>
                <h4 className="mb-2 text-sm font-medium text-slate-700">Fax</h4>
                <div className="text-sm text-slate-600">{firm.fax}</div>
              </div>
            )}

            {/* Website */}
            {firm.website && (
              <div>
                <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Globe className="h-4 w-4 text-indigo-500" />
                  Website
                </h4>
                <a
                  href={firm.website.startsWith("http") ? firm.website : `https://${firm.website}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 text-sm text-indigo-600 hover:underline"
                >
                  {firm.website}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}

            {/* Addresses */}
            {firm.addresses.length > 0 && (
              <div className="md:col-span-2">
                <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <MapPin className="h-4 w-4 text-indigo-500" />
                  Addresses
                </h4>
                <div className="space-y-1">
                  {firm.addresses.map((address, i) => (
                    <div key={i} className="text-sm text-slate-600">
                      {address}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Contacts */}
            {firm.contacts.length > 0 && (
              <div className="md:col-span-2">
                <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Users className="h-4 w-4 text-indigo-500" />
                  Contacts ({firm.contacts.length})
                </h4>
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {firm.contacts.map((contact, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-slate-100 bg-slate-50 p-2 text-sm"
                    >
                      <div className="font-medium text-slate-800">
                        {contact.name || "Unknown"}
                      </div>
                      {contact.title && (
                        <div className="text-xs text-slate-500">{contact.title}</div>
                      )}
                      {contact.email && (
                        <div className="text-xs text-slate-600">{contact.email}</div>
                      )}
                      {contact.phone && (
                        <div className="text-xs text-slate-600">
                          {contact.phone}
                          {contact.extension && ` ext. ${contact.extension}`}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Conversation IDs */}
            <div className="md:col-span-2">
              <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                <MessageSquare className="h-4 w-4 text-indigo-500" />
                Conversations ({firm.conversation_ids.length})
              </h4>
              <div className="flex flex-wrap gap-1">
                {firm.conversation_ids.slice(0, 10).map((convId, i) => (
                  <a
                    key={i}
                    href={`https://app.frontapp.com/open/${convId}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 hover:bg-indigo-100 hover:text-indigo-700"
                  >
                    {convId}
                    <ExternalLink className="h-2.5 w-2.5" />
                  </a>
                ))}
                {firm.conversation_ids.length > 10 && (
                  <span className="px-2 py-0.5 text-xs text-slate-400">
                    +{firm.conversation_ids.length - 10} more
                  </span>
                )}
              </div>
            </div>

            {/* Notes */}
            {firm.extraction_notes && (
              <div className="md:col-span-2">
                <h4 className="mb-2 text-sm font-medium text-slate-700">
                  Extraction Notes
                </h4>
                <div className="text-sm text-slate-600">{firm.extraction_notes}</div>
              </div>
            )}

            {/* Behavioral Intelligence */}
            <BehavioralSection
              firm={firm}
              onAnalyzeComplete={() => {
                /* parent could refresh firm data here */
              }}
            />

            {/* Outreach Pipeline */}
            <PipelineSection pifId={firm.id} />

            {/* Leadership (from research) */}
            {firm.leadership && firm.leadership.length > 0 && (
              <div className="md:col-span-2">
                <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                  <Sparkles className="h-4 w-4 text-amber-500" />
                  Leadership Team ({firm.leadership.length})
                </h4>
                <div className="grid gap-3 sm:grid-cols-2">
                  {firm.leadership.map((leader, i) => (
                    <div
                      key={i}
                      className="rounded-lg border border-amber-100 bg-amber-50/50 p-3 text-sm"
                    >
                      <div className="font-medium text-slate-800">
                        {leader.name}
                      </div>
                      {leader.title && (
                        <div className="text-xs text-slate-600">{leader.title}</div>
                      )}
                      <div className="mt-2 space-y-1">
                        {leader.email && (
                          <div className="flex items-center gap-1.5 text-xs text-slate-600">
                            <Mail className="h-3 w-3 text-indigo-400" />
                            <a href={`mailto:${leader.email}`} className="hover:text-indigo-600 hover:underline">
                              {leader.email}
                            </a>
                          </div>
                        )}
                        {leader.phone && (
                          <div className="flex items-center gap-1.5 text-xs text-slate-600">
                            <Phone className="h-3 w-3 text-indigo-400" />
                            {leader.phone}
                          </div>
                        )}
                        {isValidLinkedInUrl(leader.linkedin) ? (
                          <div className="flex items-center gap-1.5 text-xs">
                            <Linkedin className="h-3 w-3 text-blue-600" />
                            <a
                              href={leader.linkedin?.startsWith("http") ? leader.linkedin : `https://${leader.linkedin}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline"
                            >
                              LinkedIn Profile
                            </a>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-xs text-slate-400">
                            <Linkedin className="h-3 w-3" />
                            <span>LinkedIn not found</span>
                          </div>
                        )}
                      </div>
                      {leader.bio && (
                        <div className="mt-2 text-xs text-slate-500 line-clamp-3">
                          {leader.bio}
                        </div>
                      )}
                      {/* Enriched data from LinkedIn */}
                      {leader.bar_admissions && leader.bar_admissions.length > 0 && (
                        <div className="mt-2">
                          <div className="text-xs font-medium text-slate-500">Bar Admissions</div>
                          <div className="text-xs text-slate-600">{leader.bar_admissions.join(", ")}</div>
                        </div>
                      )}
                      {leader.education && leader.education.length > 0 && (
                        <div className="mt-2">
                          <div className="text-xs font-medium text-slate-500">Education</div>
                          <div className="text-xs text-slate-600">
                            {leader.education.slice(0, 2).map((edu, j) => (
                              <div key={j}>{edu}</div>
                            ))}
                          </div>
                        </div>
                      )}
                      {leader.skills && leader.skills.length > 0 && (
                        <div className="mt-2">
                          <div className="flex flex-wrap gap-1">
                            {leader.skills.slice(0, 4).map((skill, j) => (
                              <Badge key={j} className="bg-slate-100 text-slate-600 text-xs py-0">
                                {skill}
                              </Badge>
                            ))}
                            {leader.skills.length > 4 && (
                              <span className="text-xs text-slate-400">+{leader.skills.length - 4}</span>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Research Data */}
            {firm.research_data && (
              <>
                {/* Practice Areas */}
                {firm.research_data.practice_areas && firm.research_data.practice_areas.length > 0 && (
                  <div className="md:col-span-2">
                    <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                      <Briefcase className="h-4 w-4 text-indigo-500" />
                      Practice Areas
                    </h4>
                    <div className="flex flex-wrap gap-1.5">
                      {firm.research_data.practice_areas.map((area, i) => (
                        <Badge key={i} className="bg-indigo-50 text-indigo-700">
                          {area}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {/* Firm Info */}
                <div className="grid gap-4 md:col-span-2 md:grid-cols-3">
                  {firm.research_data.founded_year && (
                    <div>
                      <h4 className="text-xs font-medium text-slate-500">Founded</h4>
                      <div className="text-sm font-medium text-slate-700">{firm.research_data.founded_year}</div>
                    </div>
                  )}
                  {firm.research_data.firm_size && (
                    <div>
                      <h4 className="text-xs font-medium text-slate-500">Firm Size</h4>
                      <div className="text-sm font-medium text-slate-700">{firm.research_data.firm_size}</div>
                    </div>
                  )}
                  {firm.research_data.office_locations && firm.research_data.office_locations.length > 0 && (
                    <div>
                      <h4 className="text-xs font-medium text-slate-500">Office Locations</h4>
                      <div className="text-sm text-slate-700">{firm.research_data.office_locations.join(", ")}</div>
                    </div>
                  )}
                </div>

                {/* Awards */}
                {firm.research_data.awards_recognition && firm.research_data.awards_recognition.length > 0 && (
                  <div className="md:col-span-2">
                    <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                      <Award className="h-4 w-4 text-amber-500" />
                      Awards & Recognition
                    </h4>
                    <div className="space-y-1">
                      {firm.research_data.awards_recognition.slice(0, 5).map((award, i) => (
                        <div key={i} className="text-sm text-slate-600">• {award}</div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Notable Cases */}
                {firm.research_data.notable_cases && firm.research_data.notable_cases.length > 0 && (
                  <div className="md:col-span-2">
                    <h4 className="mb-2 text-sm font-medium text-slate-700">Notable Cases</h4>
                    <div className="space-y-1">
                      {firm.research_data.notable_cases.slice(0, 5).map((caseItem, i) => (
                        <div key={i} className="text-sm text-slate-600">• {caseItem}</div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Social Media */}
                {firm.research_data.social_media && Object.keys(firm.research_data.social_media).length > 0 && (
                  <div>
                    <h4 className="mb-2 text-sm font-medium text-slate-700">Social Media</h4>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(firm.research_data.social_media).map(([platform, url]) => (
                        <a
                          key={platform}
                          href={url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-1 text-xs text-slate-600 hover:bg-indigo-100 hover:text-indigo-700"
                        >
                          {platform}
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {/* Sources */}
                {firm.research_data.sources && firm.research_data.sources.length > 0 && (
                  <div className="md:col-span-2">
                    <h4 className="mb-2 text-sm font-medium text-slate-500">Research Sources</h4>
                    <div className="flex flex-wrap gap-1">
                      {firm.research_data.sources.slice(0, 5).map((source, i) => (
                        <a
                          key={i}
                          href={source}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded bg-slate-50 px-2 py-0.5 text-xs text-slate-500 hover:bg-slate-100 hover:text-slate-700"
                        >
                          Source {i + 1}
                          <ExternalLink className="h-2.5 w-2.5" />
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Research Error */}
          {researchError && (
            <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm text-rose-600">
              {researchError}
            </div>
          )}

          {/* Actions */}
          <div className="mt-4 flex justify-end border-t border-slate-100 pt-4">
            <Button
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </Button>
          </div>

          {/* Timestamps */}
          <div className="mt-2 text-xs text-slate-400">
            Created: {new Date(firm.created_at).toLocaleString()} | Updated:{" "}
            {new Date(firm.updated_at).toLocaleString()}
          </div>
        </div>
      )}
    </div>
  );
}

function CopyButton({ text, label }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <button
      onClick={handleCopy}
      className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-600 hover:bg-slate-50 transition-colors"
      title={label || "Copy to clipboard"}
    >
      {copied ? (
        <>
          <Check className="h-3 w-3 text-emerald-500" />
          Copied
        </>
      ) : (
        <>
          <Copy className="h-3 w-3" />
          {label || "Copy"}
        </>
      )}
    </button>
  );
}

function FirmLookupTab({
  onFirmCreated,
}: {
  onFirmCreated: () => void;
}) {
  const [firmName, setFirmName] = useState("");
  const [website, setWebsite] = useState("");
  const [emailField, setEmailField] = useState("");
  const [phone, setPhone] = useState("");
  const [contactName, setContactName] = useState("");

  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [lookupResult, setLookupResult] = useState<FirmLookupResponse | null>(null);

  // Selected conversations for association
  const [selectedConvIds, setSelectedConvIds] = useState<Set<string>>(new Set());

  // Creation state
  const [isCreating, setIsCreating] = useState(false);
  const [createResult, setCreateResult] = useState<FirmLookupCreateResponse | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  // Research polling state
  const [isResearching, setIsResearching] = useState(false);
  const [researchStatus, setResearchStatus] = useState<string | null>(null);
  const [researchedFirm, setResearchedFirm] = useState<PifInfoResponse | null>(null);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!firmName.trim()) return;

    setIsSearching(true);
    setSearchError(null);
    setLookupResult(null);
    setSelectedConvIds(new Set());
    setCreateResult(null);
    setCreateError(null);
    setResearchedFirm(null);

    try {
      const result = await PifApi.firmLookup({
        firm_name: firmName.trim(),
        website: website.trim() || undefined,
        email: emailField.trim() || undefined,
        phone: phone.trim() || undefined,
        contact_name: contactName.trim() || undefined,
      });
      setLookupResult(result);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Search failed";
      setSearchError(message);
    } finally {
      setIsSearching(false);
    }
  };

  const toggleConversation = (convId: string) => {
    setSelectedConvIds((prev) => {
      const next = new Set(prev);
      if (next.has(convId)) {
        next.delete(convId);
      } else {
        next.add(convId);
      }
      return next;
    });
  };

  const selectAllConversations = () => {
    if (!lookupResult) return;
    const allIds = lookupResult.conversations.map((c) => c.conversation_id);
    setSelectedConvIds(new Set(allIds));
  };

  const deselectAllConversations = () => {
    setSelectedConvIds(new Set());
  };

  const pollResearchStatus = async (taskId: string) => {
    const maxAttempts = 120;
    let attempts = 0;

    const poll = async (): Promise<void> => {
      attempts++;
      try {
        const status = await PifApi.getResearchStatus(taskId);
        setResearchStatus(status.status);

        if (status.status === "completed") {
          setIsResearching(false);
          // Fetch the updated firm
          if (status.pif_id && status.pif_id !== "00000000-0000-0000-0000-000000000000") {
            try {
              const updatedFirm = await PifApi.get(status.pif_id);
              setResearchedFirm(updatedFirm);
            } catch {
              // Ignore fetch error
            }
          }
          onFirmCreated();
        } else if (status.status === "failed") {
          setIsResearching(false);
          setCreateError(status.message || "Research failed");
        } else if (attempts < maxAttempts) {
          setTimeout(poll, 5000);
        } else {
          setIsResearching(false);
          setCreateError("Research timed out");
        }
      } catch (err) {
        setIsResearching(false);
        const message = err instanceof Error ? err.message : "Failed to check research status";
        setCreateError(message);
      }
    };

    await poll();
  };

  const handleCreate = async (startResearch: boolean) => {
    if (!firmName.trim()) return;

    setIsCreating(true);
    setCreateError(null);
    setCreateResult(null);

    try {
      const result = await PifApi.firmLookupCreate({
        firm_name: firmName.trim(),
        website: website.trim() || undefined,
        email: emailField.trim() || undefined,
        phone: phone.trim() || undefined,
        contact_name: contactName.trim() || undefined,
        selected_conversation_ids: Array.from(selectedConvIds),
        start_research: startResearch,
      });
      setCreateResult(result);
      onFirmCreated();

      // If research was started, poll for status
      if (result.task_id) {
        setIsResearching(true);
        setResearchStatus("queued");
        await pollResearchStatus(result.task_id);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to create firm";
      setCreateError(message);
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={easing}
      className="space-y-6"
    >
      {/* Search Form */}
      <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-3 text-xl">
            <Search className="h-5 w-5 text-indigo-600" />
            Firm Lookup
          </CardTitle>
          <CardDescription>
            Search for a firm across local database and Front conversations
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSearch} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-1.5 sm:col-span-2">
                <label htmlFor="lookup-firm-name" className="text-sm font-medium text-slate-700">
                  Firm Name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  id="lookup-firm-name"
                  value={firmName}
                  onChange={(e) => setFirmName(e.target.value)}
                  placeholder="Enter firm name..."
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  required
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="lookup-website" className="text-sm font-medium text-slate-700">
                  Website
                </label>
                <input
                  type="text"
                  id="lookup-website"
                  value={website}
                  onChange={(e) => setWebsite(e.target.value)}
                  placeholder="example.com"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="lookup-email" className="text-sm font-medium text-slate-700">
                  Email
                </label>
                <input
                  type="email"
                  id="lookup-email"
                  value={emailField}
                  onChange={(e) => setEmailField(e.target.value)}
                  placeholder="contact@example.com"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="lookup-phone" className="text-sm font-medium text-slate-700">
                  Phone
                </label>
                <input
                  type="tel"
                  id="lookup-phone"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="(555) 123-4567"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="space-y-1.5">
                <label htmlFor="lookup-contact" className="text-sm font-medium text-slate-700">
                  Contact Name
                </label>
                <input
                  type="text"
                  id="lookup-contact"
                  value={contactName}
                  onChange={(e) => setContactName(e.target.value)}
                  placeholder="John Doe"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            <Button type="submit" disabled={isSearching || !firmName.trim()} className="flex items-center gap-2">
              {isSearching ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Searching...
                </>
              ) : (
                <>
                  <Search className="h-4 w-4" />
                  Search
                </>
              )}
            </Button>
          </form>

          {searchError && (
            <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
              {searchError}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      {lookupResult && (
        <>
          {/* Matching Existing Firms */}
          {lookupResult.matching_firms.length > 0 && (
            <Card className="rounded-2xl border border-amber-200/70 bg-amber-50/30">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3 text-lg">
                  <Building2 className="h-5 w-5 text-amber-600" />
                  Existing Firms Found
                  <Badge className="bg-amber-100 text-amber-700">
                    {lookupResult.matching_firms.length}
                  </Badge>
                </CardTitle>
                <CardDescription>
                  These firms already exist in the database
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {lookupResult.matching_firms.map((firm) => (
                  <div
                    key={firm.id}
                    className="flex items-center justify-between rounded-lg border border-amber-200 bg-white p-3"
                  >
                    <div>
                      <div className="font-medium text-slate-800">{firm.firm_name}</div>
                      <div className="flex flex-wrap gap-2 text-xs text-slate-500">
                        {firm.website && (
                          <span className="flex items-center gap-1">
                            <Globe className="h-3 w-3" />
                            {firm.website}
                          </span>
                        )}
                        <span className="flex items-center gap-1">
                          <MessageSquare className="h-3 w-3" />
                          {firm.conversation_ids.length} conversations
                        </span>
                        {firm.research_status === "completed" && (
                          <span className="flex items-center gap-1 text-emerald-600">
                            <Sparkles className="h-3 w-3" />
                            Researched
                          </span>
                        )}
                      </div>
                    </div>
                    <div className="flex gap-2">
                      {firm.research_status !== "completed" && (
                        <Badge className="bg-slate-100 text-slate-600">Not researched</Badge>
                      )}
                    </div>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Matching Conversations */}
          <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-3 text-lg">
                <MessageSquare className="h-5 w-5 text-indigo-600" />
                Matching Conversations
                <Badge className="bg-slate-100 text-slate-600">
                  {lookupResult.total_conversations}
                </Badge>
              </CardTitle>
              <CardDescription>
                Conversations matching &quot;{firmName}&quot; from local DB and Front
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {lookupResult.conversations.length > 0 ? (
                <>
                  <div className="flex items-center gap-2 text-sm">
                    <button
                      onClick={selectAllConversations}
                      className="text-indigo-600 hover:text-indigo-800 hover:underline"
                    >
                      Select all
                    </button>
                    <span className="text-slate-300">|</span>
                    <button
                      onClick={deselectAllConversations}
                      className="text-indigo-600 hover:text-indigo-800 hover:underline"
                    >
                      Deselect all
                    </button>
                    {selectedConvIds.size > 0 && (
                      <span className="text-slate-500">
                        ({selectedConvIds.size} selected)
                      </span>
                    )}
                  </div>

                  <div className="max-h-96 overflow-y-auto space-y-1">
                    {lookupResult.conversations.map((conv) => (
                      <label
                        key={conv.conversation_id}
                        className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                          selectedConvIds.has(conv.conversation_id)
                            ? "border-indigo-300 bg-indigo-50/50"
                            : "border-slate-100 bg-white hover:bg-slate-50"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={selectedConvIds.has(conv.conversation_id)}
                          onChange={() => toggleConversation(conv.conversation_id)}
                          className="mt-1 h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-800 truncate">
                              {conv.subject || "(No subject)"}
                            </span>
                            <Badge className={`text-xs ${
                              conv.source === "local"
                                ? "bg-emerald-100 text-emerald-700"
                                : "bg-blue-100 text-blue-700"
                            }`}>
                              {conv.source}
                            </Badge>
                          </div>
                          <div className="flex flex-wrap gap-2 text-xs text-slate-500 mt-0.5">
                            {conv.sender && <span>From: {conv.sender}</span>}
                            {conv.created_at && (
                              <span>{new Date(conv.created_at).toLocaleDateString()}</span>
                            )}
                          </div>
                          {conv.snippet && (
                            <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                              {conv.snippet}
                            </p>
                          )}
                        </div>
                        <a
                          href={`https://app.frontapp.com/open/${conv.conversation_id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex-shrink-0 text-slate-400 hover:text-indigo-600"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <ExternalLink className="h-4 w-4" />
                        </a>
                      </label>
                    ))}
                  </div>
                </>
              ) : (
                <div className="py-8 text-center text-slate-500">
                  No matching conversations found
                </div>
              )}

              {/* Action Buttons */}
              {!createResult && (
                <div className="flex gap-3 border-t border-slate-100 pt-4">
                  <Button
                    onClick={() => handleCreate(false)}
                    disabled={isCreating || isResearching}
                    variant="ghost"
                    className="flex items-center gap-2 border border-slate-200"
                  >
                    {isCreating && !isResearching ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <Building2 className="h-4 w-4" />
                        Add Firm
                      </>
                    )}
                  </Button>
                  <Button
                    onClick={() => handleCreate(true)}
                    disabled={isCreating || isResearching}
                    className="flex items-center gap-2"
                  >
                    {isResearching ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        {researchStatus === "queued" && "Queued..."}
                        {researchStatus === "in_progress" && "Researching..."}
                        {!researchStatus && "Starting..."}
                      </>
                    ) : isCreating ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Creating...
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4" />
                        Add &amp; Research
                      </>
                    )}
                  </Button>
                </div>
              )}

              {createError && (
                <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {createError}
                </div>
              )}

              {createResult && !researchedFirm && !isResearching && (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                  {createResult.message}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Created/Researched Firm Card */}
          {(researchedFirm || (createResult && !isResearching)) && (
            <Card className="rounded-2xl border border-emerald-200/70 bg-emerald-50/30">
              <CardHeader className="pb-3">
                <CardTitle className="flex items-center gap-3 text-lg">
                  <Check className="h-5 w-5 text-emerald-600" />
                  {researchedFirm ? "Firm Created & Researched" : "Firm Created"}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {researchedFirm ? (
                  <div className="space-y-3">
                    <div className="font-medium text-slate-800">{researchedFirm.firm_name}</div>
                    {researchedFirm.website && (
                      <div className="flex items-center gap-2 text-sm text-slate-600">
                        <Globe className="h-4 w-4 text-indigo-500" />
                        <a
                          href={researchedFirm.website.startsWith("http") ? researchedFirm.website : `https://${researchedFirm.website}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-indigo-600 hover:underline"
                        >
                          {researchedFirm.website}
                        </a>
                      </div>
                    )}
                    {researchedFirm.leadership && researchedFirm.leadership.length > 0 && (
                      <div>
                        <h4 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-700">
                          <Sparkles className="h-4 w-4 text-amber-500" />
                          Leadership ({researchedFirm.leadership.length})
                        </h4>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {researchedFirm.leadership.map((leader, i) => (
                            <div
                              key={i}
                              className="rounded-lg border border-amber-100 bg-white p-3 text-sm"
                            >
                              <div className="font-medium text-slate-800">{leader.name}</div>
                              {leader.title && (
                                <div className="text-xs text-slate-600">{leader.title}</div>
                              )}
                              {leader.email && (
                                <div className="text-xs text-slate-500 mt-1">{leader.email}</div>
                              )}
                              {isValidLinkedInUrl(leader.linkedin) && (
                                <a
                                  href={leader.linkedin?.startsWith("http") ? leader.linkedin : `https://${leader.linkedin}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline mt-1"
                                >
                                  <Linkedin className="h-3 w-3" />
                                  LinkedIn
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <div className="text-xs text-slate-500">
                      {researchedFirm.conversation_ids.length} conversations associated
                    </div>
                  </div>
                ) : createResult ? (
                  <div className="space-y-2">
                    <div className="font-medium text-slate-800">{createResult.pif.firm_name}</div>
                    <div className="text-sm text-slate-600">{createResult.message}</div>
                    <div className="text-xs text-slate-500">
                      {createResult.pif.conversation_ids.length} conversations associated
                    </div>
                  </div>
                ) : null}
              </CardContent>
            </Card>
          )}
        </>
      )}
    </motion.section>
  );
}

function OutreachTab({
  researchedFirms,
  outreachFirmId,
  setOutreachFirmId,
  caseStudyUrl,
  setCaseStudyUrl,
  clientDescription,
  setClientDescription,
  outreachMessages,
  setOutreachMessages,
  isGeneratingOutreach,
  setIsGeneratingOutreach,
  outreachError,
  setOutreachError,
}: {
  researchedFirms: PifInfoResponse[];
  outreachFirmId: string;
  setOutreachFirmId: (v: string) => void;
  caseStudyUrl: string;
  setCaseStudyUrl: (v: string) => void;
  clientDescription: string;
  setClientDescription: (v: string) => void;
  outreachMessages: OutreachMessageResult[] | null;
  setOutreachMessages: (v: OutreachMessageResult[] | null) => void;
  isGeneratingOutreach: boolean;
  setIsGeneratingOutreach: (v: boolean) => void;
  outreachError: string | null;
  setOutreachError: (v: string | null) => void;
}) {

  const handleGenerate = async () => {
    if (!outreachFirmId || !caseStudyUrl || !clientDescription) return;

    setIsGeneratingOutreach(true);
    setOutreachError(null);
    setOutreachMessages(null);

    try {
      const result = await PifApi.generateOutreach(outreachFirmId, caseStudyUrl, clientDescription);
      setOutreachMessages(result.messages);
      if (result.errors.length > 0) {
        setOutreachError(`Generated with ${result.errors.length} error(s): ${result.errors.join("; ")}`);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to generate outreach messages";
      setOutreachError(message);
    } finally {
      setIsGeneratingOutreach(false);
    }
  };

  const formatAllMessages = (msg: OutreachMessageResult) => {
    return `=== ${msg.name} (${msg.title}) ===

--- Short Pranav (${msg.shortPranav.length} chars) ---
Subject: ${msg.subjectShortPranav}
${msg.shortPranav}

--- Short Neha (${msg.shortNeha.length} chars) ---
Subject: ${msg.subjectShortNeha}
${msg.shortNeha}

--- Long Pranav ---
Subject: ${msg.subjectLongPranav}
${msg.longPranav}

--- Long Neha ---
Subject: ${msg.subjectLongNeha}
${msg.longNeha}`;
  };

  const canGenerate = outreachFirmId && caseStudyUrl.trim() && clientDescription.trim() && !isGeneratingOutreach;

  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={easing}
      className="space-y-6"
    >
      {/* Configuration Card */}
      <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-3 text-xl">
            <MessageSquare className="h-5 w-5 text-indigo-600" />
            Generate Outreach Messages
          </CardTitle>
          <CardDescription>
            Generate personalized LinkedIn outreach messages for a firm&apos;s leadership team
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Firm Selector */}
          <div className="space-y-1.5">
            <label htmlFor="outreach-firm" className="text-sm font-medium text-slate-700">
              Select Firm
            </label>
            <select
              id="outreach-firm"
              value={outreachFirmId}
              onChange={(e) => setOutreachFirmId(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Choose a researched firm...</option>
              {researchedFirms.map((firm) => {
                const researchedDate = firm.last_researched_at
                  ? new Date(firm.last_researched_at).toLocaleDateString()
                  : "Unknown";
                return (
                  <option key={firm.id} value={firm.id}>
                    {firm.firm_name} ({firm.leadership?.length || 0} leaders) - {researchedDate}
                  </option>
                );
              })}
            </select>
            {researchedFirms.length === 0 && (
              <p className="text-xs text-slate-400">
                No researched firms available. Research a firm first from the PIF Data tab.
              </p>
            )}
          </div>

          {/* Case Study URL */}
          <div className="space-y-1.5">
            <label htmlFor="case-study-url" className="text-sm font-medium text-slate-700">
              Case Study URL
            </label>
            <input
              type="url"
              id="case-study-url"
              value={caseStudyUrl}
              onChange={(e) => setCaseStudyUrl(e.target.value)}
              placeholder="https://example.com/case-study"
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Generation Instructions */}
          <div className="space-y-1.5">
            <label htmlFor="client-description" className="text-sm font-medium text-slate-700">
              Generation Instructions
            </label>
            <textarea
              id="client-description"
              value={clientDescription}
              onChange={(e) => setClientDescription(e.target.value)}
              placeholder="Provide instructions on how to generate the outreach message (e.g., tone, key points to mention, specific angles to use...)"
              rows={3}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y"
            />
          </div>

          {/* Generate Button */}
          <Button
            onClick={handleGenerate}
            disabled={!canGenerate}
            className="flex items-center gap-2"
          >
            {isGeneratingOutreach ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                Generate Messages
              </>
            )}
          </Button>

          {/* Error */}
          {outreachError && (
            <div className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
              {outreachError}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Results */}
      {outreachMessages && outreachMessages.length > 0 && (
        <div className="space-y-4">
          {outreachMessages.map((msg, idx) => (
            <Card key={idx} className="rounded-2xl border border-slate-200/70 bg-white/90">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">
                    {msg.name}
                    <span className="ml-2 text-sm font-normal text-slate-500">{msg.title}</span>
                  </CardTitle>
                  <CopyButton text={formatAllMessages(msg)} label="Copy All" />
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Short Pranav */}
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Short Pranav</span>
                      <Badge className={`text-xs ${msg.shortPranav.length <= 300 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                        {msg.shortPranav.length} chars
                      </Badge>
                    </div>
                    <CopyButton text={msg.shortPranav} />
                  </div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-xs font-medium text-indigo-700">Subject:</span>
                    <span className="text-xs text-indigo-900">{msg.subjectShortPranav}</span>
                    <CopyButton text={msg.subjectShortPranav} />
                  </div>
                  <p className="text-sm text-slate-600 whitespace-pre-wrap">{msg.shortPranav}</p>
                </div>

                {/* Short Neha */}
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Short Neha</span>
                      <Badge className={`text-xs ${msg.shortNeha.length <= 300 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                        {msg.shortNeha.length} chars
                      </Badge>
                    </div>
                    <CopyButton text={msg.shortNeha} />
                  </div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-xs font-medium text-indigo-700">Subject:</span>
                    <span className="text-xs text-indigo-900">{msg.subjectShortNeha}</span>
                    <CopyButton text={msg.subjectShortNeha} />
                  </div>
                  <p className="text-sm text-slate-600 whitespace-pre-wrap">{msg.shortNeha}</p>
                </div>

                {/* Long Pranav */}
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Long Pranav</span>
                      <Badge className={`text-xs ${msg.longPranav.length <= 450 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                        {msg.longPranav.length} chars
                      </Badge>
                    </div>
                    <CopyButton text={msg.longPranav} />
                  </div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-xs font-medium text-indigo-700">Subject:</span>
                    <span className="text-xs text-indigo-900">{msg.subjectLongPranav}</span>
                    <CopyButton text={msg.subjectLongPranav} />
                  </div>
                  <p className="text-sm text-slate-600 whitespace-pre-wrap">{msg.longPranav}</p>
                </div>

                {/* Long Neha */}
                <div className="rounded-lg border border-slate-100 bg-slate-50 p-3">
                  <div className="mb-2 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-slate-700">Long Neha</span>
                      <Badge className={`text-xs ${msg.longNeha.length <= 450 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                        {msg.longNeha.length} chars
                      </Badge>
                    </div>
                    <CopyButton text={msg.longNeha} />
                  </div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="text-xs font-medium text-indigo-700">Subject:</span>
                    <span className="text-xs text-indigo-900">{msg.subjectLongNeha}</span>
                    <CopyButton text={msg.subjectLongNeha} />
                  </div>
                  <p className="text-sm text-slate-600 whitespace-pre-wrap">{msg.longNeha}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {outreachMessages && outreachMessages.length === 0 && !outreachError && (
        <div className="py-12 text-center text-slate-500">
          No messages were generated. The firm may not have leadership data.
        </div>
      )}
    </motion.section>
  );
}

function OutgenTab({
  researchedFirms,
  outgenFirmId,
  setOutgenFirmId,
  outgenCaseStudyUrl,
  setOutgenCaseStudyUrl,
  outgenInstructions,
  setOutgenInstructions,
  outgenMutualApproved,
  setOutgenMutualApproved,
}: {
  researchedFirms: PifInfoResponse[];
  outgenFirmId: string;
  setOutgenFirmId: (v: string) => void;
  outgenCaseStudyUrl: string;
  setOutgenCaseStudyUrl: (v: string) => void;
  outgenInstructions: string;
  setOutgenInstructions: (v: string) => void;
  outgenMutualApproved: boolean;
  setOutgenMutualApproved: (v: boolean) => void;
}) {
  const [copiedIdx, setCopiedIdx] = useState<number | null>(null);
  const selectedFirm = researchedFirms.find((f) => f.id === outgenFirmId);

  const formatLeaderInfo = (leader: NonNullable<PifInfoResponse["leadership"]>[number]) => {
    const parts: string[] = [];
    parts.push(`Name: ${leader.name}`);
    parts.push(`Title: ${leader.title}`);
    if (leader.email) parts.push(`Email: ${leader.email}`);
    if (leader.linkedin) parts.push(`LinkedIn: ${leader.linkedin}`);
    if (leader.bio) parts.push(`Bio: ${leader.bio}`);
    if (leader.education?.length) parts.push(`Education: ${leader.education.join(", ")}`);
    if (leader.experience?.length) parts.push(`Experience: ${leader.experience.join("; ")}`);
    if (leader.skills?.length) parts.push(`Skills: ${leader.skills.join(", ")}`);
    if (leader.certifications?.length) parts.push(`Certifications: ${leader.certifications.join(", ")}`);
    if (leader.cases_handled?.length) parts.push(`Notable Cases: ${leader.cases_handled.join("; ")}`);
    if (leader.bar_admissions?.length) parts.push(`Bar Admissions: ${leader.bar_admissions.join(", ")}`);
    return parts.join("\n");
  };

  const generatePrompts = (): { name: string; prompt: string }[] => {
    if (!selectedFirm) return [];

    const leaders = selectedFirm.leadership || [];
    if (leaders.length === 0) return [];

    const researchData = selectedFirm.research_data;
    const firmInfo = [
      `Firm Name: ${selectedFirm.firm_name}`,
      selectedFirm.website ? `Website: ${selectedFirm.website}` : null,
      selectedFirm.emails.length ? `Emails: ${selectedFirm.emails.join(", ")}` : null,
      selectedFirm.phones.length ? `Phones: ${selectedFirm.phones.join(", ")}` : null,
      selectedFirm.addresses.length ? `Addresses: ${selectedFirm.addresses.join("; ")}` : null,
      researchData?.practice_areas?.length ? `Practice Areas: ${researchData.practice_areas.join(", ")}` : null,
      researchData?.firm_size ? `Firm Size: ${researchData.firm_size}` : null,
      researchData?.founded_year ? `Founded: ${researchData.founded_year}` : null,
      researchData?.office_locations?.length ? `Office Locations: ${researchData.office_locations.join("; ")}` : null,
      researchData?.notable_cases?.length ? `Notable Cases: ${researchData.notable_cases.join("; ")}` : null,
      researchData?.awards_recognition?.length ? `Awards & Recognition: ${researchData.awards_recognition.join("; ")}` : null,
    ].filter(Boolean).join("\n");

    const mutualClientTier = outgenMutualApproved ? "1" : "2"; // Tier 3 (N/A) would require additional UI state
    const mutualClientSection = `
- Mutual client: Precise Imaging
- Mutual client relationship: PI firms send their clients to Precise Imaging for diagnostic imaging. Precise works on a lien basis and sends back signed liens, records, and documentation to the firm.
- Did mutual client approve outreach reference? ${outgenMutualApproved ? "YES" : "NO"}
- Mutual client tier: ${mutualClientTier}`;

    return leaders.map((leader) => {
      const leaderInfo = formatLeaderInfo(leader);

      const prompt = `Generate LinkedIn outreach messages for the following person.

=== RESEARCH FIRST ===
Before completing the checklist, do this research:
- Read the case study URL provided in the context section
- Search for the prospect's LinkedIn profile URL (include it in your output)
- Look for interviews, press mentions, published quotes, or notable case results featuring the prospect
- Identify which insights from Neha's library are most relevant to this firm's situation

=== PRE-GENERATION CHECKLIST ===
Before writing any messages, answer these questions internally (do not output them except in the rationale section):

1. What is this person's most likely daily operational frustration?
   (Not "running a law firm" — something specific: managing intake volume? chasing medical records? losing leads to faster competitors? coordinating across offices?)

2. What is the single strongest angle for this prospect?
   Choose ONE:
   a. Mutual client connection (if Tier 1 or Tier 2)
   b. Career transition or unusual background
   c. Firm growth stage (new offices, recent hires, recently founded)
   d. Competitive pressure (saturated market, losing leads)
   e. Workflow inefficiency (signs of manual processes)
   f. Something specific from their public content

3. Which 2 Cialdini principles are the strongest fit?
   Pick exactly 2. Using all of them in a 300-character message produces garbage.

4. What would make this person stop scrolling?
   Something specific: a number they haven't seen, a question about something they care about, a reference only someone paying attention would know.

5. What is the Pranav angle vs. the Neha angle?
   They must be different. Write one sentence for each:
   - Pranav will approach from: [angle]
   - Neha will approach from: [angle]
   If both angles are the same, choose a new one for Neha.

6. Mutual client tier: [1 / 2 / 3] based on context section.

These answers should guide every word of every message.

=== DISQUALIFICATION CHECK ===
Before generating, check for these signals. If any are present, output: "DISQUALIFICATION FLAG: [reason]. Recommend skipping or adjusting approach." Then generate messages anyway.

- Prospect has publicly posted negative content about AI, automation, or cold outreach in the last 6 months
- Firm is 1-2 people total (solution economics likely don't work)
- Prospect is retired, transitioning out, or has "former" in their title
- Firm does not practice personal injury
- Prospect recently posted about a competitor's product
- Profile shows no activity in 12+ months

=== FIRM SIZE HEURISTIC ===
For firms under 5 people: emphasize time savings, after-hours coverage, and missed opportunities.
For firms over 10 people: emphasize staff efficiency, lead velocity, scalability, and competitive pressure from faster firms.

=== OUTPUT FORMAT ===

**Phase 1 (internal, do not output):**
- Complete the pre-generation checklist
- Identify the single strongest angle
- Select 2 Cialdini principles

**Phase 2 (output these 6 messages):**
1. Connection request from Pranav (under 300 characters) + subject line (under 6 words)
2. Connection request from Neha (under 300 characters) + subject line (under 6 words)
3. InMail from Pranav (under 450 characters) + subject line (under 6 words)
4. InMail from Neha (under 450 characters) + subject line (under 6 words)
5. Follow-up from Pranav after connection acceptance (under 300 characters)
6. Follow-up from Neha after connection acceptance (under 300 characters)

**Phase 3 (output):**
Brief rationale: For each message, one sentence explaining the angle chosen and the primary Cialdini principle used.

=== CHARACTER LIMITS ===

**300 characters is 2-3 short sentences. Here's exactly what 300 characters looks like:**
"Victor, saw you switched from 24 years as Deputy City Attorney to plaintiff work. That's a rare path. Curious what made you make the jump, and whether the documentation standards feel different on this side."

**450 characters is 3-4 short sentences. Here's exactly what 450 characters looks like:**
"Daniel, the Munoz settlement was all over the news. $18.85M for a single plaintiff is remarkable. We've been working with imaging centers on the lien side of PI cases, and the documentation quality coming back to attorneys varies wildly. About 12% of liens we process have some kind of alteration. Curious if that matches what you see on big cases. Wrote up what we learned here: [URL]"

**Before outputting each message, count its characters. If a message exceeds its limit, shorten it. Do not compress by removing spaces, using abbreviations, or making text harder to read. Cut content instead.**

=== CONNECTION REQUESTS VS INMAILS ===

**Connection requests (messages 1, 2, 5, 6):**
- NO links, NO case study URLs, NO product mentions
- Goal: Earn the right to have a conversation
- Formula: Non-obvious insight about their situation + genuine question
- The recipient should feel they learned something just by reading

**InMails (messages 3, 4):**
- Include case study URL
- Structure: Warm opener > Shared problem > What you learned > Soft CTA
- MUST include at least one specific, quantified result in the message body (not just behind the link)
- Use soft CTAs that give them an easy out:
  - "Happy to share what we learned if it's useful"
  - "Curious if you've run into this"
  - "No pressure, just thought it might resonate"
  - "If you've already solved this, I'd love to hear how"
  - "Either way, good to connect"

=== MUTUAL CLIENT TIERS ===
Read the "Did mutual client approve outreach reference?" field in context FIRST. This determines which tier to use.

**Tier 1 — Client approved (context says "YES"):**
- Name Precise Imaging in subject lines and opening sentences
- Lead with the relationship: "Precise Imaging is how we got into this space"
- Use their name freely throughout

**Tier 2 — Client exists but did NOT approve (context says "NO"):**
- Never name the client
- Reference the ecosystem: "imaging centers that work with PI firms on liens," "the lien workflow between firms and imaging partners"
- Reference patterns without attribution: "we've seen about 12% of lien documents have some kind of alteration"
- Signal insider knowledge without naming anyone

**Tier 3 — No mutual client (context says "N/A"):**
- Skip mutual client framing entirely
- Do not fabricate a connection
- Use other angles: competitive pressure, workflow observation, career/background research

=== CASE STUDY BRIDGE (healthcare to law firm) ===
The connection is the lien workflow. PI firms and imaging centers are on opposite ends of the same pipeline:
1. PI firm sends client to imaging center for diagnostic work
2. Imaging center does work on lien basis
3. Imaging center sends back signed liens, records, documentation to firm
4. Firm uses documents for case progression, demand packages, settlements

What we learned on the imaging center side directly affects what the PI firm receives.

**Bridge language (adapt, don't copy verbatim):**
- "We built our systems on the imaging center side of the PI workflow. The documentation improvements flow directly to the firms they work with."
- "We started by automating lien handling for imaging centers. The patterns we found in document quality are the same ones that slow down case progression on the firm side."

For InMails: Use a bridge sentence BEFORE the case study link. For connection requests: No link, so no bridge needed.

=== NEHA'S INSIGHT LIBRARY ===
For each prospect, select 1-2 insights most relevant to their situation. Do not use all of them. Rotate across prospects.

1. **Lien document quality:** "When we started reading liens automatically, about 12% had some kind of alteration. Strikethroughs, whiteout, missing signatures, formatting that would cause problems if nobody caught it."

2. **After-hours lead decay:** "We tracked what happens to PI leads that come in after 6pm. About 35-40% contact at least one other firm before the original firm calls back the next morning."

3. **Response time cliff:** "There's a cliff in PI lead conversion around the 5-minute mark. Under 5 minutes, conversion rates are 3-4x higher than at 30 minutes. Most firms average 45 minutes to 2 hours for web leads."

4. **Bilingual intake gap:** "Firms that advertise 'se habla español' but only have bilingual staff during business hours see a measurable drop in Spanish-language lead conversion after 5pm."

5. **Form abandonment:** "About 60% of people who start a PI intake form don't finish it. They get to the second or third question and leave."

=== CIALDINI PRINCIPLES (pick 2 per message) ===

- **Reciprocity:** Give before you ask. Lead with a non-obvious insight or data point. The recipient should feel they received something just by reading.
- **Social proof:** Be specific. "3 PI firms in SoCal running 5+ offices" is strong. "Firms like yours" is weak.
- **Authority:** Demonstrate expertise through discovered insights, not credentials. A specific failure mode, a counterintuitive pattern.
- **Liking:** Reference specific, researched details from their bio or interviews. Use their own words back to them.
- **Unity:** Establish shared identity. Pranav should reference being a founder when writing to founders.
- **Commitment/consistency:** Ask easy, ego-friendly questions that lead to engagement.

=== PRANAV VS NEHA ===

**Pranav (Founder):**
- Peer-to-peer, business owner to business leader
- Focuses on operational challenges, growth, scaling
- Voice: "I've been thinking about..." / "Curious how you handle..."
- When writing to founders: explicitly establish founder-to-founder identity

**Neha (Engineer):**
- Curious problem-solver, interested in how things work
- Focuses on workflows, systems, the "how" behind operations
- Voice: "One thing that surprised us..." / "The tricky part we found was..."
- MUST anchor authority with at least one "discovered insight" per message from the library above

**CRITICAL:** After generating both connection requests, check: if you swapped the sender names, would the messages still make sense? If yes, the angles aren't different enough. Rewrite.

=== EXAMPLES ===

**Good connection request (insight + question):**
"Victor, saw you switched from 24 years as Deputy City Attorney to plaintiff work. That's a big shift. Curious what made you make the jump."

**Good connection request (data point + question):**
"Daniel, the Munoz settlement was all over the news. $18.85M for a single plaintiff is remarkable. Did the documentation side go smoothly, or was it a battle?"

**Bad connection request (too salesy):**
"Managing intake across 3 offices takes serious coordination. We work with Precise Imaging on exactly this. Would love to connect."

**Bad connection request (all question, no value):**
"Victor, saw you've been at the firm for 10 years. Curious what's changed the most."

**Good subject lines:** "Quick question, Victor" / "The Munoz case" / "Encino to Turlock"
**Bad subject lines:** "How we automated 24/7 intake" / "Partnership opportunity"

=== FOLLOW-UP MESSAGES (outputs 5 and 6) ===
After connection acceptance, wait 24-48 hours. The follow-up should:

- Thank them for connecting (one short sentence, not effusive)
- Reference something specific from their recent activity (a post, comment, firm update, case result)
- Make one soft offer: share something specific and useful. Not "let's chat" but "I put together [specific resource] for [their situation]. Happy to send it over."
- Under 300 characters
- NOT include a case study link (that comes in message 3 if conversation continues)

If the original connection request referenced a question, gently re-ask: "Curious if you ever figured out [the thing I asked about]."

=== WHAT TO AVOID ===
1. Including links in connection requests
2. Generic subject lines that could apply to anyone
3. Leading with "We helped..." instead of their situation
4. Using em dashes (use commas, periods, semicolons)
5. Connection requests that are all question, no value given
6. Vague social proof ("firms like yours")
7. Teaching the prospect something they already know
8. The phrase "I'd love to connect"
9. InMails without a case study URL
10. Pranav and Neha taking the same angle

=== CONTEXT ===

Case study URL (primary): ${outgenCaseStudyUrl}
${mutualClientSection}
${outgenInstructions ? `\nAdditional Instructions:\n${outgenInstructions}\n` : ""}

Firm Information:
${firmInfo}

Target Person:
${leaderInfo}`;

      return { name: leader.name, prompt };
    });
  };

  const handleCopyOne = async (text: string, idx: number) => {
    await navigator.clipboard.writeText(text);
    setCopiedIdx(idx);
    setTimeout(() => setCopiedIdx(null), 2000);
  };

  const prompts = generatePrompts();
  const canCopy = outgenFirmId && selectedFirm;

  return (
    <motion.section
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={easing}
      className="space-y-6"
    >
      {/* Configuration Card */}
      <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
        <CardHeader className="pb-4">
          <CardTitle className="flex items-center gap-3 text-xl">
            <Copy className="h-5 w-5 text-indigo-600" />
            Generate Outreach Prompt
          </CardTitle>
          <CardDescription>
            Copy firm and leadership information to use with any chatbot for generating outreach messages
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Firm Selector */}
          <div className="space-y-1.5">
            <label htmlFor="outgen-firm" className="text-sm font-medium text-slate-700">
              Select Firm
            </label>
            <select
              id="outgen-firm"
              value={outgenFirmId}
              onChange={(e) => setOutgenFirmId(e.target.value)}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            >
              <option value="">Choose a researched firm...</option>
              {researchedFirms.map((firm) => {
                const researchedDate = firm.last_researched_at
                  ? new Date(firm.last_researched_at).toLocaleDateString()
                  : "Unknown";
                return (
                  <option key={firm.id} value={firm.id}>
                    {firm.firm_name} ({firm.leadership?.length || 0} leaders) - {researchedDate}
                  </option>
                );
              })}
            </select>
            {researchedFirms.length === 0 && (
              <p className="text-xs text-slate-400">
                No researched firms available. Research a firm first from the PIF Data tab.
              </p>
            )}
          </div>

          {/* Case Study URL */}
          <div className="space-y-1.5">
            <label htmlFor="outgen-case-study-url" className="text-sm font-medium text-slate-700">
              Case Study URL
            </label>
            <input
              type="url"
              id="outgen-case-study-url"
              value={outgenCaseStudyUrl}
              onChange={(e) => setOutgenCaseStudyUrl(e.target.value)}
              placeholder="https://example.com/case-study"
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
          </div>

          {/* Generation Instructions */}
          <div className="space-y-1.5">
            <label htmlFor="outgen-instructions" className="text-sm font-medium text-slate-700">
              Additional Instructions (optional)
            </label>
            <textarea
              id="outgen-instructions"
              value={outgenInstructions}
              onChange={(e) => setOutgenInstructions(e.target.value)}
              placeholder="Any additional instructions for generating the messages (e.g., tone, key points to mention, specific angles to use...)"
              rows={3}
              className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-y"
            />
          </div>

          {/* Mutual Client Section */}
          <div className="rounded-lg border border-slate-200 bg-slate-50/50 p-4 space-y-3">
            <p className="text-sm font-medium text-slate-700">Mutual Client: Precise Imaging</p>
            <p className="text-xs text-slate-500">PI firms send their clients to Precise Imaging, and Precise works on a lien basis, so they send back signed liens.</p>

            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="outgen-mutual-approved"
                checked={outgenMutualApproved}
                onChange={(e) => setOutgenMutualApproved(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
              />
              <label htmlFor="outgen-mutual-approved" className="text-xs font-medium text-slate-600">
                Precise Imaging approved outreach reference
              </label>
            </div>
          </div>

        </CardContent>
      </Card>

      {/* Per-Leader Prompts */}
      {canCopy && prompts.length > 0 && (
        <div className="space-y-4">
          {prompts.map((item, idx) => (
            <Card key={idx} className="rounded-2xl border border-slate-200/70 bg-white/90">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{item.name}</CardTitle>
                  <Button
                    variant="ghost"
                    onClick={() => handleCopyOne(item.prompt, idx)}
                    className="flex items-center gap-1.5 text-sm px-3 py-1.5 h-auto"
                  >
                    {copiedIdx === idx ? (
                      <>
                        <Check className="h-3.5 w-3.5" />
                        Copied!
                      </>
                    ) : (
                      <>
                        <Copy className="h-3.5 w-3.5" />
                        Copy Prompt
                      </>
                    )}
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <pre className="max-h-72 overflow-auto rounded-lg border border-slate-100 bg-slate-50 p-4 text-xs text-slate-700 whitespace-pre-wrap">
                  {item.prompt}
                </pre>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {canCopy && prompts.length === 0 && (
        <div className="py-12 text-center text-slate-500">
          No leadership data available for this firm.
        </div>
      )}
    </motion.section>
  );
}
