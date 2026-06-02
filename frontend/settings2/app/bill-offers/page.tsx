"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  FileSearch,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Send,
  TriangleAlert,
} from "lucide-react";

import { ApiError, BillOffersApi } from "@/lib/api";
import type {
  BillOfferAgentLog,
  BillOfferIntake,
  BillOfferTaggedEmail,
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
import { Header, getCurrentPageInfo } from "@/components/layout/Header";

const FIELD_LABELS: Record<string, string> = {
  settlement_amount: "Settlement amount",
  total_medical_bills: "Total medical bills",
  medpay_status: "Med-pay status",
  precise_offer_amount: "Precise offer amount",
};

const STATUS_STYLES: Record<string, string> = {
  pending_patient: "bg-amber-100 text-amber-700",
  pending_details: "bg-orange-100 text-orange-700",
  ready_for_phase_2: "bg-emerald-100 text-emerald-700",
  manual_review: "bg-rose-100 text-rose-700",
};

function formatDate(value?: string | null) {
  if (!value) return "-";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function valueOf(facts: Record<string, any> | null | undefined, field: string) {
  const value = facts?.[field];
  if (value && typeof value === "object" && "value" in value) return value.value ?? "";
  return value ?? "";
}

function evidenceOf(facts: Record<string, any> | null | undefined, field: string) {
  const value = facts?.[field];
  if (!value || typeof value !== "object") return "";
  return value.evidence || value.source || "";
}

function normalizeEditableValue(field: string, value: string) {
  if (field === "medpay_status") return value;
  const cleaned = value.replace(/[$,]/g, "").trim();
  if (!cleaned) return "";
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : value;
}

export default function BillOffersPage() {
  const [items, setItems] = useState<BillOfferTaggedEmail[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [selectedIntake, setSelectedIntake] = useState<BillOfferIntake | null>(null);
  const [logs, setLogs] = useState<BillOfferAgentLog[]>([]);
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const currentPage = useMemo(() => getCurrentPageInfo("/bill-offers"), []);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await BillOffersApi.listTaggedEmails({ limit: 200 });
      setItems(response.items);
      if (!selectedConversationId && response.items.length > 0) {
        setSelectedConversationId(response.items[0].front_conversation_id);
        setSelectedIntake(response.items[0].intake ?? null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load Bill Offers");
    } finally {
      setLoading(false);
    }
  }, [selectedConversationId]);

  const loadLogs = useCallback(async (conversationId: string) => {
    try {
      const response = await BillOffersApi.listLogs(conversationId);
      setLogs(response.items);
    } catch {
      setLogs([]);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedConversationId) {
      loadLogs(selectedConversationId);
    }
  }, [selectedConversationId, loadLogs]);

  useEffect(() => {
    if (!selectedIntake) {
      setDraftValues({});
      return;
    }
    const next: Record<string, string> = {};
    Object.keys(FIELD_LABELS).forEach((field) => {
      next[field] = String(
        valueOf(selectedIntake.corrected_facts, field) ||
          valueOf(selectedIntake.extracted_facts, field) ||
          ""
      );
    });
    setDraftValues(next);
  }, [selectedIntake]);

  const visibleItems = items.filter((item) => {
    if (filter === "all") return true;
    if (filter === "unprocessed") return !item.has_intake;
    return item.intake?.status === filter;
  });

  const selectItem = (item: BillOfferTaggedEmail) => {
    setSelectedConversationId(item.front_conversation_id);
    setSelectedIntake(item.intake ?? null);
    setMessage(null);
    setError(null);
  };

  const refreshSelected = async (intake: BillOfferIntake) => {
    setSelectedIntake(intake);
    setItems((prev) =>
      prev.map((item) =>
        item.front_conversation_id === intake.front_conversation_id
          ? { ...item, has_intake: true, intake }
          : item
      )
    );
    await loadLogs(intake.front_conversation_id);
  };

  const handleRunAgent = async () => {
    if (!selectedConversationId) return;
    setBusy("run");
    setMessage(null);
    setError(null);
    try {
      const response = await BillOffersApi.runAgent(selectedConversationId);
      await refreshSelected(response.intake);
      setMessage(`Agent run completed: ${response.run_id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to run agent");
    } finally {
      setBusy(null);
    }
  };

  const handleSave = async () => {
    if (!selectedIntake) return;
    setBusy("save");
    setMessage(null);
    setError(null);
    try {
      const corrected_facts = Object.fromEntries(
        Object.entries(draftValues).map(([field, value]) => [
          field,
          { value: normalizeEditableValue(field, value), source: "user_correction", confidence: 1 },
        ])
      );
      const updated = await BillOffersApi.updateIntake(selectedIntake.id, {
        corrected_facts,
        reviewed_by: "Settings2",
      });
      await refreshSelected(updated);
      setMessage("Corrections saved");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save corrections");
    } finally {
      setBusy(null);
    }
  };

  const handleRerunCheck = async () => {
    if (!selectedIntake) return;
    setBusy("check");
    setMessage(null);
    setError(null);
    try {
      const updated = await BillOffersApi.rerunCheck(selectedIntake.id);
      await refreshSelected(updated);
      setMessage("Completeness check updated");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to rerun check");
    } finally {
      setBusy(null);
    }
  };

  const handleSendReply = async () => {
    if (!selectedIntake) return;
    setBusy("send");
    setMessage(null);
    setError(null);
    try {
      const updated = await BillOffersApi.sendReply(selectedIntake.id);
      await refreshSelected(updated);
      setMessage("Reply sent");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to send reply");
    } finally {
      setBusy(null);
    }
  };

  const handleManualReview = async () => {
    if (!selectedIntake) return;
    setBusy("manual");
    setMessage(null);
    setError(null);
    try {
      const updated = await BillOffersApi.markManualReview(selectedIntake.id, "Marked from Settings2");
      await refreshSelected(updated);
      setMessage("Marked manual review");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to mark manual review");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <Header user="Admin" currentPage={currentPage} />

      <main className="mx-auto max-w-7xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Bill Offers</h1>
            <p className="text-sm text-slate-500">
              Review Bill Offer-tagged conversations, extracted facts, reply drafts, and agent logs.
            </p>
          </div>
          <Button variant="ghost" onClick={loadList} disabled={loading}>
            {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
            Refresh
          </Button>
        </div>

        {message && (
          <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {message}
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[420px_1fr]">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileSearch className="h-5 w-5 text-slate-700" />
                Tagged Conversations
              </CardTitle>
              <CardDescription>Most recent Bill Offer-tagged emails first.</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="mb-4 flex flex-wrap gap-2">
                {[
                  ["all", "All"],
                  ["unprocessed", "Unprocessed"],
                  ["pending_patient", "Pending Patient"],
                  ["pending_details", "Pending Details"],
                  ["ready_for_phase_2", "Ready"],
                  ["manual_review", "Manual"],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    onClick={() => setFilter(value)}
                    className={`rounded-md border px-2.5 py-1 text-xs ${
                      filter === value
                        ? "border-slate-900 bg-slate-900 text-white"
                        : "border-slate-200 bg-white text-slate-600"
                    }`}
                  >
                    {label}
                  </button>
                ))}
              </div>

              {loading ? (
                <div className="py-10 text-center text-sm text-slate-500">Loading...</div>
              ) : visibleItems.length === 0 ? (
                <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                  No Bill Offer-tagged conversations found.
                </div>
              ) : (
                <div className="max-h-[720px] space-y-2 overflow-y-auto pr-1">
                  {visibleItems.map((item) => {
                    const active = item.front_conversation_id === selectedConversationId;
                    return (
                      <button
                        key={item.front_conversation_id}
                        onClick={() => selectItem(item)}
                        className={`w-full rounded-lg border p-3 text-left transition ${
                          active ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-800 hover:border-slate-300"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium">{item.subject || "(No subject)"}</div>
                            <div className={`truncate text-xs ${active ? "text-white/70" : "text-slate-500"}`}>{item.sender}</div>
                          </div>
                          {item.intake ? (
                            <Badge className={STATUS_STYLES[item.intake.status] || "bg-slate-100 text-slate-700"}>
                              {item.intake.status.replace(/_/g, " ")}
                            </Badge>
                          ) : (
                            <Badge className="bg-slate-100 text-slate-700">not processed</Badge>
                          )}
                        </div>
                        <div className={`mt-2 text-xs ${active ? "text-white/70" : "text-slate-500"}`}>
                          {formatDate(item.received_at)}
                        </div>
                        {item.intake?.missing_fields?.length ? (
                          <div className={`mt-1 text-xs ${active ? "text-amber-100" : "text-amber-700"}`}>
                            Missing: {item.intake.missing_fields.join(", ")}
                          </div>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Play className="h-5 w-5 text-slate-700" />
                  Intake Review
                </CardTitle>
                <CardDescription>
                  {selectedConversationId || "Select a tagged conversation"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-5">
                <div className="flex flex-wrap gap-2">
                  <Button onClick={handleRunAgent} disabled={!selectedConversationId || busy === "run"}>
                    {busy === "run" ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}
                    Run Bill Offer Agent
                  </Button>
                  <Button variant="ghost" onClick={handleSave} disabled={!selectedIntake || busy === "save"}>
                    <Save className="mr-2 h-4 w-4" />
                    Save Corrections
                  </Button>
                  <Button variant="ghost" onClick={handleRerunCheck} disabled={!selectedIntake || busy === "check"}>
                    <RefreshCw className="mr-2 h-4 w-4" />
                    Re-run Check
                  </Button>
                  <Button variant="ghost" onClick={handleSendReply} disabled={!selectedIntake?.reply_draft || busy === "send"}>
                    <Send className="mr-2 h-4 w-4" />
                    Approve & Send Reply
                  </Button>
                  <Button variant="ghost" onClick={handleManualReview} disabled={!selectedIntake || busy === "manual"}>
                    <TriangleAlert className="mr-2 h-4 w-4" />
                    Mark Manual Review
                  </Button>
                </div>

                {!selectedIntake ? (
                  <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                    No intake exists yet. Run the agent to create one.
                  </div>
                ) : (
                  <>
                    <div className="grid gap-3 md:grid-cols-4">
                      <Info label="Status" value={selectedIntake.status.replace(/_/g, " ")} />
                      <Info label="Patient ID" value={selectedIntake.patient_id || "-"} />
                      <Info label="Last action" value={selectedIntake.last_agent_action || "-"} />
                      <Info label="Last run" value={selectedIntake.last_agent_run_status || "-"} />
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      {Object.entries(FIELD_LABELS).map(([field, label]) => (
                        <div key={field} className="rounded-lg border border-slate-200 bg-white p-4">
                          <label className="text-sm font-medium text-slate-900">{label}</label>
                          <input
                            value={draftValues[field] ?? ""}
                            onChange={(event) =>
                              setDraftValues((prev) => ({ ...prev, [field]: event.target.value }))
                            }
                            className="mt-2 w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                          />
                          <div className="mt-2 text-xs text-slate-500">
                            Extracted: {String(valueOf(selectedIntake.extracted_facts, field) || "-")}
                          </div>
                          {evidenceOf(selectedIntake.extracted_facts, field) && (
                            <div className="mt-2 rounded-md bg-slate-50 p-2 text-xs text-slate-600">
                              {evidenceOf(selectedIntake.extracted_facts, field)}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>

                    <div className="rounded-lg border border-slate-200 bg-white p-4">
                      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-900">
                        <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                        Reply Preview
                      </div>
                      {selectedIntake.reply_draft ? (
                        <div
                          className="prose prose-sm max-w-none rounded-md bg-slate-50 p-4 text-slate-700"
                          dangerouslySetInnerHTML={{ __html: selectedIntake.reply_draft }}
                        />
                      ) : (
                        <div className="text-sm text-slate-500">No reply draft yet.</div>
                      )}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Agent Logs</CardTitle>
                <CardDescription>Chronological step log for the selected conversation.</CardDescription>
              </CardHeader>
              <CardContent>
                {logs.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                    No agent logs yet.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {logs.map((log) => (
                      <details key={log.id} className="rounded-lg border border-slate-200 bg-white p-3">
                        <summary className="cursor-pointer text-sm">
                          <span className="font-medium text-slate-900">{log.step_name}</span>
                          <Badge className={`ml-2 ${log.step_status === "failed" ? "bg-rose-100 text-rose-700" : "bg-slate-100 text-slate-700"}`}>
                            {log.step_status}
                          </Badge>
                          <span className="ml-2 text-xs text-slate-500">{formatDate(log.created_at)}</span>
                        </summary>
                        <div className="mt-3 space-y-2 text-xs text-slate-600">
                          {log.message && <div>{log.message}</div>}
                          {log.error && <div className="text-rose-700">{log.error}</div>}
                          <pre className="overflow-auto rounded-md bg-slate-50 p-3">
                            {JSON.stringify(
                              {
                                run_id: log.run_id,
                                input: log.input_snapshot,
                                output: log.output_snapshot,
                              },
                              null,
                              2
                            )}
                          </pre>
                        </div>
                      </details>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}
