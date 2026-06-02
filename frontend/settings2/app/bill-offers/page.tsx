"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  FileSearch,
  FileText,
  History,
  Loader2,
  Play,
  RefreshCw,
  Save,
  Send,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";

import { ApiError, BillOffersApi } from "@/lib/api";
import type {
  BillOfferAgentLog,
  BillOfferCorrectionAudit,
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
  precise_offer_amount: "Precise offer amount",
  settlement_amount: "Settlement amount",
  total_medical_bills: "Total medical bills",
  medpay_status: "Med-pay status",
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

function formatMoney(value: any) {
  if (value === null || value === undefined || value === "") return "-";
  const parsed = Number(String(value).replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? `$${parsed.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : String(value);
}

function valueOf(facts: Record<string, any> | null | undefined, field: string) {
  const value = facts?.[field];
  if (value && typeof value === "object" && "value" in value) return value.value ?? "";
  return value ?? "";
}

function factOf(facts: Record<string, any> | null | undefined, field: string) {
  const value = facts?.[field];
  return value && typeof value === "object" ? value : null;
}

function normalizeEditableValue(field: string, value: string) {
  if (field === "medpay_status") return value;
  const cleaned = value.replace(/[$,]/g, "").trim();
  if (!cleaned) return "";
  const parsed = Number(cleaned);
  return Number.isFinite(parsed) ? parsed : value;
}

function frontUrl(conversationId: string | null) {
  return conversationId ? `https://app.frontapp.com/open/${encodeURIComponent(conversationId)}` : "";
}

function confidenceText(value: any) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

export default function BillOffersPage() {
  const [items, setItems] = useState<BillOfferTaggedEmail[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [selectedIntake, setSelectedIntake] = useState<BillOfferIntake | null>(null);
  const [logs, setLogs] = useState<BillOfferAgentLog[]>([]);
  const [audits, setAudits] = useState<BillOfferCorrectionAudit[]>([]);
  const [draftValues, setDraftValues] = useState<Record<string, string>>({});
  const [patientIdDraft, setPatientIdDraft] = useState("");
  const [reviewRequired, setReviewRequired] = useState(true);
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const currentPage = useMemo(() => getCurrentPageInfo("/bill-offers"), []);
  const selectedItem = items.find((item) => item.front_conversation_id === selectedConversationId) || null;

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [response, settings] = await Promise.all([
        BillOffersApi.listTaggedEmails({ limit: 200 }),
        BillOffersApi.getSettings(),
      ]);
      setItems(response.items);
      setReviewRequired(settings.review_required);
      const selected = selectedConversationId
        ? response.items.find((item) => item.front_conversation_id === selectedConversationId)
        : response.items[0];
      if (selected) {
        setSelectedConversationId(selected.front_conversation_id);
        setSelectedIntake(selected.intake ?? null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load Bill Offers");
    } finally {
      setLoading(false);
    }
  }, [selectedConversationId]);

  const loadConversationDetails = useCallback(async (conversationId: string) => {
    const [logResponse, auditResponse] = await Promise.allSettled([
      BillOffersApi.listLogs(conversationId),
      BillOffersApi.listCorrectionAudits(conversationId),
    ]);
    setLogs(logResponse.status === "fulfilled" ? logResponse.value.items : []);
    setAudits(auditResponse.status === "fulfilled" ? auditResponse.value.items : []);
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (selectedConversationId) {
      loadConversationDetails(selectedConversationId);
    }
  }, [selectedConversationId, loadConversationDetails]);

  useEffect(() => {
    if (!selectedIntake) {
      setDraftValues({});
      setPatientIdDraft("");
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
    setPatientIdDraft(selectedIntake.patient_id || "");
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
    await loadConversationDetails(intake.front_conversation_id);
  };

  const handleRunAgent = async () => {
    if (!selectedConversationId) return;
    setBusy("run");
    setMessage(null);
    setError(null);
    try {
      const response = await BillOffersApi.runAgent(selectedConversationId);
      await refreshSelected(response.intake);
      if (response.status === "queued") {
        setMessage(`Agent run queued: ${response.run_id}`);
        window.setTimeout(() => {
          loadList();
          loadConversationDetails(selectedConversationId);
        }, 3000);
      } else {
        setMessage(`Agent run completed: ${response.run_id}`);
      }
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
        patient_id: patientIdDraft || null,
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

  const handleToggleReviewRequired = async () => {
    setBusy("review-required");
    setError(null);
    try {
      const updated = await BillOffersApi.setReviewRequired(!reviewRequired);
      setReviewRequired(updated.review_required);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update review setting");
    } finally {
      setBusy(null);
    }
  };

  const patientData = selectedIntake?.patient_data || {};
  const studies = Array.isArray(patientData.studies) ? patientData.studies : [];
  const documentFacts = Array.isArray(selectedIntake?.extracted_facts?._document_facts)
    ? selectedIntake?.extracted_facts?._document_facts
    : [];
  const conflicts = Array.isArray(selectedIntake?.extracted_facts?._conflicts)
    ? selectedIntake?.extracted_facts?._conflicts
    : [];

  return (
    <div className="min-h-screen bg-slate-50">
      <Header user="Admin" currentPage={currentPage} />

      <main className="mx-auto max-w-[1520px] px-6 py-6">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Bill Offers</h1>
            <p className="text-sm text-slate-500">Phase 1 intake queue</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" onClick={handleToggleReviewRequired} disabled={busy === "review-required"}>
              <ShieldCheck className="mr-2 h-4 w-4" />
              {reviewRequired ? "Review required" : "Auto-send enabled"}
            </Button>
            <Button variant="ghost" onClick={loadList} disabled={loading}>
              {loading ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCw className="mr-2 h-4 w-4" />}
              Refresh
            </Button>
          </div>
        </div>

        {message && (
          <div className="mb-4 rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {message}
          </div>
        )}
        {error && (
          <div className="mb-4 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <div className="grid gap-5 xl:grid-cols-[520px_1fr]">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <FileSearch className="h-5 w-5 text-slate-700" />
                Tagged Conversations
              </CardTitle>
              <CardDescription>{items.length} conversations</CardDescription>
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
                <div className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                  No Bill Offer-tagged conversations found.
                </div>
              ) : (
                <div className="max-h-[780px] overflow-y-auto rounded-md border border-slate-200 bg-white">
                  <table className="w-full text-left text-xs">
                    <thead className="sticky top-0 bg-slate-100 text-slate-600">
                      <tr>
                        <th className="px-3 py-2 font-medium">Conversation</th>
                        <th className="px-3 py-2 font-medium">Patient</th>
                        <th className="px-3 py-2 font-medium">Status</th>
                        <th className="px-3 py-2 font-medium">Confidence</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleItems.map((item) => {
                        const active = item.front_conversation_id === selectedConversationId;
                        const intake = item.intake;
                        return (
                          <tr
                            key={item.front_conversation_id}
                            onClick={() => selectItem(item)}
                            className={`cursor-pointer border-t border-slate-100 ${
                              active ? "bg-slate-900 text-white" : "hover:bg-slate-50"
                            }`}
                          >
                            <td className="px-3 py-3 align-top">
                              <div className="max-w-[210px] truncate font-medium">{item.subject || "(No subject)"}</div>
                              <div className={`mt-1 truncate ${active ? "text-white/70" : "text-slate-500"}`}>
                                {item.front_conversation_id}
                              </div>
                              <div className={`truncate ${active ? "text-white/70" : "text-slate-500"}`}>{item.sender}</div>
                              <div className={active ? "text-white/70" : "text-slate-500"}>{formatDate(item.received_at)}</div>
                            </td>
                            <td className="px-3 py-3 align-top">
                              <div>{intake?.patient_data?.patient_name || "-"}</div>
                              <div className={active ? "text-white/70" : "text-slate-500"}>{intake?.patient_id || "-"}</div>
                            </td>
                            <td className="px-3 py-3 align-top">
                              {intake ? (
                                <Badge className={STATUS_STYLES[intake.status] || "bg-slate-100 text-slate-700"}>
                                  {intake.status.replace(/_/g, " ")}
                                </Badge>
                              ) : (
                                <Badge className="bg-slate-100 text-slate-700">not processed</Badge>
                              )}
                              {intake?.missing_fields?.length ? (
                                <div className={`mt-1 ${active ? "text-amber-100" : "text-amber-700"}`}>
                                  {intake.missing_fields.join(", ")}
                                </div>
                              ) : null}
                              <div className={active ? "text-white/70" : "text-slate-500"}>
                                {intake?.last_agent_run_status || "-"}
                              </div>
                            </td>
                            <td className="px-3 py-3 align-top">
                              <div>{confidenceText(intake?.confidence?.average)}</div>
                              <div className={active ? "text-white/70" : "text-slate-500"}>
                                {formatDate(intake?.updated_at)}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="space-y-5">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Play className="h-5 w-5 text-slate-700" />
                  Intake Review
                </CardTitle>
                <CardDescription>{selectedConversationId || "Select a conversation"}</CardDescription>
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
                  {selectedConversationId && (
                    <a
                      href={frontUrl(selectedConversationId)}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 hover:border-slate-300"
                    >
                      <ExternalLink className="mr-2 h-4 w-4" />
                      Front
                    </a>
                  )}
                </div>

                {!selectedIntake ? (
                  <div className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                    No intake exists yet. Run the agent to create one.
                  </div>
                ) : (
                  <>
                    <div className="grid gap-3 md:grid-cols-4">
                      <Info label="Status" value={selectedIntake.status.replace(/_/g, " ")} />
                      <Info label="Original Sender" value={selectedIntake.original_sender_email || selectedItem?.sender || "-"} />
                      <Info label="Last action" value={selectedIntake.last_agent_action || "-"} />
                      <Info label="Last run" value={selectedIntake.last_agent_run_status || "-"} />
                    </div>

                    <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
                      <section className="rounded-md border border-slate-200 bg-white p-4">
                        <h3 className="text-sm font-semibold text-slate-900">Patient</h3>
                        <label className="mt-3 block text-xs font-medium text-slate-500">Patient ID</label>
                        <input
                          value={patientIdDraft}
                          onChange={(event) => setPatientIdDraft(event.target.value)}
                          className="mt-1 w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
                        />
                        <div className="mt-3 space-y-1 text-sm text-slate-700">
                          <div>{patientData.patient_name || "-"}</div>
                          <div>DOB: {patientData.dob || "-"}</div>
                          <div>DOI: {patientData.doi || "-"}</div>
                          <div>Lien: {formatMoney(patientData.lien_total)}</div>
                        </div>
                        <JsonPreview title="Patient match" value={selectedIntake.patient_match} />
                      </section>

                      <section className="rounded-md border border-slate-200 bg-white p-4">
                        <h3 className="text-sm font-semibold text-slate-900">Studies</h3>
                        {studies.length === 0 ? (
                          <div className="mt-3 text-sm text-slate-500">No study details available.</div>
                        ) : (
                          <div className="mt-3 overflow-x-auto">
                            <table className="w-full text-left text-xs">
                              <thead className="bg-slate-50 text-slate-500">
                                <tr>
                                  <th className="px-2 py-2 font-medium">Study</th>
                                  <th className="px-2 py-2 font-medium">Date</th>
                                  <th className="px-2 py-2 text-right font-medium">Billed</th>
                                </tr>
                              </thead>
                              <tbody>
                                {studies.map((study: any, index: number) => (
                                  <tr key={`${study.description || study.study || "study"}-${index}`} className="border-t border-slate-100">
                                    <td className="px-2 py-2">{study.description || study.studyDescription || study.study || study.modality || "Study"}</td>
                                    <td className="px-2 py-2">{study.date || study.studyDate || study.dos || "-"}</td>
                                    <td className="px-2 py-2 text-right">{formatMoney(study.billedAmount || study.billed_amount || study.billAmount || study.amount)}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        )}
                      </section>
                    </div>

                    <section className="rounded-md border border-slate-200 bg-white p-4">
                      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold text-slate-900">Offer Facts</h3>
                        {selectedIntake.missing_fields?.length ? (
                          <Badge className="bg-amber-100 text-amber-700">
                            Missing: {selectedIntake.missing_fields.join(", ")}
                          </Badge>
                        ) : (
                          <Badge className="bg-emerald-100 text-emerald-700">Complete</Badge>
                        )}
                      </div>
                      <div className="grid gap-4 md:grid-cols-2">
                        {Object.entries(FIELD_LABELS).map(([field, label]) => (
                          <FactEditor
                            key={field}
                            label={label}
                            value={draftValues[field] ?? ""}
                            extractedFact={factOf(selectedIntake.extracted_facts, field)}
                            correctedFact={factOf(selectedIntake.corrected_facts, field)}
                            onChange={(value) => setDraftValues((prev) => ({ ...prev, [field]: value }))}
                          />
                        ))}
                      </div>
                      {conflicts.length ? <JsonPreview title="Conflicts" value={conflicts} open /> : null}
                    </section>

                    <section className="rounded-md border border-slate-200 bg-white p-4">
                      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                        <FileText className="h-4 w-4" />
                        Document Facts
                      </h3>
                      {documentFacts.length === 0 ? (
                        <div className="mt-3 text-sm text-slate-500">No document-derived facts.</div>
                      ) : (
                        <div className="mt-3 space-y-3">
                          {documentFacts.map((doc: any, index: number) => (
                            <div key={`${doc.document_id || "doc"}-${index}`} className="rounded-md border border-slate-200 p-3 text-sm">
                              <div className="font-medium text-slate-900">{doc.filename || doc.document_id || `Document ${index + 1}`}</div>
                              <div className="text-xs text-slate-500">{doc.document_type || "-"} {doc.page ? `page ${doc.page}` : ""}</div>
                              <div className="mt-2 space-y-1">
                                {(doc.extracted_fields || []).map((fact: any, factIndex: number) => (
                                  <div key={`${fact.field}-${factIndex}`} className="rounded bg-slate-50 p-2 text-xs text-slate-700">
                                    <span className="font-medium">{fact.field}:</span> {String(fact.value ?? "-")}
                                    <div className="mt-1 text-slate-500">{fact.evidence || fact.ambiguity_notes || "-"}</div>
                                  </div>
                                ))}
                              </div>
                              {doc.notes && <div className="mt-2 text-xs text-slate-500">{doc.notes}</div>}
                            </div>
                          ))}
                        </div>
                      )}
                    </section>

                    <section className="rounded-md border border-slate-200 bg-white p-4">
                      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
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
                    </section>
                  </>
                )}
              </CardContent>
            </Card>

            <div className="grid gap-5 lg:grid-cols-2">
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <History className="h-5 w-5 text-slate-700" />
                    Correction Audit
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {audits.length === 0 ? (
                    <div className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                      No corrections recorded.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {audits.map((audit) => (
                        <details key={audit.id} className="rounded-md border border-slate-200 bg-white p-3">
                          <summary className="cursor-pointer text-sm">
                            <span className="font-medium text-slate-900">{audit.field_name}</span>
                            <span className="ml-2 text-xs text-slate-500">{formatDate(audit.created_at)}</span>
                          </summary>
                          <pre className="mt-3 overflow-auto rounded-md bg-slate-50 p-3 text-xs text-slate-600">
                            {JSON.stringify({ previous: audit.previous_value, next: audit.new_value, changed_by: audit.changed_by }, null, 2)}
                          </pre>
                        </details>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Agent Logs</CardTitle>
                </CardHeader>
                <CardContent>
                  {logs.length === 0 ? (
                    <div className="rounded-md border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">
                      No agent logs yet.
                    </div>
                  ) : (
                    <div className="max-h-[520px] space-y-2 overflow-y-auto">
                      {logs.map((log) => (
                        <details key={log.id} className="rounded-md border border-slate-200 bg-white p-3">
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
        </div>
      </main>
    </div>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3">
      <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 truncate text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}

function FactEditor({
  label,
  value,
  extractedFact,
  correctedFact,
  onChange,
}: {
  label: string;
  value: string;
  extractedFact: Record<string, any> | null;
  correctedFact: Record<string, any> | null;
  onChange: (value: string) => void;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <label className="text-sm font-medium text-slate-900">{label}</label>
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-md border border-slate-200 px-3 py-2 text-sm"
      />
      <div className="mt-3 grid gap-2 text-xs text-slate-600">
        <div className="rounded bg-slate-50 p-2">
          <div className="font-medium text-slate-700">Extracted</div>
          <div>{String(extractedFact?.value ?? "-")}</div>
          <div className="mt-1 text-slate-500">
            Source: {extractedFact?.source || "-"} {extractedFact?.source_id ? `(${extractedFact.source_id})` : ""}
          </div>
          <div className="text-slate-500">Confidence: {confidenceText(extractedFact?.confidence)}</div>
          {extractedFact?.is_ambiguous && (
            <div className="mt-1 text-amber-700">{extractedFact.ambiguity_notes || "Ambiguous"}</div>
          )}
          {extractedFact?.evidence && <div className="mt-2 text-slate-600">{extractedFact.evidence}</div>}
        </div>
        {correctedFact && (
          <div className="rounded bg-emerald-50 p-2 text-emerald-800">
            <div className="font-medium">Corrected</div>
            <div>{String(correctedFact.value ?? "-")}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function JsonPreview({ title, value, open = false }: { title: string; value: any; open?: boolean }) {
  if (!value) return null;
  return (
    <details open={open} className="mt-3 rounded-md border border-slate-200 bg-slate-50 p-3">
      <summary className="cursor-pointer text-xs font-medium text-slate-700">{title}</summary>
      <pre className="mt-2 max-h-72 overflow-auto text-xs text-slate-600">
        {JSON.stringify(value, null, 2)}
      </pre>
    </details>
  );
}
