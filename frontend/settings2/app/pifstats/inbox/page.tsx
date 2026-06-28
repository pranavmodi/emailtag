"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowLeft,
  CalendarDays,
  ChevronRight,
  Download,
  ExternalLink,
  Inbox,
  Loader2,
  LogOut,
  Mail,
  Paperclip,
  RefreshCw,
  Search,
  User,
} from "lucide-react";

import { ApiError, PifInboxApi, PifStatsAuthApi } from "@/lib/api";
import type {
  FrontConversationDetailResponse,
  FrontConversationMessage,
  FrontConversationSummary,
  FrontInbox,
  FrontInboxExportStatus,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const CONVERSATION_LIMIT = 15;

const isoDate = (date: Date) => date.toISOString().slice(0, 10);

const formatDate = (value: string | null | undefined) => {
  if (!value) return "";
  return new Date(value).toLocaleString();
};

const messageText = (message: FrontConversationMessage) => {
  const value = message.text || message.blurb || message.body || "";
  return stripHtml(value) || "(No message text)";
};

const stripHtml = (value: string) =>
  value
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/\s+/g, " ")
    .trim();

export default function PifStatsInboxPage() {
  const [inboxes, setInboxes] = useState<FrontInbox[]>([]);
  const [selectedInboxId, setSelectedInboxId] = useState<string | null>(null);
  const [inboxSearch, setInboxSearch] = useState("");
  const [conversationSearch, setConversationSearch] = useState("");
  const [conversations, setConversations] = useState<FrontConversationSummary[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [conversationDetail, setConversationDetail] = useState<FrontConversationDetailResponse | null>(null);
  const [isLoadingInboxes, setIsLoadingInboxes] = useState(true);
  const [isLoadingConversations, setIsLoadingConversations] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [exportDateFrom, setExportDateFrom] = useState(() => isoDate(new Date()));
  const [exportDateTo, setExportDateTo] = useState(() => isoDate(new Date()));
  const [isStartingExport, setIsStartingExport] = useState(false);
  const [exportStatus, setExportStatus] = useState<FrontInboxExportStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadInboxes = useCallback(async () => {
    setIsLoadingInboxes(true);
    try {
      const payload = await PifInboxApi.listInboxes();
      setInboxes(payload.items);
      setSelectedInboxId((current) => current ?? payload.items[0]?.id ?? null);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load Front inboxes");
    } finally {
      setIsLoadingInboxes(false);
    }
  }, []);

  useEffect(() => {
    loadInboxes();
  }, [loadInboxes]);

  const loadConversations = useCallback(
    async (inboxId: string, options?: { append?: boolean; cursor?: string | null }) => {
      const append = Boolean(options?.append);
      append ? setIsLoadingMore(true) : setIsLoadingConversations(true);
      try {
        const payload = await PifInboxApi.listConversations(inboxId, {
          limit: CONVERSATION_LIMIT,
          cursor: options?.cursor,
        });
        setConversations((current) => (append ? [...current, ...payload.items] : payload.items));
        setNextCursor(payload.next_cursor);
        if (!append) {
          setSelectedConversationId(payload.items[0]?.id ?? null);
          setConversationDetail(null);
        }
        setError(null);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Unable to load conversations");
      } finally {
        append ? setIsLoadingMore(false) : setIsLoadingConversations(false);
      }
    },
    []
  );

  useEffect(() => {
    if (!selectedInboxId) return;
    setConversations([]);
    setNextCursor(null);
    setSelectedConversationId(null);
    setConversationDetail(null);
    loadConversations(selectedInboxId);
  }, [loadConversations, selectedInboxId]);

  const loadConversationDetail = useCallback(async (conversationId: string) => {
    setIsLoadingDetail(true);
    try {
      const payload = await PifInboxApi.getConversation(conversationId);
      setConversationDetail(payload);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load conversation");
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  useEffect(() => {
    if (!selectedConversationId) return;
    loadConversationDetail(selectedConversationId);
  }, [loadConversationDetail, selectedConversationId]);

  const selectedInbox = useMemo(
    () => inboxes.find((inbox) => inbox.id === selectedInboxId) ?? null,
    [inboxes, selectedInboxId]
  );

  const filteredInboxes = useMemo(() => {
    const query = inboxSearch.trim().toLowerCase();
    if (!query) return inboxes;
    return inboxes.filter((inbox) =>
      `${inbox.name} ${inbox.address} ${inbox.id}`.toLowerCase().includes(query)
    );
  }, [inboxSearch, inboxes]);

  const filteredConversations = useMemo(() => {
    const query = conversationSearch.trim().toLowerCase();
    if (!query) return conversations;
    return conversations.filter((conversation) =>
      `${conversation.subject} ${conversation.recipient_name} ${conversation.recipient_handle} ${conversation.id}`
        .toLowerCase()
        .includes(query)
    );
  }, [conversationSearch, conversations]);

  const refreshCurrentInbox = () => {
    if (selectedInboxId) loadConversations(selectedInboxId);
  };

  const handleLogout = async () => {
    try {
      await PifStatsAuthApi.logout();
    } finally {
      window.location.href = "/pifstats/login";
    }
  };

  const exportRunning = exportStatus
    ? exportStatus.status === "queued" || exportStatus.status === "running"
    : false;

  const startExport = async () => {
    if (!selectedInboxId) return;
    setIsStartingExport(true);
    try {
      const response = await PifInboxApi.startExport({
        inboxId: selectedInboxId,
        inboxName: selectedInbox?.name,
        dateFrom: exportDateFrom,
        dateTo: exportDateTo,
      });
      setExportStatus({
        status: response.status,
        message: response.message,
        inbox_id: selectedInboxId,
        inbox_name: selectedInbox?.name,
        date_from: exportDateFrom,
        date_to: exportDateTo,
        total_conversations: 0,
        processed_conversations: 0,
        download_url: null,
        file_size: null,
        created_at: new Date().toISOString(),
      });
      setError(null);
      window.setTimeout(async () => {
        const status = await PifInboxApi.getExportStatus(response.export_id);
        setExportStatus({ ...status, export_id: response.export_id } as FrontInboxExportStatus);
      }, 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to start export");
    } finally {
      setIsStartingExport(false);
    }
  };

  useEffect(() => {
    const exportId = (exportStatus as FrontInboxExportStatus & { export_id?: string } | null)?.export_id;
    if (!exportId || !exportRunning) return;

    const interval = window.setInterval(async () => {
      try {
        const status = await PifInboxApi.getExportStatus(exportId);
        setExportStatus({ ...status, export_id: exportId } as FrontInboxExportStatus);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Unable to poll export status");
      }
    }, 5000);

    return () => window.clearInterval(interval);
  }, [exportRunning, exportStatus]);

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-6 py-5">
          <div>
            <Link
              href="/pifstats"
              className="mb-2 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
            >
              <ArrowLeft className="h-4 w-4" />
              PIFStats
            </Link>
            <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
            <p className="text-sm text-slate-500">
              {selectedInbox ? `${selectedInbox.name} · ${selectedInbox.address || selectedInbox.id}` : "Front inbox viewer"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={loadInboxes} disabled={isLoadingInboxes} variant="ghost" className="border border-slate-300">
              {isLoadingInboxes ? <Loader2 className="h-4 w-4 animate-spin" /> : <Inbox className="h-4 w-4" />}
              Inboxes
            </Button>
            <Button onClick={refreshCurrentInbox} disabled={!selectedInboxId || isLoadingConversations} className="gap-2">
              {isLoadingConversations ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh
            </Button>
            <Button type="button" variant="ghost" onClick={handleLogout} className="gap-2 border border-slate-300">
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-[1600px] px-6 py-5">
        {error && (
          <div className="mb-4 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <section className="mb-4 rounded-lg border border-slate-200 bg-white p-4">
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <Download className="h-4 w-4" />
                Bulk export
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Exports full conversations and attachments for the selected inbox. Range is capped at 7 days and runs slowly to protect Front API limits.
              </p>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <label className="block">
                <span className="mb-1 flex items-center gap-1 text-xs font-medium text-slate-500">
                  <CalendarDays className="h-3.5 w-3.5" />
                  From
                </span>
                <input
                  type="date"
                  value={exportDateFrom}
                  onChange={(event) => setExportDateFrom(event.target.value)}
                  className="h-9 rounded-md border border-slate-300 px-3 text-sm"
                />
              </label>
              <label className="block">
                <span className="mb-1 flex items-center gap-1 text-xs font-medium text-slate-500">
                  <CalendarDays className="h-3.5 w-3.5" />
                  To
                </span>
                <input
                  type="date"
                  value={exportDateTo}
                  onChange={(event) => setExportDateTo(event.target.value)}
                  className="h-9 rounded-md border border-slate-300 px-3 text-sm"
                />
              </label>
              <Button
                type="button"
                onClick={startExport}
                disabled={!selectedInboxId || isStartingExport || exportRunning}
                className="h-9 gap-2"
              >
                {isStartingExport || exportRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
                {exportRunning ? "Exporting..." : "Export ZIP"}
              </Button>
            </div>
          </div>
          {exportStatus && (
            <div className="mt-3 flex flex-wrap items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
              <Badge className={exportStatus.status === "completed" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : exportStatus.status === "failed" ? "border-rose-200 bg-rose-50 text-rose-700" : "border-amber-200 bg-amber-50 text-amber-700"}>
                {exportStatus.status}
              </Badge>
              <span className="text-slate-600">
                {exportStatus.message}
                {exportStatus.total_conversations > 0 &&
                  ` (${exportStatus.processed_conversations}/${exportStatus.total_conversations})`}
              </span>
              {exportStatus.status === "completed" && (exportStatus as FrontInboxExportStatus & { export_id?: string }).export_id && (
                <a
                  href={PifInboxApi.getExportDownloadUrl((exportStatus as FrontInboxExportStatus & { export_id: string }).export_id)}
                  className="ml-auto inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-slate-900 hover:text-slate-950"
                >
                  Download ZIP
                  <Download className="h-3.5 w-3.5" />
                </a>
              )}
            </div>
          )}
        </section>

        <div className="grid min-h-[calc(100vh-150px)] overflow-hidden rounded-lg border border-slate-200 bg-white lg:grid-cols-[280px_390px_minmax(0,1fr)]">
          <aside className="border-b border-slate-200 lg:border-b-0 lg:border-r">
            <PaneHeader icon={<Inbox className="h-4 w-4" />} title="Inboxes" count={filteredInboxes.length} />
            <SearchBox value={inboxSearch} onChange={setInboxSearch} placeholder="Search inboxes" />
            <div className="max-h-[72vh] overflow-auto p-2">
              {isLoadingInboxes ? (
                <LoadingBlock label="Loading inboxes" />
              ) : (
                filteredInboxes.map((inbox) => (
                  <button
                    key={inbox.id}
                    type="button"
                    disabled={isLoadingConversations}
                    onClick={() => setSelectedInboxId(inbox.id)}
                    className={`mb-1 flex w-full items-center gap-3 rounded-md px-3 py-2 text-left text-sm ${
                      inbox.id === selectedInboxId
                        ? "bg-slate-900 text-white"
                        : "text-slate-700 hover:bg-slate-100"
                    } disabled:cursor-wait disabled:opacity-70`}
                  >
                    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${
                      inbox.id === selectedInboxId ? "bg-white/15" : "bg-slate-100"
                    }`}>
                      <Mail className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-medium">{inbox.name}</span>
                      <span className={`block truncate text-xs ${
                        inbox.id === selectedInboxId ? "text-slate-300" : "text-slate-400"
                      }`}>
                        {inbox.address || inbox.type || inbox.id}
                      </span>
                    </span>
                  </button>
                ))
              )}
            </div>
          </aside>

          <section className="border-b border-slate-200 lg:border-b-0 lg:border-r">
            <PaneHeader
              icon={<Mail className="h-4 w-4" />}
              title="Conversations"
              count={filteredConversations.length}
            />
            <SearchBox value={conversationSearch} onChange={setConversationSearch} placeholder="Search conversations" />
            <div className="max-h-[72vh] overflow-auto p-2">
              {isLoadingConversations ? (
                <LoadingBlock label="Loading conversations" />
              ) : filteredConversations.length ? (
                filteredConversations.map((conversation) => (
                  <ConversationButton
                    key={conversation.id}
                    conversation={conversation}
                    selected={conversation.id === selectedConversationId}
                    disabled={isLoadingDetail}
                    onClick={() => setSelectedConversationId(conversation.id)}
                  />
                ))
              ) : (
                <EmptyState label="No conversations found." />
              )}
              {nextCursor && !conversationSearch && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={isLoadingMore || !selectedInboxId}
                  onClick={() => selectedInboxId && loadConversations(selectedInboxId, { append: true, cursor: nextCursor })}
                  className="mt-2 w-full border border-slate-300"
                >
                  {isLoadingMore ? <Loader2 className="h-4 w-4 animate-spin" /> : <ChevronRight className="h-4 w-4" />}
                  Load more
                </Button>
              )}
            </div>
          </section>

          <section className="min-w-0 bg-slate-50">
            {isLoadingDetail ? (
              <LoadingBlock label="Loading conversation" />
            ) : conversationDetail ? (
              <ConversationDetail detail={conversationDetail} />
            ) : (
              <EmptyState label="Select a conversation." />
            )}
          </section>
        </div>
      </section>
    </main>
  );
}

function PaneHeader({ icon, title, count }: { icon: React.ReactNode; title: string; count: number }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
        {icon}
        {title}
      </h2>
      <Badge className="border-slate-200 bg-slate-50 text-slate-600">{count}</Badge>
    </div>
  );
}

function SearchBox({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}) {
  return (
    <label className="relative block border-b border-slate-200 p-3">
      <span className="sr-only">{placeholder}</span>
      <Search className="pointer-events-none absolute left-6 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        className="h-9 w-full rounded-md border border-slate-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-slate-900"
      />
    </label>
  );
}

function ConversationButton({
  conversation,
  selected,
  disabled,
  onClick,
}: {
  conversation: FrontConversationSummary;
  selected: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`mb-1 w-full rounded-md px-3 py-3 text-left text-sm ${
        selected ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"
      } disabled:cursor-wait disabled:opacity-70`}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="line-clamp-2 font-medium">{conversation.subject}</span>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] ${
          selected ? "bg-white/15 text-slate-100" : "bg-slate-100 text-slate-500"
        }`}>
          {conversation.status || "open"}
        </span>
      </div>
      <div className={`mt-1 truncate text-xs ${selected ? "text-slate-300" : "text-slate-500"}`}>
        {conversation.recipient_name || conversation.recipient_handle || conversation.id}
      </div>
      <div className={`mt-2 flex flex-wrap items-center gap-1 text-xs ${selected ? "text-slate-300" : "text-slate-400"}`}>
        {conversation.updated_at && <span>{formatDate(conversation.updated_at)}</span>}
        {conversation.tags.slice(0, 2).map((tag) => (
          <span
            key={tag.id || tag.name}
            className={`rounded px-1.5 py-0.5 ${selected ? "bg-white/10" : "bg-slate-100 text-slate-500"}`}
          >
            {tag.name}
          </span>
        ))}
      </div>
    </button>
  );
}

function ConversationDetail({ detail }: { detail: FrontConversationDetailResponse }) {
  const { conversation } = detail;
  return (
    <div className="flex h-full min-h-[72vh] flex-col">
      <div className="border-b border-slate-200 bg-white px-5 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="line-clamp-2 text-lg font-semibold text-slate-950">{conversation.subject}</h2>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span>{conversation.id}</span>
              {conversation.updated_at && <span>{formatDate(conversation.updated_at)}</span>}
              {conversation.recipient_handle && <span>{conversation.recipient_handle}</span>}
            </div>
          </div>
          <a
            href={conversation.front_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:border-slate-900 hover:text-slate-950"
          >
            Open in Front
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          <Badge className="border-slate-200 bg-slate-50 text-slate-600">{conversation.status || "open"}</Badge>
          <Badge className="border-slate-200 bg-slate-50 text-slate-600">{detail.message_count} messages</Badge>
          {conversation.tags.map((tag) => (
            <Badge key={tag.id || tag.name} className="border-indigo-200 bg-indigo-50 text-indigo-700">
              {tag.name}
            </Badge>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto p-5">
        <div className="mx-auto max-w-4xl space-y-4">
          {detail.messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: FrontConversationMessage }) {
  const toRecipients = message.recipients.filter((recipient) => recipient.role === "to");
  const ccRecipients = message.recipients.filter((recipient) => recipient.role === "cc");
  return (
    <article className={`rounded-lg border p-4 ${
      message.is_inbound ? "border-slate-200 bg-white" : "ml-auto border-indigo-100 bg-indigo-50"
    }`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <User className="h-4 w-4 text-slate-400" />
            <span className="truncate">{message.author_name || message.author_handle || "Unknown sender"}</span>
          </div>
          {message.author_handle && (
            <div className="mt-0.5 truncate text-xs text-slate-500">{message.author_handle}</div>
          )}
        </div>
        <div className="text-xs text-slate-400">{formatDate(message.created_at)}</div>
      </div>

      {(toRecipients.length > 0 || ccRecipients.length > 0) && (
        <div className="mt-3 space-y-1 text-xs text-slate-500">
          {toRecipients.length > 0 && <RecipientLine label="To" recipients={toRecipients} />}
          {ccRecipients.length > 0 && <RecipientLine label="Cc" recipients={ccRecipients} />}
        </div>
      )}

      <pre className="mt-4 whitespace-pre-wrap break-words font-sans text-sm leading-6 text-slate-800">
        {messageText(message)}
      </pre>

      {message.attachments.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.attachments.map((attachment) => (
            <a
              key={attachment.id || attachment.filename}
              href={PifInboxApi.getAttachmentDownloadUrl(message.id, attachment.id)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:border-slate-400 hover:text-slate-950"
            >
              <Paperclip className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{attachment.filename || attachment.content_type || "Attachment"}</span>
            </a>
          ))}
        </div>
      )}
    </article>
  );
}

function RecipientLine({
  label,
  recipients,
}: {
  label: string;
  recipients: Array<{ name: string; handle: string; role: string }>;
}) {
  return (
    <div className="flex gap-2">
      <span className="w-5 shrink-0 font-medium uppercase text-slate-400">{label}</span>
      <span className="min-w-0 break-words">
        {recipients.map((recipient) => recipient.name || recipient.handle).join(", ")}
      </span>
    </div>
  );
}

function LoadingBlock({ label }: { label: string }) {
  return (
    <div className="flex min-h-44 items-center justify-center gap-2 text-sm text-slate-500">
      <Loader2 className="h-4 w-4 animate-spin" />
      {label}
    </div>
  );
}

function EmptyState({ label }: { label: string }) {
  return (
    <div className="flex min-h-44 items-center justify-center text-sm text-slate-500">
      {label}
    </div>
  );
}
