"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Send,
  Mail,
  RefreshCw,
  Check,
  X,
  AlertCircle,
  Tag,
  Paperclip,
  Search,
  CheckSquare,
  Square,
  ChevronDown,
  ChevronUp,
  Inbox,
} from "lucide-react";

import { ApiError, SettingsApi } from "@/lib/api";
import { Header } from "@/components/layout/Header";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import type { TestEmailScenario, SendTestEmailResult } from "@/lib/types";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

type ScenariosByType = Record<string, Record<string, TestEmailScenario>>;

const ErrorBanner = ({ message }: { message: string }) => (
  <motion.div
    initial={{ opacity: 0, y: -10 }}
    animate={{ opacity: 1, y: 0 }}
    className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700 font-medium shadow-sm"
  >
    <div className="flex items-center gap-2">
      <div className="h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
      {message}
    </div>
  </motion.div>
);

const SuccessBanner = ({ message }: { message: string }) => (
  <motion.div
    initial={{ opacity: 0, y: -10 }}
    animate={{ opacity: 1, y: 0 }}
    className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 font-medium shadow-sm"
  >
    <div className="flex items-center gap-2">
      <Check className="h-4 w-4 text-emerald-600" />
      {message}
    </div>
  </motion.div>
);

export default function TestEmailsPage() {
  const [user, setUser] = useState<string>("Admin");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Data state
  const [scenarios, setScenarios] = useState<ScenariosByType>({});
  const [types, setTypes] = useState<Record<string, string>>({});
  const [smtpConfigured, setSmtpConfigured] = useState(false);
  const [recipientEmail, setRecipientEmail] = useState<string | null>(null);

  // UI state
  const [selectedType, setSelectedType] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedScenarios, setSelectedScenarios] = useState<Set<string>>(new Set());
  const [expandedTypes, setExpandedTypes] = useState<Set<string>>(new Set());
  const [isSending, setIsSending] = useState(false);
  const [sendResults, setSendResults] = useState<SendTestEmailResult[]>([]);

  // Load scenarios
  const loadScenarios = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await SettingsApi.getTestEmailScenarios();
      setScenarios(data.scenarios);
      setTypes(data.types);
      setSmtpConfigured(data.smtp_configured);
      setRecipientEmail(data.recipient_email);

      // Expand all types by default
      setExpandedTypes(new Set(Object.keys(data.scenarios)));
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to load test scenarios";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  // Auth check
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const auth = await SettingsApi.getAuthStatus();
        if (!auth.authenticated) {
          window.location.href = "/login";
          return;
        }
        setUser(auth.username ?? "Admin");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
        }
      }
    };
    checkAuth();
    loadScenarios();
  }, []);

  // Get all scenarios as a flat list
  const getAllScenarios = (): TestEmailScenario[] => {
    const all: TestEmailScenario[] = [];
    for (const typeScenarios of Object.values(scenarios)) {
      for (const scenario of Object.values(typeScenarios)) {
        all.push(scenario);
      }
    }
    return all;
  };

  // Filter scenarios based on search and type
  const getFilteredScenarios = (): ScenariosByType => {
    const filtered: ScenariosByType = {};
    const query = searchQuery.toLowerCase();

    for (const [typeKey, typeScenarios] of Object.entries(scenarios)) {
      if (selectedType !== "all" && selectedType !== typeKey) {
        continue;
      }

      const matchingScenarios: Record<string, TestEmailScenario> = {};
      for (const [key, scenario] of Object.entries(typeScenarios)) {
        if (!query) {
          matchingScenarios[key] = scenario;
          continue;
        }

        const matches =
          scenario.description.toLowerCase().includes(query) ||
          scenario.subject.toLowerCase().includes(query) ||
          scenario.expected_tags.some(tag => tag.toLowerCase().includes(query)) ||
          key.includes(query);

        if (matches) {
          matchingScenarios[key] = scenario;
        }
      }

      if (Object.keys(matchingScenarios).length > 0) {
        filtered[typeKey] = matchingScenarios;
      }
    }

    return filtered;
  };

  // Toggle scenario selection
  const toggleScenario = (key: string) => {
    const newSelected = new Set(selectedScenarios);
    if (newSelected.has(key)) {
      newSelected.delete(key);
    } else {
      newSelected.add(key);
    }
    setSelectedScenarios(newSelected);
  };

  // Select all visible scenarios
  const selectAll = () => {
    const filtered = getFilteredScenarios();
    const allKeys = new Set<string>();
    for (const typeScenarios of Object.values(filtered)) {
      for (const key of Object.keys(typeScenarios)) {
        allKeys.add(key);
      }
    }
    setSelectedScenarios(allKeys);
  };

  // Clear selection
  const clearSelection = () => {
    setSelectedScenarios(new Set());
  };

  // Toggle type expansion
  const toggleTypeExpanded = (typeKey: string) => {
    const newExpanded = new Set(expandedTypes);
    if (newExpanded.has(typeKey)) {
      newExpanded.delete(typeKey);
    } else {
      newExpanded.add(typeKey);
    }
    setExpandedTypes(newExpanded);
  };

  // Send selected emails
  const handleSendSelected = async () => {
    if (selectedScenarios.size === 0) return;

    setIsSending(true);
    setError(null);
    setSuccessMessage(null);
    setSendResults([]);

    try {
      const scenarioKeys = Array.from(selectedScenarios);
      const response = await SettingsApi.sendTestEmails(scenarioKeys);
      setSendResults(response.results);

      const successCount = response.results.filter(r => r.status === "success").length;
      if (successCount === scenarioKeys.length) {
        setSuccessMessage(`All ${successCount} test email(s) sent successfully!`);
      } else if (successCount > 0) {
        setSuccessMessage(`${successCount} of ${scenarioKeys.length} test email(s) sent. Check results for details.`);
      } else {
        setError("Failed to send any test emails. Check results for details.");
      }

      // Clear selection after successful send
      setSelectedScenarios(new Set());
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message = err instanceof Error ? err.message : "Failed to send test emails";
      setError(message);
    } finally {
      setIsSending(false);
    }
  };

  const filteredScenarios = getFilteredScenarios();
  const totalScenarios = getAllScenarios().length;
  const visibleScenarioCount = Object.values(filteredScenarios).reduce(
    (acc, ts) => acc + Object.keys(ts).length,
    0
  );

  if (isLoading) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16">
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={easing}
          className="rounded-2xl border border-slate-200 bg-white px-12 py-16 text-center shadow-xl"
        >
          <div className="flex items-center justify-center mb-4">
            <div className="relative">
              <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-500 animate-pulse" />
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-cyan-500 to-blue-500 blur-lg opacity-50 animate-pulse" />
            </div>
          </div>
          <p className="text-base font-semibold text-slate-900 mb-1">Loading Test Scenarios</p>
          <p className="text-sm text-slate-500">Fetching available test emails...</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header user={user} currentPage={{ label: "Test Emails", icon: "📧" }} />

      <main className="mx-auto flex max-w-6xl flex-col gap-8 px-6 py-10">
        {/* Hero Section */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="flex flex-col gap-4 rounded-3xl border border-white/40 bg-gradient-to-br from-cyan-500 via-blue-500 to-indigo-500 p-8 text-white shadow-2xl"
        >
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-white/70">EmailTag Testing</p>
              <h1 className="text-3xl font-semibold">Test Email Scenarios</h1>
              <p className="text-white/80">
                Send test emails to trigger email processing workflows. Select scenarios and send them to your configured recipient.
              </p>
            </div>
          </div>
          <div className="grid gap-3 text-sm text-white/80 sm:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-white/60">Total Scenarios</p>
              <p className="text-lg font-semibold">{totalScenarios}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-white/60">Categories</p>
              <p className="text-lg font-semibold">{Object.keys(types).length}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-white/60">SMTP Status</p>
              <p className="text-lg font-semibold flex items-center gap-2">
                {smtpConfigured ? (
                  <>
                    <Check className="h-4 w-4" />
                    Configured
                  </>
                ) : (
                  <>
                    <X className="h-4 w-4" />
                    Not Configured
                  </>
                )}
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-white/60">Recipient</p>
              <p className="text-lg font-semibold truncate">{recipientEmail || "Not Set"}</p>
            </div>
          </div>
        </motion.div>

        {/* SMTP Warning */}
        {!smtpConfigured && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800"
          >
            <div className="flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
              <div>
                <p className="font-medium">SMTP Not Configured</p>
                <p className="text-amber-700">
                  Set SMTP_HOST, SMTP_PORT, SENDER_EMAIL, SENDER_PASSWORD, and DEFAULT_RECIPIENT_EMAIL environment variables to enable sending test emails.
                </p>
              </div>
            </div>
          </motion.div>
        )}

        {/* Messages */}
        {error && <ErrorBanner message={error} />}
        {successMessage && <SuccessBanner message={successMessage} />}

        {/* Send Results */}
        {sendResults.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
          >
            <h3 className="text-sm font-semibold text-slate-900 mb-3">Send Results</h3>
            <div className="space-y-2">
              {sendResults.map((result, idx) => (
                <div
                  key={idx}
                  className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm ${
                    result.status === "success"
                      ? "bg-emerald-50 text-emerald-800"
                      : "bg-rose-50 text-rose-800"
                  }`}
                >
                  <div className="flex items-center gap-2">
                    {result.status === "success" ? (
                      <Check className="h-4 w-4 text-emerald-600" />
                    ) : (
                      <X className="h-4 w-4 text-rose-600" />
                    )}
                    <span className="font-mono">Scenario {result.scenario_key}</span>
                  </div>
                  <span className="text-xs">{result.message}</span>
                </div>
              ))}
            </div>
            <Button
              onClick={() => setSendResults([])}
              variant="ghost"
              className="mt-3 text-sm"
            >
              Dismiss Results
            </Button>
          </motion.div>
        )}

        {/* Controls */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Button
              onClick={loadScenarios}
              variant="ghost"
              className="border border-slate-200 hover:bg-slate-50"
              disabled={isSending}
            >
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
            <Button
              onClick={selectAll}
              variant="ghost"
              className="border border-slate-200 hover:bg-slate-50"
              disabled={isSending}
            >
              <CheckSquare className="h-4 w-4 mr-2" />
              Select All ({visibleScenarioCount})
            </Button>
            {selectedScenarios.size > 0 && (
              <Button
                onClick={clearSelection}
                variant="ghost"
                className="border border-slate-200 hover:bg-slate-50"
                disabled={isSending}
              >
                <Square className="h-4 w-4 mr-2" />
                Clear ({selectedScenarios.size})
              </Button>
            )}
          </div>
          <Button
            onClick={handleSendSelected}
            disabled={selectedScenarios.size === 0 || isSending || !smtpConfigured}
            className="bg-gradient-to-r from-cyan-500 to-blue-500 text-white hover:from-cyan-600 hover:to-blue-600 disabled:opacity-50"
          >
            {isSending ? (
              <>
                <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                Sending...
              </>
            ) : (
              <>
                <Send className="h-4 w-4 mr-2" />
                Send Selected ({selectedScenarios.size})
              </>
            )}
          </Button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Type Filter */}
          <div className="flex gap-2 p-1 rounded-xl bg-slate-100 overflow-x-auto">
            <button
              onClick={() => setSelectedType("all")}
              className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                selectedType === "all"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Inbox className="h-4 w-4" />
              All
            </button>
            {Object.entries(types).map(([typeKey, typeLabel]) => {
              const count = scenarios[typeKey] ? Object.keys(scenarios[typeKey]).length : 0;
              if (count === 0) return null;
              return (
                <button
                  key={typeKey}
                  onClick={() => setSelectedType(typeKey)}
                  className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-all whitespace-nowrap ${
                    selectedType === typeKey
                      ? "bg-white text-slate-900 shadow-sm"
                      : "text-slate-600 hover:text-slate-900"
                  }`}
                >
                  {typeLabel}
                  <span className={`px-1.5 py-0.5 rounded text-xs ${
                    selectedType === typeKey ? "bg-blue-100 text-blue-700" : "bg-slate-200 text-slate-600"
                  }`}>
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[200px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search scenarios..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-10 py-2.5 rounded-xl border border-slate-200 bg-white text-sm text-slate-700 placeholder-slate-400 outline-none transition-all focus:border-blue-300 focus:ring-2 focus:ring-blue-100"
            />
            {searchQuery && (
              <button
                onClick={() => setSearchQuery("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>

        {/* Scenarios List */}
        {Object.keys(filteredScenarios).length === 0 ? (
          <motion.div
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={easing}
          >
            <Card className="border-dashed border-2 border-slate-200 bg-slate-50/50">
              <CardContent className="flex flex-col items-center gap-6 py-16 text-center">
                <div className="rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 p-6">
                  {searchQuery ? <Search className="h-16 w-16 text-slate-400" /> : <Mail className="h-16 w-16 text-slate-400" />}
                </div>
                <div className="max-w-md">
                  <h3 className="text-xl font-semibold text-slate-900 mb-2">
                    {searchQuery ? "No Matching Scenarios" : "No Test Scenarios Available"}
                  </h3>
                  <p className="text-slate-600 leading-relaxed">
                    {searchQuery
                      ? `No scenarios match "${searchQuery}". Try a different search term.`
                      : "No test scenarios could be loaded. Check the scenarios configuration."
                    }
                  </p>
                </div>
                {searchQuery && (
                  <Button variant="ghost" className="mt-2 border border-slate-200" onClick={() => setSearchQuery("")}>
                    Clear Search
                  </Button>
                )}
              </CardContent>
            </Card>
          </motion.div>
        ) : (
          <div className="space-y-4">
            {Object.entries(filteredScenarios).map(([typeKey, typeScenarios], typeIndex) => (
              <motion.div
                key={typeKey}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...easing, delay: typeIndex * 0.05 }}
              >
                <Card className="border border-slate-200 overflow-hidden">
                  <button
                    onClick={() => toggleTypeExpanded(typeKey)}
                    className="w-full flex items-center justify-between p-4 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-500 flex items-center justify-center text-white">
                        <Mail className="h-4 w-4" />
                      </div>
                      <div>
                        <h3 className="font-semibold text-slate-900">{types[typeKey] || typeKey}</h3>
                        <p className="text-sm text-slate-500">{Object.keys(typeScenarios).length} scenarios</p>
                      </div>
                    </div>
                    {expandedTypes.has(typeKey) ? (
                      <ChevronUp className="h-5 w-5 text-slate-400" />
                    ) : (
                      <ChevronDown className="h-5 w-5 text-slate-400" />
                    )}
                  </button>

                  {expandedTypes.has(typeKey) && (
                    <CardContent className="p-0">
                      <div className="divide-y divide-slate-100">
                        {Object.entries(typeScenarios).map(([key, scenario]) => (
                          <div
                            key={key}
                            onClick={() => toggleScenario(key)}
                            className={`flex items-start gap-4 p-4 cursor-pointer transition-colors ${
                              selectedScenarios.has(key)
                                ? "bg-blue-50 hover:bg-blue-100"
                                : "hover:bg-slate-50"
                            }`}
                          >
                            <div className="mt-0.5">
                              {selectedScenarios.has(key) ? (
                                <CheckSquare className="h-5 w-5 text-blue-600" />
                              ) : (
                                <Square className="h-5 w-5 text-slate-400" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-mono bg-slate-100 px-2 py-0.5 rounded text-slate-600">
                                  #{key}
                                </span>
                                {scenario.has_attachments && (
                                  <span className="flex items-center gap-1 text-xs bg-amber-100 text-amber-700 px-2 py-0.5 rounded">
                                    <Paperclip className="h-3 w-3" />
                                    Attachments
                                  </span>
                                )}
                              </div>
                              <h4 className="text-sm font-medium text-slate-900 mb-1">
                                {scenario.subject}
                              </h4>
                              <p className="text-sm text-slate-600 mb-2">
                                {scenario.description}
                              </p>
                              {scenario.expected_tags.length > 0 && (
                                <div className="flex flex-wrap gap-1.5">
                                  {scenario.expected_tags.map((tag, idx) => (
                                    <span
                                      key={idx}
                                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700"
                                    >
                                      <Tag className="h-3 w-3" />
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  )}
                </Card>
              </motion.div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
