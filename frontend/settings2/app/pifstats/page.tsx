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
  Activity,
  Clock,
  MousePointer,
  Eye,
  BarChart3,
  TrendingUp,
  Sparkles,
  Linkedin,
  Award,
  Briefcase,
} from "lucide-react";

import { ApiError, PifApi, UsageApi, UsageStatsResponse } from "@/lib/api";
import type { PifInfoResponse, PifInfoListResponse, ProcessDayResponse, ResearchStatusResponse } from "@/lib/types";
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

  // Process day state
  const [processDate, setProcessDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<ProcessDayResponse | null>(null);

  // Usage stats state
  const [usageStats, setUsageStats] = useState<UsageStatsResponse | null>(null);
  const [usageStatsLoading, setUsageStatsLoading] = useState(false);
  const [usageStatsError, setUsageStatsError] = useState<string | null>(null);
  const [usageStatsDays, setUsageStatsDays] = useState(30);

  // Tab state
  const [activeTab, setActiveTab] = useState<"pif" | "usage">("pif");

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

  const fetchUsageStats = useCallback(async () => {
    setUsageStatsLoading(true);
    setUsageStatsError(null);
    try {
      const stats = await UsageApi.getStats("admin", usageStatsDays);
      setUsageStats(stats);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load usage stats";
      setUsageStatsError(message);
    } finally {
      setUsageStatsLoading(false);
    }
  }, [usageStatsDays]);

  const fetchData = useCallback(async () => {
    try {
      const payload = await PifApi.list({
        search: searchTerm || undefined,
        page: currentPage,
        pageSize,
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
  }, [searchTerm, currentPage, pageSize]);

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      if (!isAuthenticated) {
        setIsLoading(false);
        return;
      }

      try {
        await Promise.all([fetchData(), fetchUsageStats()]);
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

  // Re-fetch when page changes
  useEffect(() => {
    if (!isLoading) {
      fetchData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentPage]);

  // Re-fetch usage stats when days filter changes
  useEffect(() => {
    if (isAuthenticated && !isLoading) {
      fetchUsageStats();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usageStatsDays]);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    setCurrentPage(1);
    fetchData();
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
            onClick={() => setActiveTab("usage")}
            className={`px-4 py-2 text-sm font-medium rounded-md transition-colors ${
              activeTab === "usage"
                ? "bg-white text-slate-900 shadow-sm"
                : "text-slate-600 hover:text-slate-900"
            }`}
          >
            <Activity className="h-4 w-4 inline-block mr-1.5 -mt-0.5" />
            Usage Stats
          </button>
        </div>

        {activeTab === "pif" && (
          <>
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

                {/* Search Form */}
                <form onSubmit={handleSearch} className="flex gap-2">
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

        {activeTab === "usage" && (
          <motion.section
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={easing}
          >
            <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
              <CardHeader className="pb-4">
                <CardTitle className="flex items-center gap-3 text-xl">
                  <Activity className="h-5 w-5 text-indigo-600" />
                  Admin Usage Statistics
                </CardTitle>
                <CardDescription>
                  Track how the admin user interacts with the /settings page
                </CardDescription>
              </CardHeader>
              <CardContent>
                {/* Time range selector */}
                <div className="mb-6 flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => setUsageStatsDays(1)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      usageStatsDays === 1
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    24h
                  </button>
                  <button
                    onClick={() => setUsageStatsDays(7)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      usageStatsDays === 7
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    7d
                  </button>
                  <button
                    onClick={() => setUsageStatsDays(30)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      usageStatsDays === 30
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    30d
                  </button>
                  <button
                    onClick={() => setUsageStatsDays(90)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      usageStatsDays === 90
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    90d
                  </button>
                  <div className="ml-2 flex items-center">
                    {usageStatsLoading && <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />}
                  </div>
                </div>

              {usageStatsError && (
                <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {usageStatsError}
                </div>
              )}

              {usageStatsLoading && !usageStats ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                </div>
              ) : usageStats ? (
                <div className="space-y-6">
                  {/* Overview Stats */}
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-6">
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <BarChart3 className="h-3.5 w-3.5" />
                        Total Events
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_events.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Eye className="h-3.5 w-3.5" />
                        Page Views
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_page_views.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <MousePointer className="h-3.5 w-3.5" />
                        Actions
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_actions.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Users className="h-3.5 w-3.5" />
                        Sessions
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_sessions.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Globe className="h-3.5 w-3.5" />
                        Unique Pages
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.unique_pages_visited}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Clock className="h-3.5 w-3.5" />
                        Avg Session
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {Math.round(usageStats.average_session_duration_ms / 1000 / 60)}m
                      </div>
                    </div>
                  </div>

                  {/* Recent Activity */}
                  <div className="grid gap-6 md:grid-cols-2">
                    {/* Time-based activity */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <TrendingUp className="h-4 w-4 text-indigo-500" />
                        Activity Summary
                      </h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-slate-600">Today</span>
                          <span className="font-medium text-slate-800">{usageStats.events_today} events</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-600">This Week</span>
                          <span className="font-medium text-slate-800">{usageStats.events_this_week} events</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-600">This Month</span>
                          <span className="font-medium text-slate-800">{usageStats.events_this_month} events</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-600">Total Time</span>
                          <span className="font-medium text-slate-800">
                            {Math.round(usageStats.total_time_spent_ms / 1000 / 60)} minutes
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Most visited pages */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <Eye className="h-4 w-4 text-indigo-500" />
                        Most Visited Pages
                      </h4>
                      <div className="space-y-2 text-sm">
                        {usageStats.most_visited_pages.slice(0, 5).map((page, i) => (
                          <div key={i} className="flex justify-between">
                            <span className="text-slate-600 truncate max-w-[150px]" title={page.page}>
                              {page.page || "/"}
                            </span>
                            <span className="font-medium text-slate-800">{page.count} views</span>
                          </div>
                        ))}
                        {usageStats.most_visited_pages.length === 0 && (
                          <div className="text-slate-400">No page visits recorded</div>
                        )}
                      </div>
                    </div>

                    {/* Most common actions */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <MousePointer className="h-4 w-4 text-indigo-500" />
                        Most Common Actions
                      </h4>
                      <div className="space-y-2 text-sm">
                        {usageStats.most_common_actions.slice(0, 5).map((action, i) => (
                          <div key={i} className="flex justify-between">
                            <span className="text-slate-600 truncate max-w-[150px]" title={action.action}>
                              {action.action.replace(/_/g, " ")}
                            </span>
                            <span className="font-medium text-slate-800">{action.count}x</span>
                          </div>
                        ))}
                        {usageStats.most_common_actions.length === 0 && (
                          <div className="text-slate-400">No actions recorded</div>
                        )}
                      </div>
                    </div>

                    {/* Hourly activity */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <Clock className="h-4 w-4 text-indigo-500" />
                        Activity by Hour
                      </h4>
                      <div className="flex h-16 items-end gap-0.5">
                        {Array.from({ length: 24 }, (_, hour) => {
                          const count = usageStats.hourly_activity[String(hour)] || 0;
                          const maxCount = Math.max(...Object.values(usageStats.hourly_activity), 1);
                          const height = Math.max((count / maxCount) * 100, 2);
                          return (
                            <div
                              key={hour}
                              className="flex-1 bg-indigo-400 rounded-t transition-all hover:bg-indigo-600"
                              style={{ height: `${height}%` }}
                              title={`${hour}:00 - ${count} events`}
                            />
                          );
                        })}
                      </div>
                      <div className="mt-1 flex justify-between text-xs text-slate-400">
                        <span>0h</span>
                        <span>12h</span>
                        <span>24h</span>
                      </div>
                    </div>
                  </div>

                  {/* Recent Sessions */}
                  {usageStats.sessions.length > 0 && (
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <Activity className="h-4 w-4 text-indigo-500" />
                        Recent Sessions
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-xs text-slate-500">
                              <th className="pb-2 pr-4">Session ID</th>
                              <th className="pb-2 pr-4">Start</th>
                              <th className="pb-2 pr-4">End</th>
                              <th className="pb-2 pr-4">Events</th>
                              <th className="pb-2">Pages</th>
                            </tr>
                          </thead>
                          <tbody>
                            {usageStats.sessions.slice(0, 5).map((session, i) => (
                              <tr key={i} className="border-t border-slate-100">
                                <td className="py-2 pr-4 font-mono text-xs text-slate-600">
                                  {session.session_id?.slice(0, 12)}...
                                </td>
                                <td className="py-2 pr-4 text-slate-600">
                                  {session.start ? new Date(session.start).toLocaleString() : "-"}
                                </td>
                                <td className="py-2 pr-4 text-slate-600">
                                  {session.end ? new Date(session.end).toLocaleString() : "-"}
                                </td>
                                <td className="py-2 pr-4 font-medium text-slate-800">
                                  {session.events_count}
                                </td>
                                <td className="py-2 font-medium text-slate-800">
                                  {session.pages_visited}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Recent Events */}
                  {usageStats.recent_events.length > 0 && (
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <MessageSquare className="h-4 w-4 text-indigo-500" />
                        Recent Events
                      </h4>
                      <div className="max-h-64 overflow-y-auto space-y-2">
                        {usageStats.recent_events.slice(0, 20).map((event, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-sm border border-slate-100"
                          >
                            <div className="flex items-center gap-3">
                              <Badge className={
                                event.event_type === "page_view"
                                  ? "bg-blue-100 text-blue-700"
                                  : event.event_type === "action"
                                  ? "bg-green-100 text-green-700"
                                  : event.event_type === "click"
                                  ? "bg-amber-100 text-amber-700"
                                  : event.event_type === "error"
                                  ? "bg-rose-100 text-rose-700"
                                  : "bg-slate-100 text-slate-700"
                              }>
                                {event.event_type}
                              </Badge>
                              <span className="text-slate-700">{event.event_name.replace(/_/g, " ")}</span>
                              {event.page_path && (
                                <span className="text-slate-400 text-xs">{event.page_path}</span>
                              )}
                            </div>
                            <span className="text-xs text-slate-400">
                              {new Date(event.created_at).toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-12 text-center text-slate-500">
                  No usage data available yet
                </div>
              )}
            </CardContent>
          </Card>
        </motion.section>
        )}
      </main>
    </div>
  );
}

function FirmCard({
  firm,
  isExpanded,
  onToggle,
  onDelete,
  onResearchComplete,
}: {
  firm: PifInfoResponse;
  isExpanded: boolean;
  onToggle: () => void;
  onDelete: () => void;
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
          {firm.leadership && firm.leadership.length > 0 && (
            <Badge className="bg-emerald-100 text-emerald-700">
              {firm.leadership.length} leaders
            </Badge>
          )}
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
                        {leader.linkedin && (
                          <div className="flex items-center gap-1.5 text-xs">
                            <Linkedin className="h-3 w-3 text-blue-600" />
                            <a
                              href={leader.linkedin}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-blue-600 hover:underline"
                            >
                              LinkedIn Profile
                            </a>
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
          <div className="mt-4 flex justify-between border-t border-slate-100 pt-4">
            <Button
              variant="ghost"
              onClick={handleResearch}
              disabled={isResearching}
              className="text-amber-600 hover:bg-amber-50 hover:text-amber-700"
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
                  {firm.research_status === "completed" ? "Re-Research" : "Research Firm"}
                </>
              )}
            </Button>
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
