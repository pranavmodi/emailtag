"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { SettingsApi, ReprocessApi, ApiError, ReprocessResponse } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { MENU_ITEMS } from "../template-config/constants/template-config.constants";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

type ReprocessResult = ReprocessResponse & {
  timestamp: string;
  error?: string;
};

export default function ReprocessPage() {
  const [user, setUser] = useState<string>("Admin");
  const [isLoading, setIsLoading] = useState(true);
  const [conversationId, setConversationId] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [results, setResults] = useState<ReprocessResult[]>([]);
  const [error, setError] = useState<string | null>(null);

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
        setError(error instanceof Error ? error.message : "Failed to load");
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  const handleReprocess = async () => {
    if (!conversationId.trim()) {
      setError("Please enter a conversation ID");
      return;
    }

    setIsProcessing(true);
    setError(null);

    try {
      const response = await ReprocessApi.reprocessConversation(conversationId.trim());

      const result: ReprocessResult = {
        ...response,
        timestamp: new Date().toLocaleTimeString(),
      };

      setResults((prev) => [result, ...prev]);
      setConversationId("");
    } catch (err) {
      const errorMessage = err instanceof ApiError
        ? `Error ${err.status}: ${err.message}`
        : err instanceof Error
          ? err.message
          : "Failed to reprocess conversation";

      setResults((prev) => [{
        status: "created_but_not_queued" as const,
        email_id: "",
        conversation_id: conversationId,
        timestamp: new Date().toLocaleTimeString(),
        error: errorMessage,
      }, ...prev]);
    } finally {
      setIsProcessing(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !isProcessing) {
      handleReprocess();
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-3 text-slate-500">
          <svg
            className="h-5 w-5 animate-spin"
            viewBox="0 0 24 24"
            fill="none"
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
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
      {/* Navigation */}
      <nav className="grid gap-3 rounded-3xl border border-white/60 bg-white/80 p-3 shadow-xl shadow-slate-900/5 backdrop-blur sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
        {MENU_ITEMS.map((item) => {
          const isActive = item.href === "/reprocess";
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`group flex flex-col gap-1 rounded-2xl px-4 py-3 transition-all ${
                isActive
                  ? "bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-lg"
                  : "hover:bg-slate-50"
              }`}
            >
              <span className="text-lg">{item.icon}</span>
              <span
                className={`text-sm font-medium ${isActive ? "text-white" : "text-slate-700"}`}
              >
                {item.label}
              </span>
              <span
                className={`text-xs ${isActive ? "text-white/80" : "text-slate-400"}`}
              >
                {item.description}
              </span>
            </Link>
          );
        })}
      </nav>

      {/* Hero Section */}
      <motion.section
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...easing }}
        className="text-center"
      >
        <h1 className="bg-gradient-to-r from-indigo-600 to-purple-600 bg-clip-text text-4xl font-bold tracking-tight text-transparent">
          Reprocess Conversation
        </h1>
        <p className="mt-2 text-slate-500">
          Manually trigger processing for a Front conversation by ID
        </p>
      </motion.section>

      {/* Main Input Card */}
      <motion.section
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...easing, delay: 0.05 }}
      >
        <Card className="overflow-hidden rounded-3xl border-0 bg-white shadow-xl shadow-slate-900/5">
          <CardHeader className="border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-6 py-5">
            <CardTitle className="flex items-center gap-3 text-lg font-semibold text-slate-800">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 text-xl">
                🔄
              </span>
              Enter Conversation ID
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <div className="flex flex-col gap-4 sm:flex-row">
              <input
                type="text"
                value={conversationId}
                onChange={(e) => setConversationId(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="cnv_xxxxxxxxxx"
                className="flex-1 rounded-xl border border-slate-200 px-4 py-3 text-slate-700 placeholder-slate-400 outline-none transition-all focus:border-indigo-300 focus:ring-2 focus:ring-indigo-100"
                disabled={isProcessing}
              />
              <Button
                onClick={handleReprocess}
                disabled={isProcessing || !conversationId.trim()}
                className="rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 px-6 py-3 font-medium text-white shadow-lg transition-all hover:shadow-xl disabled:opacity-50"
              >
                {isProcessing ? (
                  <span className="flex items-center gap-2">
                    <svg
                      className="h-4 w-4 animate-spin"
                      viewBox="0 0 24 24"
                      fill="none"
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
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                      />
                    </svg>
                    Processing...
                  </span>
                ) : (
                  "Reprocess"
                )}
              </Button>
            </div>
            {error && (
              <p className="mt-3 text-sm text-rose-600">{error}</p>
            )}
            <p className="mt-4 text-sm text-slate-500">
              This will fetch the conversation from Front, create a new email record, and queue it for processing as if it were a new inbound message.
            </p>
          </CardContent>
        </Card>
      </motion.section>

      {/* Results Section */}
      {results.length > 0 && (
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.1 }}
        >
          <Card className="overflow-hidden rounded-3xl border-0 bg-white shadow-xl shadow-slate-900/5">
            <CardHeader className="border-b border-slate-100 bg-gradient-to-r from-slate-50 to-white px-6 py-5">
              <div className="flex items-center justify-between">
                <CardTitle className="flex items-center gap-3 text-lg font-semibold text-slate-800">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-100 text-xl">
                    📋
                  </span>
                  Results
                </CardTitle>
                <button
                  onClick={() => setResults([])}
                  className="text-sm text-slate-500 hover:text-slate-700"
                >
                  Clear all
                </button>
              </div>
            </CardHeader>
            <CardContent className="p-6">
              <div className="flex flex-col gap-3">
                {results.map((result, index) => (
                  <div
                    key={`${result.conversation_id}-${index}`}
                    className={`rounded-xl border p-4 ${
                      result.error
                        ? "border-rose-200 bg-rose-50"
                        : result.status === "queued"
                          ? "border-emerald-200 bg-emerald-50"
                          : "border-amber-200 bg-amber-50"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                              result.error
                                ? "bg-rose-100 text-rose-700"
                                : result.status === "queued"
                                  ? "bg-emerald-100 text-emerald-700"
                                  : "bg-amber-100 text-amber-700"
                            }`}
                          >
                            {result.error ? "Error" : result.status === "queued" ? "Queued" : "Not Queued"}
                          </span>
                          <span className="text-xs text-slate-500">{result.timestamp}</span>
                        </div>
                        <p className="mt-2 font-mono text-sm text-slate-700">
                          {result.conversation_id}
                        </p>
                        {result.error ? (
                          <p className="mt-1 text-sm text-rose-600">{result.error}</p>
                        ) : (
                          <>
                            {result.subject && (
                              <p className="mt-1 text-sm text-slate-600">
                                <span className="font-medium">Subject:</span> {result.subject}
                              </p>
                            )}
                            {result.sender && (
                              <p className="text-sm text-slate-600">
                                <span className="font-medium">Sender:</span> {result.sender}
                              </p>
                            )}
                            {result.email_id && (
                              <p className="text-sm text-slate-500">
                                <span className="font-medium">Email ID:</span>{" "}
                                <span className="font-mono text-xs">{result.email_id}</span>
                              </p>
                            )}
                            {result.reason && (
                              <p className="mt-1 text-sm text-amber-600">
                                <span className="font-medium">Reason:</span> {result.reason}
                              </p>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </motion.section>
      )}

      {/* Footer */}
      <motion.footer
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ ...easing, delay: 0.15 }}
        className="text-center text-sm text-slate-400"
      >
        Logged in as <span className="font-medium text-slate-600">{user}</span>
      </motion.footer>
    </div>
  );
}
