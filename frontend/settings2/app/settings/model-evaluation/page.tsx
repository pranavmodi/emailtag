"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bot,
  CheckCircle2,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquare,
  Paperclip,
  RefreshCw,
  Route,
  Tag,
} from "lucide-react";

import { Header } from "@/components/layout/Header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ApiError, ModelEvaluationApi, SettingsApi } from "@/lib/api";
import type {
  ModelEvaluationConversation,
  ModelEvaluationPilotResponse,
} from "@/lib/types";
import { EvaluationRunner } from "./EvaluationRunner";
import { ClassificationRankingSection } from "./ClassificationRankingSection";
import { ModelControls } from "./ModelControls";
import { VisionEvaluationSection } from "./VisionEvaluationSection";

type DetailView = "thread" | "decisions" | "models" | "ground-truth";

function formatDate(value: string | null | undefined): string {
  if (!value) return "Unknown";
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function plainText(html: string): string {
  return html
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function ConversationListItem({
  conversation,
  active,
  onClick,
}: {
  conversation: ModelEvaluationConversation;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full rounded-xl border p-4 text-left transition ${
        active
          ? "border-indigo-500 bg-indigo-50 shadow-sm"
          : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="line-clamp-2 text-sm font-semibold text-slate-900">
          {conversation.subject || "No subject"}
        </p>
        <Badge className="shrink-0 border-slate-200 bg-slate-100 text-[10px] uppercase text-slate-600">
          {conversation.ground_truth.status.replace("_", " ")}
        </Badge>
      </div>
      <p className="mt-1 text-xs text-slate-500">{conversation.conversation_id}</p>
      <div className="mt-2 flex flex-wrap gap-1">
        {conversation.sample_tags.map((tag) => (
          <span key={tag} className="rounded bg-indigo-50 px-2 py-1 text-[10px] font-medium text-indigo-700">
            Sample: {tag}
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
        <span>{conversation.messages.length} messages</span>
        <span>•</span>
        <span>{conversation.outbound_reply_count} replies</span>
        <span>•</span>
        <span>{conversation.actions.length} actions</span>
      </div>
      <div className="mt-3 flex flex-wrap gap-1">
        {conversation.current_tags.slice(0, 3).map((tag) => (
          <span key={tag} className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-600">
            {tag}
          </span>
        ))}
        {conversation.current_tags.length > 3 && (
          <span className="rounded bg-slate-100 px-2 py-1 text-[10px] text-slate-500">
            +{conversation.current_tags.length - 3}
          </span>
        )}
      </div>
    </button>
  );
}

function ThreadView({ conversation }: { conversation: ModelEvaluationConversation }) {
  if (conversation.load_error) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
        Messages could not be loaded: {conversation.load_error}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {conversation.messages.map((message) => {
        const outbound = message.is_inbound === false;
        const content = message.text_body || plainText(message.body || "") || "No message body";
        return (
          <article
            key={message.id}
            className={`rounded-xl border p-4 ${
              outbound ? "border-indigo-200 bg-indigo-50/70" : "border-slate-200 bg-white"
            }`}
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <div className="flex items-center gap-2">
                  <Badge
                    className={
                      outbound
                        ? "border-indigo-600 bg-indigo-600 text-white"
                        : "border-slate-200 bg-slate-100 text-slate-600"
                    }
                  >
                    {outbound ? "Outbound reply" : "Inbound"}
                  </Badge>
                  <span className="text-sm font-medium text-slate-800">
                    {message.author_name || message.author_email || "Unknown sender"}
                  </span>
                </div>
                {message.author_email && (
                  <p className="mt-1 text-xs text-slate-500">{message.author_email}</p>
                )}
              </div>
              <time className="text-xs text-slate-500">{formatDate(message.created_at)}</time>
            </div>
            <pre className="mt-4 max-h-80 overflow-auto whitespace-pre-wrap break-words font-sans text-sm leading-6 text-slate-700">
              {content}
            </pre>
            {message.attachments.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-2 border-t border-slate-200 pt-3">
                {message.attachments.map((attachment) => (
                  <span
                    key={attachment.id || attachment.filename}
                    className="inline-flex items-center gap-1 rounded-lg bg-white px-2 py-1 text-xs text-slate-600"
                  >
                    <Paperclip className="h-3 w-3" />
                    {attachment.filename || "Attachment"}
                  </span>
                ))}
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}

function DecisionsView({ conversation }: { conversation: ModelEvaluationConversation }) {
  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Bot className="h-4 w-4 text-indigo-600" /> Classification decisions
        </h3>
        {conversation.classifications.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">
            No classification traces were found in EmailTag for this conversation.
          </p>
        ) : (
          <div className="space-y-3">
            {conversation.classifications.map((classification, index) => (
              <div
                key={`${classification.step_name}-${index}`}
                className="rounded-xl border border-slate-200 bg-white p-4"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <Badge className="border-slate-200 bg-slate-100 text-slate-600">
                      {classification.step_name}
                    </Badge>
                    <span className="font-semibold text-slate-900">
                      {classification.chosen_option || "No option recorded"}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {classification.llm_model || "Model unknown"}
                    {classification.total_tokens ? ` · ${classification.total_tokens} tokens` : ""}
                  </span>
                </div>
                {classification.classification_path && (
                  <p className="mt-2 text-xs font-medium text-indigo-700">
                    {classification.classification_path}
                  </p>
                )}
                {classification.classification_reason && (
                  <p className="mt-2 text-sm leading-6 text-slate-600">
                    {classification.classification_reason}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Route className="h-4 w-4 text-indigo-600" /> Action timeline
        </h3>
        {conversation.actions.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 p-4 text-sm text-slate-500">
            No action history was found for this conversation.
          </p>
        ) : (
          <div className="space-y-3">
            {conversation.actions.map((action, index) => (
              <div
                key={`${action.action_type}-${action.timestamp}-${index}`}
                className="flex gap-3 rounded-xl border border-slate-200 bg-white p-4"
              >
                <div className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full bg-indigo-500" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-slate-900">{action.label}</p>
                    <time className="text-xs text-slate-500">{formatDate(action.timestamp)}</time>
                  </div>
                  <p className="mt-1 text-xs uppercase tracking-wide text-slate-500">
                    {action.source.replaceAll("_", " ")}
                  </p>
                  {Object.keys(action.details).length > 0 && (
                    <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                      {JSON.stringify(action.details, null, 2)}
                    </pre>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function GroundTruthView({ conversation }: { conversation: ModelEvaluationConversation }) {
  return (
    <div className="space-y-5">
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5">
        <div className="flex items-center gap-2 font-semibold text-amber-900">
          <CheckCircle2 className="h-5 w-5" /> Ground truth not reviewed
        </div>
        <p className="mt-2 text-sm leading-6 text-amber-800">
          Historical tags, replies, and actions are evidence. A reviewer still needs to confirm the
          correct tags, expected action, and whether the reply was appropriate before this record is
          used to score models.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Source classification tags</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {conversation.current_tags.map((tag) => (
              <Badge key={tag}>{tag}</Badge>
            ))}
            {conversation.current_tags.length === 0 && (
              <span className="text-sm text-slate-500">No tags</span>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Human-reviewed tags</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            <span className="text-sm text-amber-700">Pending human review</span>
          </CardContent>
        </Card>
      </div>

      <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
        Open the linked Front conversation when reviewing to confirm whether its current tags were
        corrected after the original EmailTag classification.
      </p>

      <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600">
        Review editing and approval will be the next milestone after this per-tag dataset is
        inspected and the labeling fields are confirmed.
      </div>
    </div>
  );
}

export default function ModelEvaluationPage() {
  const [user, setUser] = useState("Admin");
  const [pilot, setPilot] = useState<ModelEvaluationPilotResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detailView, setDetailView] = useState<DetailView>("thread");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadPilot = useCallback(async (forceRefresh: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const response = await ModelEvaluationApi.getPilot(5, true, forceRefresh);
      setPilot(response);
      setSelectedId((current) =>
        current && response.conversations.some((item) => item.conversation_id === current)
          ? current
          : response.conversations[0]?.conversation_id || null
      );
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        window.location.href = "/login";
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load the pilot dataset");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const bootstrap = async () => {
      try {
        const auth = await SettingsApi.getAuthStatus();
        if (!auth.authenticated) {
          window.location.href = "/login";
          return;
        }
        if (!active) return;
        setUser(auth.username || "Admin");
        await loadPilot(false);
      } catch (err) {
        if (!active) return;
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to initialize the page");
        setLoading(false);
      }
    };
    bootstrap();
    return () => {
      active = false;
    };
  }, [loadPilot]);

  const selected = useMemo(
    () => pilot?.conversations.find((item) => item.conversation_id === selectedId) || null,
    [pilot, selectedId]
  );
  const shortlistedConversationIds = useMemo(
    () => pilot?.conversations.map((conversation) => conversation.conversation_id) || [],
    [pilot]
  );

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header
        user={user}
        currentPage={{ label: "Model Evaluation", icon: "⚖️" }}
        extraAction={
          <Button onClick={() => loadPilot(true)} disabled={loading} variant="ghost" className="gap-2">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Reload pilot
          </Button>
        }
      />

      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900">Model Evaluation Pilot</h1>
            <p className="mt-2 max-w-3xl text-slate-600">
              Up to five recently classified, single-message emails for every output tag in
              EMAIL_CATEGORIES. AI:Training failure cases are excluded from this primary dataset.
              Evaluations are manually triggered and isolated from production processing.
            </p>
          </div>
          {pilot && (
            <div className="text-right text-xs text-slate-500">
              <p>Source: recent EmailTag classifications</p>
              <p>Single inbound message · scanned {pilot.candidates_scanned} candidates</p>
              <p>Generated {formatDate(pilot.generated_at)}</p>
            </div>
          )}
        </div>

        {error && (
          <div className="mb-6 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        <ModelControls />

        {loading && !pilot ? (
          <div className="flex min-h-80 items-center justify-center rounded-2xl border border-slate-200 bg-white">
            <div className="text-center text-slate-500">
              <Loader2 className="mx-auto mb-3 h-7 w-7 animate-spin" />
              Building per-tag coverage from Front and EmailTag…
            </div>
          </div>
        ) : pilot ? (
          <>
            <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: "Unique conversations", value: pilot.conversation_count, icon: MessageSquare },
                {
                  label: "Configured tags",
                  value: pilot.configured_tag_count,
                  icon: Tag,
                },
                {
                  label: "Examples found",
                  value: pilot.tag_coverage.reduce((sum, item) => sum + item.found, 0),
                  icon: CheckCircle2,
                },
                {
                  label: "Examples missing",
                  value: pilot.tag_coverage.reduce((sum, item) => sum + item.missing, 0),
                  icon: FileText,
                },
              ].map(({ label, value, icon: Icon }) => (
                <Card key={label}>
                  <CardContent className="flex items-center gap-4 p-5">
                    <div className="rounded-xl bg-indigo-50 p-3 text-indigo-600">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div>
                      <p className="text-2xl font-bold text-slate-900">{value}</p>
                      <p className="text-xs text-slate-500">{label}</p>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <details className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <summary className="cursor-pointer text-sm font-semibold text-slate-900">
                Tag coverage: {pilot.tag_coverage.filter((item) => item.missing === 0).length} of {pilot.configured_tag_count} tags complete
              </summary>
              <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {pilot.tag_coverage.map((item) => (
                  <div
                    key={item.tag_name}
                    className={`flex items-center justify-between rounded-lg border px-3 py-2 text-sm ${
                      item.missing === 0
                        ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                        : "border-amber-200 bg-amber-50 text-amber-800"
                    }`}
                  >
                    <span className="truncate font-medium">{item.tag_name}</span>
                    <span className="ml-3 shrink-0">{item.found}/{item.requested}</span>
                  </div>
                ))}
              </div>
            </details>

            <ClassificationRankingSection
              conversationIds={shortlistedConversationIds}
            />

            <div className="grid gap-6 lg:grid-cols-[340px_minmax(0,1fr)]">
              <aside className="space-y-3 lg:max-h-[calc(100vh-260px)] lg:overflow-auto lg:pr-1">
                {pilot.conversations.map((conversation) => (
                  <ConversationListItem
                    key={conversation.conversation_id}
                    conversation={conversation}
                    active={conversation.conversation_id === selectedId}
                    onClick={() => {
                      setSelectedId(conversation.conversation_id);
                      setDetailView("thread");
                    }}
                  />
                ))}
              </aside>

              {selected ? (
                <section className="min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm">
                  <div className="border-b border-slate-200 p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <h2 className="text-xl font-bold text-slate-900">
                          {selected.subject || "No subject"}
                        </h2>
                        <p className="mt-1 text-xs text-slate-500">
                          {selected.conversation_id} · {formatDate(selected.created_at)}
                          {selected.assignee ? ` · Assigned to ${selected.assignee}` : ""}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Link
                          href={`/settings/model-evaluation/case?${new URLSearchParams({ case_type: "classification", case_id: selected.conversation_id, conversation_id: selected.conversation_id, front_url: selected.front_url }).toString()}`}
                          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm font-medium text-white hover:bg-indigo-700"
                        >
                          Model drill-down <ExternalLink className="h-4 w-4" />
                        </Link>
                        <a
                          href={selected.front_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                        >
                          Open in Front <ExternalLink className="h-4 w-4" />
                        </a>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2">
                      {selected.current_tags.map((tag) => (
                        <Badge key={tag} className="gap-1 border-slate-200 bg-slate-100 text-slate-600">
                          <Tag className="h-3 w-3" /> {tag}
                        </Badge>
                      ))}
                      <Badge className="border-slate-300 bg-white text-slate-600">
                        EmailTag: {selected.status || "unknown"}
                      </Badge>
                      {selected.sample_tags.map((tag) => (
                        <Badge key={tag} className="border-indigo-200 bg-indigo-50 text-indigo-700">
                          Sample: {tag}
                        </Badge>
                      ))}
                      <Badge className="border-slate-300 bg-white text-slate-600">
                        OCR results: {selected.ocr_result_count}
                      </Badge>
                    </div>

                    <div className="mt-5 flex flex-wrap gap-2">
                      {(
                        [
                          ["thread", "Thread & replies"],
                          ["decisions", "Decisions & actions"],
                          ["models", "Run models"],
                          ["ground-truth", "Ground truth"],
                        ] as [DetailView, string][]
                      ).map(([value, label]) => (
                        <button
                          key={value}
                          type="button"
                          onClick={() => setDetailView(value)}
                          className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                            detailView === value
                              ? "bg-slate-900 text-white"
                              : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="p-5">
                    {detailView === "thread" && <ThreadView conversation={selected} />}
                    {detailView === "decisions" && <DecisionsView conversation={selected} />}
                    {detailView === "models" && (
                      <EvaluationRunner
                        caseType="classification"
                        caseId={selected.conversation_id}
                        target={{ conversation_id: selected.conversation_id }}
                      />
                    )}
                    {detailView === "ground-truth" && <GroundTruthView conversation={selected} />}
                  </div>
                </section>
              ) : (
                <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-10 text-center text-slate-500">
                  Select a conversation to inspect it.
                </div>
              )}
            </div>
          </>
        ) : null}

        <VisionEvaluationSection />
      </main>
    </div>
  );
}
