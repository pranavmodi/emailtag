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
} from "lucide-react";

import { ApiError, PifApi } from "@/lib/api";
import type { PifInfoResponse, PifInfoListResponse, ProcessDayResponse, ResearchStatusResponse, OutreachMessageResult } from "@/lib/types";
import { ResearchModal } from "./ResearchModal";
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
  const [researchModalFirm, setResearchModalFirm] = useState<PifInfoResponse | null>(null);

  // Process day state
  const [processDate, setProcessDate] = useState(() => {
    const today = new Date();
    return today.toISOString().split("T")[0];
  });
  const [isProcessing, setIsProcessing] = useState(false);
  const [processResult, setProcessResult] = useState<ProcessDayResponse | null>(null);


  // Tab state
  const [activeTab, setActiveTab] = useState<"pif" | "outreach" | "outgen">("pif");

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

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      if (!isAuthenticated) {
        setIsLoading(false);
        return;
      }

      try {
        await Promise.all([fetchData(), fetchResearchedFirms()]);
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

                  {/* Sort Selector */}
                  <div className="flex items-center gap-2">
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
  const [copied, setCopied] = useState(false);
  const selectedFirm = researchedFirms.find((f) => f.id === outgenFirmId);

  const generatePrompt = () => {
    if (!selectedFirm) return "";

    const leaders = selectedFirm.leadership || [];
    const leadersInfo = leaders.map((leader, idx) => {
      const parts = [`Leader ${idx + 1}:`];
      parts.push(`  Name: ${leader.name}`);
      parts.push(`  Title: ${leader.title}`);
      if (leader.email) parts.push(`  Email: ${leader.email}`);
      if (leader.linkedin) parts.push(`  LinkedIn: ${leader.linkedin}`);
      if (leader.bio) parts.push(`  Bio: ${leader.bio}`);
      if (leader.education?.length) parts.push(`  Education: ${leader.education.join(", ")}`);
      if (leader.experience?.length) parts.push(`  Experience: ${leader.experience.join("; ")}`);
      if (leader.skills?.length) parts.push(`  Skills: ${leader.skills.join(", ")}`);
      if (leader.certifications?.length) parts.push(`  Certifications: ${leader.certifications.join(", ")}`);
      if (leader.cases_handled?.length) parts.push(`  Notable Cases: ${leader.cases_handled.join("; ")}`);
      if (leader.bar_admissions?.length) parts.push(`  Bar Admissions: ${leader.bar_admissions.join(", ")}`);
      return parts.join("\n");
    }).join("\n\n");

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

    const mutualClientSection = `
- Mutual client: Precise Imaging
- Mutual client relationship: PI firms send their clients to Precise Imaging, and Precise works on a lien basis, so they send back signed liens
- Did mutual client approve outreach reference? ${outgenMutualApproved ? "YES" : "NO"}
- Specific results mutual client experienced that benefit prospect: Faster records responses, automated lien handling, cleaner documentation back to attorneys`;

    return `Generate LinkedIn outreach messages for the leadership team at the following firm.

### For each leader, create 8 outputs (a unique subject line for each message):
1. **Subject line for short Pranav message** - Personalized, business-outcome angle
2. **Short message from Pranav Modi (founder)** - Under 300 characters, hooks interest with a relevant problem/result
3. **Subject line for short Neha message** - Personalized, technical angle
4. **Short message from Neha Pipada (engineer)** - Under 300 characters, slightly more technical angle
5. **Subject line for long Pranav message** - Personalized, hints at mutual connection or business pain point
6. **Long message from Pranav Modi** - Under 450 characters, warm, personalized opening, relevant connection, soft CTA
7. **Subject line for long Neha message** - Personalized, hints at technical relevance or problem-solving
8. **Long message from Neha Pipada** - Under 450 characters, technical credibility, relevant proof point, soft CTA

---

### Guidelines:

**Research first:**
- Read the case study URL provided
- If available, also check for industry-specific case studies (e.g., /law-case-study for law firms)
- Search for and find the LinkedIn profile URL for each leader (include the link in your output)
- Identify which of our solutions is MOST relevant to this firm's likely pain points

**Personalization requirements:**
- Reference something specific from their bio (not just "20 years of experience"; dig deeper)
- For solo practitioners: focus on time savings, missed opportunities, after-hours coverage
- For larger firms: focus on staff efficiency, cost savings, scalability
- Avoid generic claims like "your clients may have visited"; find a stronger connection or don't force one
- Reference specific details from their operation (office locations by name, team size, practice areas)

**Mutual client connections (HIGHEST PRIORITY):**
If a mutual client relationship exists:
- Lead with the connection in subject lines and opening sentences
- Name the mutual client explicitly (if approved)
- Explain the business relationship between prospect and mutual client
- Connect case study results to how it benefits the prospect's workflow
- Use subject lines like "[Client Name] asked me to reach out" or "From the team behind [Client Name]'s system" (only if client approved the outreach)
- If client didn't explicitly approve, use softer framing: "We work with [Client Name]" or "Your [partner/vendor]'s AI system"

**Message structure (IMPORTANT):**
- Lead with THEIR pain or situation, not our solution
- Structure: Pain point > Validation > Proof > Soft CTA
- Bad: "We helped an imaging center save 670 hours..."
- Good: "With 7 offices across California, I'm curious how you handle intake when your team's offline. We helped..."

**Case study bridging:**
- If case study is from a different industry, explicitly bridge the relevance
- Bad: Showing healthcare results to a law firm without explanation
- Good: "Different industry, same problem: high volume, multiple locations, leads slipping through"
- Better: If mutual client exists, no bridge needed; the connection speaks for itself
- For PI firms specifically: highlight lien document handling, records requests, attorney communication speed

**Subject line rules:**
- Keep under 6 words when possible
- Be specific to the prospect (use their name, company, or location)
- Create curiosity or imply existing relationship
- Bad: "How we automated 24/7 intake without losing the human touch" (too long, generic)
- Good: "After-hours leads at [Firm Name]"
- Good: "[Mutual Client] asked me to reach out"
- Good: "Intake across 7 locations"

**Tone & Differentiation:**
- Pranav: Founder, empathetic, business-outcome focused, peer-to-peer. Focus on ROI, growth, client acquisition, business impact, scaling challenges.
- Neha: Engineer, curious, technically credible, problem-solver. Focus on how it works, implementation ease, technical innovation.
- IMPORTANT: Pranav and Neha's messages must take DIFFERENT angles; don't just rephrase the same message. Pranav should highlight business outcomes while Neha should highlight technical approach or problem-solving methodology.
- Neha's messages MUST include specific technical details:
  - Response latency (e.g., "sub-3-second voice latency")
  - Specific technologies (e.g., "real-time speech recognition", "OCR for document extraction")
  - Architecture details (e.g., "location-aware responses", "warm handoffs with full context")
  - Feature specifics (e.g., "signature detection", "fraud flagging for altered documents")
- Both: Warm, not salesy. End with low-pressure CTA ("happy to share what we learned" not "let's book a call")

**Case study link requirement:**
- EVERY message (short and long) MUST include the case study URL; no exceptions
- The URL should be woven naturally into the message (e.g., "here's what we found: [URL]" or "we documented the results here: [URL]")

**CTA variations (rotate across messages):**
- "Happy to share what transferred"
- "Curious if you've explored this"
- "Worth a look if this resonates"
- "Happy to walk through the architecture"
- "Let me know if you want the technical specs"
- Avoid using the same CTA for all 4 messages

**What to avoid:**
- Generic subject lines that could apply to anyone or reusing the same subject line across messages
- Forcing a "mutual connection" that doesn't really exist
- Metrics that don't resonate with their firm size
- Focusing on what WE did vs. what THEY struggle with
- Using healthcare case studies for law firms without bridging relevance (unless mutual client)
- Omitting the case study URL from any message
- Using em dashes anywhere. Use commas, periods, or semicolons instead
- Leading with "We helped..." instead of their situation
- Vague technical claims for Neha (e.g., "smart AI" without specifics)
- Subject lines over 6 words
- Abrupt transitions from personalization to pitch

---

### Context:
- Case study URL (primary): ${outgenCaseStudyUrl}${mutualClientSection}
${outgenInstructions ? `\n### Additional Instructions:\n${outgenInstructions}\n` : ""}
---

### Firm Information:
${firmInfo}

### Leadership Team:
${leadersInfo || "No leadership data available."}`;
  };

  const handleCopy = async () => {
    const prompt = generatePrompt();
    await navigator.clipboard.writeText(prompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const prompt = generatePrompt();
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

          {/* Copy Button */}
          <Button
            onClick={handleCopy}
            disabled={!canCopy}
            className="flex items-center gap-2"
          >
            {copied ? (
              <>
                <Check className="h-4 w-4" />
                Copied!
              </>
            ) : (
              <>
                <Copy className="h-4 w-4" />
                Copy Prompt to Clipboard
              </>
            )}
          </Button>
        </CardContent>
      </Card>

      {/* Preview */}
      {canCopy && (
        <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-lg">Prompt Preview</CardTitle>
              <CopyButton text={prompt} label="Copy" />
            </div>
          </CardHeader>
          <CardContent>
            <pre className="max-h-96 overflow-auto rounded-lg border border-slate-100 bg-slate-50 p-4 text-xs text-slate-700 whitespace-pre-wrap">
              {prompt}
            </pre>
          </CardContent>
        </Card>
      )}
    </motion.section>
  );
}
