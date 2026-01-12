"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Download,
  FileText,
  FolderOpen,
  RefreshCw,
  Mail,
  Calendar,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Tag,
  Trash2,
  DollarSign,
  FileCheck,
} from "lucide-react";

import { ApiError, SettingsApi } from "@/lib/api";
import { MENU_ITEMS } from "../template-config/constants/template-config.constants";
import {
  Card,
  CardContent,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

// Lien types
type ConversationUpload = {
  conversation_id: string;
  file_count: number;
  files: string[];
  subject?: string;
  sender?: string;
  email_count?: number;
  latest_upload_time?: number;
};

type FileDetail = {
  filename: string;
  size: number;
  created: number;
};

type ConversationDetails = {
  tags?: string[];
};

type ResponseDetail = {
  conversation_id: string;
  hasResponse: boolean;
  message?: string;
  timestamp?: string;
  response_text?: string;
  tags_to_add?: string[];
  lien_type?: string;
  signature_type?: string;
  status?: string;
};

// Bill Balance types
type BillBalanceOutput = {
  conversation_id: string;
  timestamp: number;
  has_response: boolean;
  subject: string | null;
  sender: string | null;
  patient_id?: string;
  response_type?: string;
};

type BillBalanceResponseDetail = {
  conversation_id: string;
  timestamp: string;
  response_text: string;
  patient_id?: string;
  response_type?: string;
  details?: Record<string, unknown>;
  status: string;
};

type TabType = "liens" | "bill_balance";

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDate = (timestamp: number): string => {
  return new Date(timestamp * 1000).toLocaleString();
};

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

export default function SandboxPage() {
  // Tab state
  const [activeTab, setActiveTab] = useState<TabType>("liens");

  // Lien state
  const [conversations, setConversations] = useState<ConversationUpload[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const [fileDetails, setFileDetails] = useState<FileDetail[]>([]);
  const [conversationDetails, setConversationDetails] = useState<ConversationDetails | null>(null);
  const [responseDetails, setResponseDetails] = useState<ResponseDetail | null>(null);
  const [isLoadingLiens, setIsLoadingLiens] = useState(true);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [isClearingLiens, setIsClearingLiens] = useState(false);
  const [showClearLiensConfirm, setShowClearLiensConfirm] = useState(false);
  const [lienError, setLienError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  // Bill Balance state
  const [billBalanceOutputs, setBillBalanceOutputs] = useState<BillBalanceOutput[]>([]);
  const [selectedBillBalance, setSelectedBillBalance] = useState<string | null>(null);
  const [billBalanceResponse, setBillBalanceResponse] = useState<BillBalanceResponseDetail | null>(null);
  const [isLoadingBillBalance, setIsLoadingBillBalance] = useState(true);
  const [isLoadingBillBalanceResponse, setIsLoadingBillBalanceResponse] = useState(false);
  const [isClearingBillBalance, setIsClearingBillBalance] = useState(false);
  const [showClearBillBalanceConfirm, setShowClearBillBalanceConfirm] = useState(false);
  const [billBalanceError, setBillBalanceError] = useState<string | null>(null);

  // Load lien conversations
  const loadConversations = async () => {
    setIsLoadingLiens(true);
    setLienError(null);
    try {
      const data = await SettingsApi.getLienTestUploads();
      setConversations(data.conversations);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load lien test uploads";
      setLienError(message);
    } finally {
      setIsLoadingLiens(false);
    }
  };

  // Load bill balance outputs
  const loadBillBalanceOutputs = async () => {
    setIsLoadingBillBalance(true);
    setBillBalanceError(null);
    try {
      const data = await SettingsApi.getBillBalanceTestOutputs();
      setBillBalanceOutputs(data.conversations);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load bill balance test outputs";
      setBillBalanceError(message);
    } finally {
      setIsLoadingBillBalance(false);
    }
  };

  const loadFileDetails = async (conversationId: string) => {
    setIsLoadingFiles(true);
    setFileError(null);
    try {
      const [filesData, responseData] = await Promise.all([
        SettingsApi.getLienTestUploadsByConversation(conversationId),
        SettingsApi.getLienTestResponse(conversationId)
      ]);

      setFileDetails(filesData.files);
      setConversationDetails({ tags: filesData.tags ?? [] });
      setResponseDetails(responseData);
      setSelectedConversation(conversationId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load file details";
      setFileError(message);
    } finally {
      setIsLoadingFiles(false);
    }
  };

  const loadBillBalanceResponseDetails = async (conversationId: string) => {
    setIsLoadingBillBalanceResponse(true);
    setBillBalanceError(null);
    try {
      const data = await SettingsApi.getBillBalanceTestResponse(conversationId);
      setBillBalanceResponse(data);
      setSelectedBillBalance(conversationId);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load bill balance response";
      setBillBalanceError(message);
    } finally {
      setIsLoadingBillBalanceResponse(false);
    }
  };

  useEffect(() => {
    loadConversations();
    loadBillBalanceOutputs();
  }, []);

  const handleDownload = (conversationId: string, filename: string) => {
    const url = SettingsApi.downloadLienTestFile(conversationId, filename);
    window.open(url, "_blank");
  };

  const getFileUrl = (conversationId: string, filename: string) => {
    return SettingsApi.downloadLienTestFile(conversationId, filename);
  };

  const handleViewFile = (conversationId: string, filename: string) => {
    const url = getFileUrl(conversationId, filename);
    window.open(url, "_blank");
  };

  const handleClearAllLiens = async () => {
    setIsClearingLiens(true);
    setLienError(null);
    try {
      await SettingsApi.clearAllLienTestUploads();
      setShowClearLiensConfirm(false);
      setSelectedConversation(null);
      setFileDetails([]);
      setConversationDetails(null);
      setResponseDetails(null);
      await loadConversations();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to clear lien test uploads";
      setLienError(message);
    } finally {
      setIsClearingLiens(false);
    }
  };

  const handleClearAllBillBalance = async () => {
    setIsClearingBillBalance(true);
    setBillBalanceError(null);
    try {
      await SettingsApi.clearAllBillBalanceTestOutputs();
      setShowClearBillBalanceConfirm(false);
      setSelectedBillBalance(null);
      setBillBalanceResponse(null);
      await loadBillBalanceOutputs();
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to clear bill balance outputs";
      setBillBalanceError(message);
    } finally {
      setIsClearingBillBalance(false);
    }
  };

  const isLoading = isLoadingLiens || isLoadingBillBalance;
  const totalLienFiles = conversations.reduce((sum, conv) => sum + conv.file_count, 0);

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
              <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 animate-pulse" />
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-500 blur-lg opacity-50 animate-pulse" />
            </div>
          </div>
          <p className="text-base font-semibold text-slate-900 mb-1">Loading Sandbox</p>
          <p className="text-sm text-slate-500">Fetching test data...</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
      <nav className="grid gap-3 rounded-3xl border border-white/60 bg-white/80 p-3 shadow-xl shadow-slate-900/5 backdrop-blur lg:grid-cols-4">
        {MENU_ITEMS.map((item) => {
          const isActive = item.href === "/sandbox";
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

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={easing}
        className="flex flex-col gap-4 rounded-3xl border border-white/40 bg-gradient-to-br from-indigo-500 via-purple-500 to-sky-500 p-8 text-white shadow-2xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-white/70">EmailTag Testing</p>
            <h1 className="text-3xl font-semibold">Autorespond Sandbox</h1>
            <p className="text-white/80">
              Review test mode outputs for all autorespond types. All conversations processed in sandbox mode appear here for verification.
            </p>
          </div>
        </div>
        <div className="grid gap-3 text-sm text-white/80 sm:grid-cols-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Lien Conversations</p>
            <p className="text-lg font-semibold">{conversations.length}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Lien Files</p>
            <p className="text-lg font-semibold">{totalLienFiles}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Bill Balance Outputs</p>
            <p className="text-lg font-semibold">{billBalanceOutputs.length}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Status</p>
            <p className="text-lg font-semibold">Active</p>
          </div>
        </div>
      </motion.div>

      {/* Tab Navigation */}
      <div className="flex gap-2 p-1 rounded-xl bg-slate-100 w-fit">
        <button
          onClick={() => setActiveTab("liens")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "liens"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <FileCheck className="h-4 w-4" />
          Liens
          {conversations.length > 0 && (
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              activeTab === "liens" ? "bg-indigo-100 text-indigo-700" : "bg-slate-200 text-slate-600"
            }`}>
              {conversations.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab("bill_balance")}
          className={`flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all ${
            activeTab === "bill_balance"
              ? "bg-white text-slate-900 shadow-sm"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <DollarSign className="h-4 w-4" />
          Bill Balance
          {billBalanceOutputs.length > 0 && (
            <span className={`px-1.5 py-0.5 rounded text-xs ${
              activeTab === "bill_balance" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-600"
            }`}>
              {billBalanceOutputs.length}
            </span>
          )}
        </button>
      </div>

      {/* Liens Tab */}
      {activeTab === "liens" && (
        <>
          {/* Actions bar */}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Lien Test Uploads</h2>
            <div className="flex items-center gap-2">
              <Button
                onClick={loadConversations}
                variant="ghost"
                className="border border-slate-200 hover:bg-slate-50"
                disabled={isClearingLiens}
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
              {conversations.length > 0 && (
                <Button
                  onClick={() => setShowClearLiensConfirm(true)}
                  variant="ghost"
                  className="border border-rose-200 text-rose-600 hover:bg-rose-50"
                  disabled={isClearingLiens}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Clear All
                </Button>
              )}
            </div>
          </div>

          {lienError && <ErrorBanner message={lienError} />}

          {/* Clear Liens Confirmation Dialog */}
          {showClearLiensConfirm && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
              onClick={() => !isClearingLiens && setShowClearLiensConfirm(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={easing}
                className="mx-4 w-full max-w-md rounded-2xl border border-rose-200 bg-white p-6 shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-100">
                    <Trash2 className="h-6 w-6 text-rose-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Clear All Lien Data?</h3>
                    <p className="text-sm text-slate-600">This action cannot be undone</p>
                  </div>
                </div>
                <p className="mb-6 text-sm text-slate-700 leading-relaxed">
                  This will permanently delete all {conversations.length} conversation{conversations.length !== 1 ? "s" : ""} and their associated files ({totalLienFiles} files total) from the sandbox.
                </p>
                <div className="flex gap-3">
                  <Button
                    onClick={() => setShowClearLiensConfirm(false)}
                    variant="ghost"
                    className="flex-1 border border-slate-200 hover:bg-slate-50"
                    disabled={isClearingLiens}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleClearAllLiens}
                    className="flex-1 bg-rose-600 text-white hover:bg-rose-700"
                    disabled={isClearingLiens}
                  >
                    {isClearingLiens ? (
                      <>
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                        Clearing...
                      </>
                    ) : (
                      <>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Clear All
                      </>
                    )}
                  </Button>
                </div>
              </motion.div>
            </motion.div>
          )}

          {conversations.length === 0 && !lienError && (
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <Card className="border-dashed border-2 border-slate-200 bg-slate-50/50">
                <CardContent className="flex flex-col items-center gap-6 py-16 text-center">
                  <div className="rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 p-6">
                    <FileCheck className="h-16 w-16 text-slate-400" />
                  </div>
                  <div className="max-w-md">
                    <h3 className="text-xl font-semibold text-slate-900 mb-2">No Lien Test Data Yet</h3>
                    <p className="text-slate-600 leading-relaxed">
                      Enable lien sandbox mode in settings and process lien emails to see outputs here.
                    </p>
                  </div>
                  <Link href="/">
                    <Button variant="primary" className="mt-2">
                      Go to Settings
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            </motion.div>
          )}

          <div className="space-y-3">
            {conversations.map((conversation, index) => (
              <motion.div
                key={conversation.conversation_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...easing, delay: index * 0.05 }}
              >
                <Card className="group hover:shadow-lg hover:border-blue-200 transition-all duration-200 border border-slate-200 overflow-hidden">
                  <CardContent className="p-0">
                    <div className="p-5">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-start gap-4 flex-1 min-w-0">
                            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 via-indigo-500 to-violet-500 shadow-md group-hover:shadow-lg transition-shadow">
                              <Mail className="h-6 w-6 text-white" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <h3 className="font-semibold text-slate-900 truncate text-base mb-1">
                                {conversation.subject || conversation.conversation_id}
                              </h3>
                              <p className="text-xs font-mono text-slate-500 break-all mb-2">
                                {conversation.conversation_id}
                              </p>
                              <div className="flex items-center gap-2 text-sm text-slate-600 mb-3">
                                <span className="truncate">{conversation.sender || "Unknown sender"}</span>
                              </div>
                              <div className="flex flex-wrap items-center gap-2">
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium">
                                <FileText className="h-3.5 w-3.5" />
                                {conversation.file_count} {conversation.file_count === 1 ? "file" : "files"}
                              </div>
                              {(conversation.email_count ?? 0) > 0 && (
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-100 text-slate-700 text-xs font-medium">
                                  <Mail className="h-3.5 w-3.5" />
                                  {conversation.email_count} {conversation.email_count === 1 ? "email" : "emails"}
                                </div>
                              )}
                              {conversation.latest_upload_time && (
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 text-xs">
                                  <Calendar className="h-3.5 w-3.5" />
                                  {formatDate(conversation.latest_upload_time)}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                        <Button
                          onClick={() => loadFileDetails(conversation.conversation_id)}
                          disabled={isLoadingFiles && selectedConversation === conversation.conversation_id}
                          variant={selectedConversation === conversation.conversation_id ? "primary" : "ghost"}
                          className="shrink-0 h-10 px-4 text-sm font-medium"
                        >
                          {isLoadingFiles && selectedConversation === conversation.conversation_id ? (
                            <>
                              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                              Loading...
                            </>
                          ) : (
                            <>
                              {selectedConversation === conversation.conversation_id ? (
                                <>
                                  <ChevronUp className="mr-2 h-4 w-4" />
                                  Hide Files
                                </>
                              ) : (
                                <>
                                  <ChevronDown className="mr-2 h-4 w-4" />
                                  View Files
                                </>
                              )}
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                    {selectedConversation === conversation.conversation_id && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={easing}
                        className="border-t border-slate-100 bg-slate-50/50"
                      >
                        <div className="p-5 space-y-4">
                          {fileError && <ErrorBanner message={fileError} />}

                          {/* Current Tags */}
                          {conversationDetails && conversationDetails.tags && conversationDetails.tags.length > 0 && (
                            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
                              <div className="flex items-center gap-2 mb-2">
                                <Tag className="h-4 w-4 text-slate-500" />
                                <p className="text-sm font-semibold text-slate-900">Current Tags</p>
                              </div>
                              <div className="flex flex-wrap gap-1.5">
                                {conversationDetails.tags.map((tag, idx) => (
                                  <span
                                    key={idx}
                                    className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-slate-50 border border-slate-200 text-xs font-medium text-slate-700"
                                  >
                                    <Tag className="h-3 w-3" />
                                    {tag}
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* Response Section */}
                          {responseDetails && responseDetails.hasResponse && (
                            <motion.div
                              initial={{ opacity: 0, y: -10 }}
                              animate={{ opacity: 1, y: 0 }}
                              transition={{ delay: 0.1 }}
                              className="rounded-xl border border-blue-200 bg-gradient-to-br from-blue-50 to-indigo-50 p-5 shadow-sm"
                            >
                              <div className="flex items-start gap-3 mb-4">
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-500 text-white shadow-md">
                                  <MessageSquare className="h-5 w-5" />
                                </div>
                                <div className="flex-1">
                                  <h4 className="text-base font-semibold text-slate-900 mb-1">
                                    Generated Autorespond Message
                                  </h4>
                                  <p className="text-xs text-slate-600">
                                    This message would be sent in production mode
                                  </p>
                                </div>
                              </div>

                              {/* Tags to Add */}
                              {responseDetails.tags_to_add && responseDetails.tags_to_add.length > 0 && (
                                <div className="mb-4">
                                  <p className="text-xs font-medium text-slate-700 mb-2">Tags that would be applied:</p>
                                  <div className="flex flex-wrap gap-1.5">
                                    {responseDetails.tags_to_add.map((tag, idx) => (
                                      <span
                                        key={idx}
                                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-700 shadow-sm"
                                      >
                                        <Tag className="h-3 w-3" />
                                        {tag}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Response Message */}
                              <div className="rounded-lg bg-white border border-slate-200 p-4 shadow-sm">
                                <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
                                  Message Content:
                                </p>
                                <div className="prose prose-sm max-w-none">
                                  {responseDetails.response_text ? (
                                    <div
                                      className="text-sm text-slate-700 leading-relaxed"
                                      dangerouslySetInnerHTML={{ __html: responseDetails.response_text }}
                                    />
                                  ) : (
                                    <p className="text-sm text-slate-500">No response content available.</p>
                                  )}
                                </div>
                              </div>
                            </motion.div>
                          )}

                          {responseDetails && !responseDetails.hasResponse && (
                            <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                              <div className="flex items-center gap-2">
                                <MessageSquare className="h-4 w-4" />
                                <span className="font-medium">
                                  {responseDetails.message || "No autorespond message generated yet"}
                                </span>
                              </div>
                            </div>
                          )}

                          {/* Files Section */}
                          <div>
                            <h4 className="text-sm font-semibold text-slate-900 mb-3">Uploaded Files</h4>
                            {fileDetails.length === 0 && !fileError && (
                              <p className="text-sm text-slate-500 text-center py-4">No files found</p>
                            )}
                          {fileDetails.map((file, fileIndex) => (
                            <motion.div
                              key={file.filename}
                              initial={{ opacity: 0, x: -20 }}
                              animate={{ opacity: 1, x: 0 }}
                              transition={{ delay: fileIndex * 0.05 }}
                              className="group/file flex items-center justify-between rounded-lg border border-slate-200 bg-white p-3.5 text-sm hover:border-blue-200 hover:shadow-sm transition-all"
                            >
                              <div className="flex items-center gap-3 flex-1 min-w-0">
                                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-blue-50 text-blue-600 group-hover/file:bg-blue-100 transition-colors">
                                  <FileText className="h-5 w-5" />
                                </div>
                                <div className="flex-1 min-w-0">
                                  <p className="font-medium text-slate-900 truncate">{file.filename}</p>
                                  <p className="text-xs text-slate-500 flex items-center gap-1.5 mt-0.5">
                                    <span>{formatFileSize(file.size)}</span>
                                    <span>•</span>
                                    <span>{formatDate(file.created)}</span>
                                  </p>
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <Button
                                  variant="ghost"
                                  onClick={() => handleDownload(conversation.conversation_id, file.filename)}
                                  className="shrink-0 h-9 w-9 p-0 hover:bg-blue-50 hover:text-blue-600"
                                >
                                  <Download className="h-4 w-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  onClick={() => handleViewFile(conversation.conversation_id, file.filename)}
                                  className="shrink-0 h-9 px-3 hover:bg-blue-50 hover:text-blue-600"
                                >
                                  <FolderOpen className="h-4 w-4 mr-1" />
                                  View
                                </Button>
                              </div>
                            </motion.div>
                          ))}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </>
      )}

      {/* Bill Balance Tab */}
      {activeTab === "bill_balance" && (
        <>
          {/* Actions bar */}
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900">Bill Balance Test Outputs</h2>
            <div className="flex items-center gap-2">
              <Button
                onClick={loadBillBalanceOutputs}
                variant="ghost"
                className="border border-slate-200 hover:bg-slate-50"
                disabled={isClearingBillBalance}
              >
                <RefreshCw className="h-4 w-4 mr-2" />
                Refresh
              </Button>
              {billBalanceOutputs.length > 0 && (
                <Button
                  onClick={() => setShowClearBillBalanceConfirm(true)}
                  variant="ghost"
                  className="border border-rose-200 text-rose-600 hover:bg-rose-50"
                  disabled={isClearingBillBalance}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Clear All
                </Button>
              )}
            </div>
          </div>

          {billBalanceError && <ErrorBanner message={billBalanceError} />}

          {/* Clear Bill Balance Confirmation Dialog */}
          {showClearBillBalanceConfirm && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
              onClick={() => !isClearingBillBalance && setShowClearBillBalanceConfirm(false)}
            >
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={easing}
                className="mx-4 w-full max-w-md rounded-2xl border border-rose-200 bg-white p-6 shadow-2xl"
                onClick={(e) => e.stopPropagation()}
              >
                <div className="mb-4 flex items-center gap-3">
                  <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-rose-100">
                    <Trash2 className="h-6 w-6 text-rose-600" />
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-slate-900">Clear All Bill Balance Data?</h3>
                    <p className="text-sm text-slate-600">This action cannot be undone</p>
                  </div>
                </div>
                <p className="mb-6 text-sm text-slate-700 leading-relaxed">
                  This will permanently delete all {billBalanceOutputs.length} bill balance output{billBalanceOutputs.length !== 1 ? "s" : ""} from the sandbox.
                </p>
                <div className="flex gap-3">
                  <Button
                    onClick={() => setShowClearBillBalanceConfirm(false)}
                    variant="ghost"
                    className="flex-1 border border-slate-200 hover:bg-slate-50"
                    disabled={isClearingBillBalance}
                  >
                    Cancel
                  </Button>
                  <Button
                    onClick={handleClearAllBillBalance}
                    className="flex-1 bg-rose-600 text-white hover:bg-rose-700"
                    disabled={isClearingBillBalance}
                  >
                    {isClearingBillBalance ? (
                      <>
                        <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                        Clearing...
                      </>
                    ) : (
                      <>
                        <Trash2 className="mr-2 h-4 w-4" />
                        Clear All
                      </>
                    )}
                  </Button>
                </div>
              </motion.div>
            </motion.div>
          )}

          {billBalanceOutputs.length === 0 && !billBalanceError && (
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={easing}
            >
              <Card className="border-dashed border-2 border-slate-200 bg-slate-50/50">
                <CardContent className="flex flex-col items-center gap-6 py-16 text-center">
                  <div className="rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 p-6">
                    <DollarSign className="h-16 w-16 text-slate-400" />
                  </div>
                  <div className="max-w-md">
                    <h3 className="text-xl font-semibold text-slate-900 mb-2">No Bill Balance Test Data Yet</h3>
                    <p className="text-slate-600 leading-relaxed">
                      Enable bill balance sandbox mode in settings and process bill balance emails to see outputs here.
                    </p>
                  </div>
                  <Link href="/">
                    <Button variant="primary" className="mt-2">
                      Go to Settings
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            </motion.div>
          )}

          <div className="space-y-3">
            {billBalanceOutputs.map((output, index) => (
              <motion.div
                key={output.conversation_id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...easing, delay: index * 0.05 }}
              >
                <Card className="group hover:shadow-lg hover:border-emerald-200 transition-all duration-200 border border-slate-200 overflow-hidden">
                  <CardContent className="p-0">
                    <div className="p-5">
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex items-start gap-4 flex-1 min-w-0">
                          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-emerald-500 via-teal-500 to-cyan-500 shadow-md group-hover:shadow-lg transition-shadow">
                            <DollarSign className="h-6 w-6 text-white" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <h3 className="font-semibold text-slate-900 truncate text-base mb-1">
                              {output.subject || output.conversation_id}
                            </h3>
                            <p className="text-xs font-mono text-slate-500 break-all mb-2">
                              {output.conversation_id}
                            </p>
                            <div className="flex items-center gap-2 text-sm text-slate-600 mb-3">
                              <span className="truncate">{output.sender || "Unknown sender"}</span>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              {output.patient_id && (
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-50 text-emerald-700 text-xs font-medium">
                                  Patient: {output.patient_id}
                                </div>
                              )}
                              {output.response_type && (
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-50 text-blue-700 text-xs font-medium">
                                  {output.response_type}
                                </div>
                              )}
                              {output.timestamp && (
                                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-50 text-slate-600 text-xs">
                                  <Calendar className="h-3.5 w-3.5" />
                                  {formatDate(output.timestamp)}
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                        <Button
                          onClick={() => loadBillBalanceResponseDetails(output.conversation_id)}
                          disabled={isLoadingBillBalanceResponse && selectedBillBalance === output.conversation_id}
                          variant={selectedBillBalance === output.conversation_id ? "primary" : "ghost"}
                          className="shrink-0 h-10 px-4 text-sm font-medium"
                        >
                          {isLoadingBillBalanceResponse && selectedBillBalance === output.conversation_id ? (
                            <>
                              <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                              Loading...
                            </>
                          ) : (
                            <>
                              {selectedBillBalance === output.conversation_id ? (
                                <>
                                  <ChevronUp className="mr-2 h-4 w-4" />
                                  Hide Response
                                </>
                              ) : (
                                <>
                                  <ChevronDown className="mr-2 h-4 w-4" />
                                  View Response
                                </>
                              )}
                            </>
                          )}
                        </Button>
                      </div>
                    </div>
                    {selectedBillBalance === output.conversation_id && billBalanceResponse && (
                      <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        transition={easing}
                        className="border-t border-slate-100 bg-slate-50/50"
                      >
                        <div className="p-5 space-y-4">
                          {/* Response Details */}
                          <motion.div
                            initial={{ opacity: 0, y: -10 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 }}
                            className="rounded-xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 p-5 shadow-sm"
                          >
                            <div className="flex items-start gap-3 mb-4">
                              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-500 text-white shadow-md">
                                <MessageSquare className="h-5 w-5" />
                              </div>
                              <div className="flex-1">
                                <h4 className="text-base font-semibold text-slate-900 mb-1">
                                  Generated Bill Balance Response
                                </h4>
                                <p className="text-xs text-slate-600">
                                  This message would be sent in production mode
                                </p>
                              </div>
                            </div>

                            {/* Metadata */}
                            <div className="flex flex-wrap gap-2 mb-4">
                              {billBalanceResponse.patient_id && (
                                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-700 shadow-sm">
                                  Patient: {billBalanceResponse.patient_id}
                                </span>
                              )}
                              {billBalanceResponse.response_type && (
                                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-700 shadow-sm">
                                  Type: {billBalanceResponse.response_type}
                                </span>
                              )}
                              {billBalanceResponse.status && (
                                <span className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-white border border-slate-200 text-xs font-medium text-slate-700 shadow-sm">
                                  Status: {billBalanceResponse.status}
                                </span>
                              )}
                            </div>

                            {/* Response Message */}
                            <div className="rounded-lg bg-white border border-slate-200 p-4 shadow-sm">
                              <p className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-2">
                                Message Content:
                              </p>
                              <div className="prose prose-sm max-w-none">
                                {billBalanceResponse.response_text ? (
                                  <div
                                    className="text-sm text-slate-700 leading-relaxed"
                                    dangerouslySetInnerHTML={{ __html: billBalanceResponse.response_text }}
                                  />
                                ) : (
                                  <p className="text-sm text-slate-500">No response content available.</p>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        </div>
                      </motion.div>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
