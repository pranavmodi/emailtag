"use client";

import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  Loader2,
  Paperclip,
  RefreshCcw,
  Search,
  Send,
} from "lucide-react";

import { ApiError, ConversationReplayApi, SettingsApi } from "@/lib/api";
import type {
  ConversationReplayMessage,
  ConversationReplayResponse,
  ConversationReplaySendResponse,
} from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

type MessageReplayStatus = "pending" | "sending" | "sent" | "error";

type MessageReplayState = {
  status: MessageReplayStatus;
  error?: string | null;
  result?: ConversationReplaySendResponse;
};

const STATUS_BADGES: Record<MessageReplayStatus, string> = {
  pending: "bg-slate-100 text-slate-600 border-slate-200",
  sending: "bg-indigo-100 text-indigo-700 border-indigo-200",
  sent: "bg-emerald-100 text-emerald-700 border-emerald-200",
  error: "bg-rose-100 text-rose-700 border-rose-200",
};

export default function ConversationReplayPage() {
  const [user, setUser] = useState("Admin");
  const [authLoading, setAuthLoading] = useState(true);
  const [conversationId, setConversationId] = useState("");
  const [conversation, setConversation] = useState<ConversationReplayResponse | null>(null);
  const [messageStates, setMessageStates] = useState<Record<string, MessageReplayState>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loadingConversation, setLoadingConversation] = useState(false);

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
        setLoadError(
          error instanceof Error ? error.message : "Unable to verify authentication"
        );
      } finally {
        if (mounted) setAuthLoading(false);
      }
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  const nextPendingId = useMemo(() => {
    if (!conversation) return null;
    const pending = conversation.messages.find(
      (msg) => (messageStates[msg.id]?.status ?? "pending") !== "sent"
    );
    return pending?.id ?? null;
  }, [conversation, messageStates]);

  const initializeMessageStates = (payload: ConversationReplayResponse) => {
    const initial: Record<string, MessageReplayState> = {};
    payload.messages.forEach((message) => {
      initial[message.id] = { status: "pending" };
    });
    setMessageStates(initial);
  };

  const handleConversationFetch = async (event?: React.FormEvent<HTMLFormElement>) => {
    event?.preventDefault();
    if (!conversationId.trim()) {
      setLoadError("Enter a Front conversation ID to begin.");
      return;
    }
    setLoadingConversation(true);
    try {
      const payload = await ConversationReplayApi.getConversation(conversationId.trim());
      setConversation(payload);
      initializeMessageStates(payload);
      setLoadError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof ApiError
          ? error.message
          : error instanceof Error
          ? error.message
          : "Failed to load conversation";
      setLoadError(message);
      setConversation(null);
      setMessageStates({});
    } finally {
      setLoadingConversation(false);
    }
  };

  const handleSendMessage = async (message: ConversationReplayMessage) => {
    if (!conversation) return;
    setMessageStates((prev) => ({
      ...prev,
      [message.id]: { status: "sending", error: null, result: prev[message.id]?.result },
    }));

    try {
      const response = await ConversationReplayApi.sendMessage({
        conversation_id: conversation.conversation_id,
        message_id: message.id,
      });
      setMessageStates((prev) => ({
        ...prev,
        [message.id]: { status: "sent", result: response },
      }));
    } catch (error) {
      const messageText =
        error instanceof ApiError
          ? error.message
          : error instanceof Error
          ? error.message
          : "Failed to send message";
      setMessageStates((prev) => ({
        ...prev,
        [message.id]: { status: "error", error: messageText },
      }));
    }
  };

  const resetConversation = () => {
    setConversation(null);
    setMessageStates({});
    setLoadError(null);
    setConversationId("");
  };

  if (authLoading) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="rounded-3xl border border-slate-200/80 bg-white/80 px-10 py-12 text-center shadow-2xl"
        >
          <p className="text-base font-medium text-slate-500">Verifying access…</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-4xl flex-col gap-8 px-6 py-10">

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={easing}
        className="flex flex-col gap-4 rounded-3xl border border-white/40 bg-gradient-to-br from-indigo-500 via-purple-500 to-sky-500 p-8 text-white shadow-2xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-white/70">Replay Laboratory</p>
            <h1 className="text-3xl font-semibold">Conversation Replayer</h1>
            <p className="text-white/80">
              Stream the original Front conversation, sending each message (and its attachments)
              to the configured DEFAULT_RECIPIENT_EMAIL.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl bg-white/15 px-4 py-2 text-sm backdrop-blur">
            <BadgeCheck className="h-4 w-4 text-emerald-200" />
            <span>{user}</span>
            <span className="text-white/60">•</span>
            <Button
              onClick={resetConversation}
              variant="ghost"
              className="border-white/30 text-white/90 hover:bg-white/10 hover:text-white"
            >
              <RefreshCcw className="mr-2 h-4 w-4" />
              Reset
            </Button>
          </div>
        </div>
        <div className="grid gap-3 text-sm text-white/80 sm:grid-cols-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Conversation Loaded</p>
            <p className="text-lg font-semibold">
              {conversation ? `${conversation.message_count} messages` : "No conversation"}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Next in Queue</p>
            <p className="text-lg font-semibold">
              {conversation && nextPendingId
                ? `Message #${
                    conversation.messages.findIndex((msg) => msg.id === nextPendingId) + 1
                  }`
                : "All caught up"}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Destination</p>
            <p className="text-lg font-semibold">DEFAULT_RECIPIENT_EMAIL</p>
          </div>
        </div>
      </motion.div>

      <Card>
        <CardHeader>
          <CardTitle className="text-2xl">Load a conversation</CardTitle>
          <CardDescription>
            Paste a Front conversation ID to fetch every message and attachment. Messages must be
            sent sequentially.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-4" onSubmit={handleConversationFetch}>
            <label className="text-sm font-medium text-slate-700" htmlFor="conversationId">
              Front Conversation ID
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                id="conversationId"
                type="text"
                placeholder="cnv_123abc"
                value={conversationId}
                onChange={(event) => setConversationId(event.target.value)}
                className="flex-1 rounded-2xl border border-slate-200 px-4 py-3 text-base focus:border-slate-900 focus:outline-none focus:ring-2 focus:ring-slate-900/20"
              />
              <Button
                type="submit"
                className="inline-flex items-center justify-center gap-2"
                disabled={loadingConversation}
              >
                {loadingConversation ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
                {loadingConversation ? "Loading…" : "Fetch"}
              </Button>
            </div>
            {loadError && (
              <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                {loadError}
              </div>
            )}
          </form>
        </CardContent>
      </Card>

      {conversation && (
        <div className="space-y-6">
          <Card className="border-slate-200/80">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                Thread Summary
                <Badge className="bg-slate-100 text-slate-700">
                  {conversation.subject || "Untitled"}
                </Badge>
              </CardTitle>
              <CardDescription>
                {conversation.message_count} messages fetched. Only the next pending message can be
                sent at a time to preserve the original order.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-3 text-sm text-slate-600">
              <span>
                <strong>Conversation:</strong> {conversation.conversation_id}
              </span>
              <span>
                <strong>Pending:</strong>{" "}
                {nextPendingId
                  ? `Message #${
                      conversation.messages.findIndex((msg) => msg.id === nextPendingId) + 1
                    }`
                  : "None"}
              </span>
            </CardContent>
          </Card>

          <div className="space-y-4">
            {conversation.messages.map((message, index) => {
              const state = messageStates[message.id] ?? { status: "pending" };
              const isNext = nextPendingId === message.id;

              return (
                <Card key={message.id} className="border border-slate-200/80 shadow-sm">
                  <CardHeader className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <CardTitle className="text-lg">
                        Message {index + 1} · {message.direction?.toUpperCase() || "UNKNOWN"}
                      </CardTitle>
                      <CardDescription className="space-x-2">
                        <span>{message.author_name || message.author_email || "Unknown author"}</span>
                        {message.created_at && <span>· {new Date(message.created_at).toLocaleString()}</span>}
                      </CardDescription>
                    </div>
                    <Badge className={STATUS_BADGES[state.status]}>
                      {state.status === "pending" && "Pending"}
                      {state.status === "sending" && "Sending…"}
                      {state.status === "sent" && "Sent"}
                      {state.status === "error" && "Error"}
                    </Badge>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {message.attachments.length > 0 && (
                      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
                        <div className="flex items-center gap-2 font-medium text-slate-700">
                          <Paperclip className="h-4 w-4" />
                          {message.attachments.length} attachment
                          {message.attachments.length > 1 ? "s" : ""}
                        </div>
                        <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-600">
                          {message.attachments.map((attachment) => (
                            <li key={attachment.id || attachment.filename}>
                              {attachment.filename || attachment.id || "attachment"}
                              {attachment.content_type && (
                                <span className="text-slate-400"> · {attachment.content_type}</span>
                              )}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {message.body ? (
                      <div
                        className="prose max-w-none rounded-2xl border border-slate-100 bg-white/60 p-4 text-sm text-slate-700"
                        dangerouslySetInnerHTML={{ __html: message.body }}
                      />
                    ) : (
                      <pre className="rounded-2xl border border-slate-100 bg-white/60 p-4 text-sm text-slate-700">
                        {message.text_body || "(No content available)"}
                      </pre>
                    )}

                    <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="text-sm text-slate-500">
                        {state.status === "sent" && state.result ? (
                          <span>
                            Sent to <strong>{state.result.sent_to}</strong> as{" "}
                            <strong>{state.result.sender}</strong>
                          </span>
                        ) : (
                          <span>
                            {isNext
                              ? "Ready to send this message."
                              : "Awaiting previous messages."}
                          </span>
                        )}
                        {state.status === "error" && state.error && (
                          <span className="text-rose-500"> · {state.error}</span>
                        )}
                      </div>
                      <Button
                        onClick={() => handleSendMessage(message)}
                        disabled={
                          !isNext ||
                          state.status === "sent" ||
                          state.status === "sending" ||
                          loadingConversation
                        }
                        className="inline-flex items-center gap-2"
                        variant={state.status === "sent" ? "ghost" : "primary"}
                      >
                        {state.status === "sending" ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Send className="h-4 w-4" />
                        )}
                        {state.status === "sent"
                          ? "Sent"
                          : isNext
                          ? "Send message"
                          : "Locked"}
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
