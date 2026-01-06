"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Download,
  FileText,
  FolderOpen,
  Home,
  RefreshCw,
  Mail,
  Calendar,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

import { ApiError, SettingsApi } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

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

export default function LienTestPage() {
  const [conversations, setConversations] = useState<ConversationUpload[]>([]);
  const [selectedConversation, setSelectedConversation] = useState<string | null>(null);
  const [fileDetails, setFileDetails] = useState<FileDetail[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingFiles, setIsLoadingFiles] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);

  const loadConversations = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await SettingsApi.getLienTestUploads();
      setConversations(data.conversations);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to load test uploads";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  const loadFileDetails = async (conversationId: string) => {
    setIsLoadingFiles(true);
    setFileError(null);
    try {
      const data = await SettingsApi.getLienTestUploadsByConversation(conversationId);
      setFileDetails(data.files);
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

  useEffect(() => {
    loadConversations();
  }, []);

  const handleDownload = (conversationId: string, filename: string) => {
    const url = SettingsApi.downloadLienTestFile(conversationId, filename);
    window.open(url, "_blank");
  };

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
              <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-blue-500 to-violet-500 animate-pulse" />
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-blue-500 to-violet-500 blur-lg opacity-50 animate-pulse" />
            </div>
          </div>
          <p className="text-base font-semibold text-slate-900 mb-1">Loading Test Uploads</p>
          <p className="text-sm text-slate-500">Fetching conversation data...</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-6 py-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={easing}
        className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-blue-600 via-indigo-600 to-violet-600 p-8 shadow-xl"
      >
        <div className="absolute inset-0 bg-grid-white/5 [mask-image:linear-gradient(0deg,white,rgba(255,255,255,0.5))]" />
        <div className="relative">
          <div className="flex flex-wrap items-start justify-between gap-6">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-2">
                <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-white/10 backdrop-blur-sm ring-1 ring-white/20">
                  <FileText className="h-6 w-6 text-white" />
                </div>
                <div>
                  <p className="text-xs font-medium uppercase tracking-wider text-white/60">Lien Testing</p>
                  <h1 className="text-3xl font-bold text-white">Test Upload Sandbox</h1>
                </div>
              </div>
              <p className="text-white/90 max-w-2xl">
                Review and download lien documents uploaded in test mode. All uploads are organized by conversation for easy tracking.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Link href="/">
                <Button
                  variant="ghost"
                  className="bg-white/10 backdrop-blur-sm text-white hover:bg-white/20 border-0 shadow-lg"
                >
                  <Home className="h-4 w-4" />
                  Settings
                </Button>
              </Link>
              <Button
                onClick={loadConversations}
                variant="ghost"
                className="bg-white/10 backdrop-blur-sm text-white hover:bg-white/20 border-0 shadow-lg"
              >
                <RefreshCw className="h-4 w-4" />
                Refresh
              </Button>
            </div>
          </div>
          <div className="mt-6 grid gap-4 sm:grid-cols-3">
            <div className="rounded-xl bg-white/10 backdrop-blur-sm p-4 ring-1 ring-white/20">
              <p className="text-xs font-medium uppercase tracking-wide text-white/70">Conversations</p>
              <p className="text-2xl font-bold text-white mt-1">{conversations.length}</p>
            </div>
            <div className="rounded-xl bg-white/10 backdrop-blur-sm p-4 ring-1 ring-white/20">
              <p className="text-xs font-medium uppercase tracking-wide text-white/70">Total Files</p>
              <p className="text-2xl font-bold text-white mt-1">
                {conversations.reduce((sum, conv) => sum + conv.file_count, 0)}
              </p>
            </div>
            <div className="rounded-xl bg-white/10 backdrop-blur-sm p-4 ring-1 ring-white/20">
              <p className="text-xs font-medium uppercase tracking-wide text-white/70">Status</p>
              <p className="text-2xl font-bold text-white mt-1">Active</p>
            </div>
          </div>
        </div>
      </motion.div>

      {error && <ErrorBanner message={error} />}

      {conversations.length === 0 && !error && (
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
        >
          <Card className="border-dashed border-2 border-slate-200 bg-slate-50/50">
            <CardContent className="flex flex-col items-center gap-6 py-16 text-center">
              <div className="rounded-2xl bg-gradient-to-br from-slate-100 to-slate-200 p-6">
                <FolderOpen className="h-16 w-16 text-slate-400" />
              </div>
              <div className="max-w-md">
                <h3 className="text-xl font-semibold text-slate-900 mb-2">No Test Uploads Yet</h3>
                <p className="text-slate-600 leading-relaxed">
                  Enable test mode in settings and send lien emails to see them appear here.
                  All uploads will be saved locally for review.
                </p>
              </div>
              <Link href="/">
                <Button variant="primary" className="mt-2">
                  <Home className="h-4 w-4 mr-2" />
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
                    <div className="p-5 space-y-2">
                      {fileError && <ErrorBanner message={fileError} />}
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
                          <Button
                            variant="ghost"
                            onClick={() => handleDownload(conversation.conversation_id, file.filename)}
                            className="shrink-0 h-9 w-9 p-0 hover:bg-blue-50 hover:text-blue-600"
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        </motion.div>
                      ))}
                    </div>
                  </motion.div>
                )}
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
