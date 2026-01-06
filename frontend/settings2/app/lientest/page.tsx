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
  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
    {message}
  </div>
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
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="rounded-3xl border border-slate-200/80 bg-white/80 px-10 py-12 text-center shadow-2xl"
        >
          <p className="text-base font-medium text-slate-500">Loading test uploads…</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-8 px-6 py-10">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={easing}
        className="flex flex-col gap-4 rounded-3xl border border-white/40 bg-gradient-to-br from-blue-500 via-indigo-500 to-purple-500 p-8 text-white shadow-2xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-white/70">Lien Testing</p>
            <h1 className="text-3xl font-semibold">Test Upload Sandbox</h1>
            <p className="text-white/80">
              Review lien documents uploaded in test mode, organized by conversation ID.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link href="/">
              <Button
                variant="ghost"
                className="border-white/30 text-white/90 hover:bg-white/10 hover:text-white"
              >
                <Home className="h-4 w-4" />
                Back to Settings
              </Button>
            </Link>
            <Button
              onClick={loadConversations}
              variant="ghost"
              className="border-white/30 text-white/90 hover:bg-white/10 hover:text-white"
            >
              <RefreshCw className="h-4 w-4" />
              Refresh
            </Button>
          </div>
        </div>
        <div className="grid gap-3 text-sm text-white/80 sm:grid-cols-2">
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Conversations</p>
            <p className="text-lg font-semibold">{conversations.length}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Total Files</p>
            <p className="text-lg font-semibold">
              {conversations.reduce((sum, conv) => sum + conv.file_count, 0)}
            </p>
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
          <Card>
            <CardContent className="flex flex-col items-center gap-4 py-12 text-center">
              <FolderOpen className="h-16 w-16 text-slate-300" />
              <div>
                <h3 className="text-lg font-semibold text-slate-900">No Test Uploads Yet</h3>
                <p className="text-sm text-slate-500">
                  Enable test mode in settings and send lien emails to see them here.
                </p>
              </div>
              <Link href="/">
                <Button variant="outline">Go to Settings</Button>
              </Link>
            </CardContent>
          </Card>
        </motion.div>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {conversations.map((conversation) => (
          <motion.div
            key={conversation.conversation_id}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={easing}
          >
            <Card className="h-full hover:shadow-lg transition-shadow">
              <CardHeader>
                <CardTitle className="flex items-center gap-3 text-lg">
                  <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg">
                    <FileText className="h-5 w-5" />
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="truncate">{conversation.conversation_id}</p>
                    <Badge className="mt-1 bg-slate-100 text-slate-600 border-slate-200">
                      {conversation.file_count} {conversation.file_count === 1 ? "file" : "files"}
                    </Badge>
                  </div>
                </CardTitle>
                <CardDescription>
                  Front conversation with {conversation.file_count} uploaded lien{" "}
                  {conversation.file_count === 1 ? "document" : "documents"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Button
                  onClick={() => loadFileDetails(conversation.conversation_id)}
                  disabled={isLoadingFiles && selectedConversation === conversation.conversation_id}
                  className="w-full"
                  variant={
                    selectedConversation === conversation.conversation_id ? "default" : "outline"
                  }
                >
                  {isLoadingFiles && selectedConversation === conversation.conversation_id ? (
                    <>
                      <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                      Loading...
                    </>
                  ) : (
                    <>
                      <FolderOpen className="mr-2 h-4 w-4" />
                      {selectedConversation === conversation.conversation_id
                        ? "Refresh Files"
                        : "View Files"}
                    </>
                  )}
                </Button>
                {selectedConversation === conversation.conversation_id && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    transition={easing}
                    className="space-y-2 pt-2"
                  >
                    {fileError && <ErrorBanner message={fileError} />}
                    {fileDetails.map((file) => (
                      <div
                        key={file.filename}
                        className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 p-3 text-sm"
                      >
                        <div className="flex-1 min-w-0 mr-3">
                          <p className="font-medium text-slate-900 truncate">{file.filename}</p>
                          <p className="text-xs text-slate-500">
                            {formatFileSize(file.size)} • {formatDate(file.created)}
                          </p>
                        </div>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => handleDownload(conversation.conversation_id, file.filename)}
                          className="shrink-0"
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
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
