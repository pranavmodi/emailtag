"use client";

import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronUp, Loader2, Plus, GitBranch, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PipelineApi } from "@/lib/api";
import type { PipelineRecord } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  not_started: "bg-slate-100 text-slate-600",
  sent: "bg-blue-100 text-blue-700",
  replied: "bg-emerald-100 text-emerald-700",
  meeting_booked: "bg-purple-100 text-purple-700",
  closed_won: "bg-green-100 text-green-700",
  closed_lost: "bg-rose-100 text-rose-700",
};

const STATUS_LABELS: Record<string, string> = {
  not_started: "Not Started",
  sent: "Sent",
  replied: "Replied",
  meeting_booked: "Meeting",
  closed_won: "Won",
  closed_lost: "Lost",
};

const FUNNEL_STAGES = ["not_started", "sent", "replied", "meeting_booked"];
const END_STAGES = ["closed_won", "closed_lost"];
const STATUSES = [...FUNNEL_STAGES, ...END_STAGES];

const OUTREACH_TYPES = ["linkedin_connection", "linkedin_inmail", "email", "referral"];

const OUTREACH_TYPE_CONFIG: Record<string, { label: string; color: string }> = {
  linkedin_connection: { label: "LinkedIn", color: "bg-blue-100 text-blue-700" },
  linkedin_inmail:     { label: "InMail",   color: "bg-blue-100 text-blue-700" },
  email:               { label: "Email",    color: "bg-indigo-100 text-indigo-700" },
  referral:            { label: "Referral", color: "bg-emerald-100 text-emerald-700" },
};

function PipelineFunnel({ records }: { records: PipelineRecord[] }) {
  const counts = STATUSES.reduce((acc, s) => {
    acc[s] = records.filter((r) => r.status === s).length;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div className="flex items-center gap-1 flex-wrap">
      {FUNNEL_STAGES.map((stage, i) => (
        <div key={stage} className="flex items-center gap-1">
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
              counts[stage] > 0 ? STATUS_COLORS[stage] : "bg-slate-50 text-slate-300"
            }`}
          >
            {STATUS_LABELS[stage]}{counts[stage] > 0 && ` ${counts[stage]}`}
          </span>
          {i < FUNNEL_STAGES.length - 1 && (
            <span className="text-slate-300 text-xs">›</span>
          )}
        </div>
      ))}
      <span className="text-slate-300 text-xs mx-0.5">·</span>
      {END_STAGES.map((stage) => (
        <span
          key={stage}
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
            counts[stage] > 0 ? STATUS_COLORS[stage] : "bg-slate-50 text-slate-300"
          }`}
        >
          {STATUS_LABELS[stage]}{counts[stage] > 0 && ` ${counts[stage]}`}
        </span>
      ))}
    </div>
  );
}

export function PipelineSection({ pifId }: { pifId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [records, setRecords] = useState<PipelineRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusDropdownOpen, setStatusDropdownOpen] = useState<string | null>(null);

  const [newContactName, setNewContactName] = useState("");
  const [newOutreachType, setNewOutreachType] = useState("linkedin_connection");
  const [newPersona, setNewPersona] = useState("pranav");
  const [newStatus, setNewStatus] = useState("not_started");
  const [newNotes, setNewNotes] = useState("");

  const loadRecords = useCallback(async () => {
    setIsLoading(true);
    try {
      const result = await PipelineApi.listByFirm(pifId);
      setRecords(result.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load pipeline");
    } finally {
      setIsLoading(false);
    }
  }, [pifId]);

  useEffect(() => {
    if (isOpen && records.length === 0) loadRecords();
  }, [isOpen, loadRecords, records.length]);

  // Close status dropdown on outside click
  useEffect(() => {
    if (!statusDropdownOpen) return;
    const handler = () => setStatusDropdownOpen(null);
    window.addEventListener("click", handler);
    return () => window.removeEventListener("click", handler);
  }, [statusDropdownOpen]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      await PipelineApi.create({
        pif_id: pifId,
        contact_name: newContactName || null,
        outreach_type: newOutreachType,
        sender_persona: newPersona || null,
        status: newStatus,
        notes: newNotes || null,
      });
      setNewContactName("");
      setNewNotes("");
      setShowForm(false);
      await loadRecords();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create record");
    } finally {
      setIsSaving(false);
    }
  };

  const handleStatusChange = async (recordId: string, newStat: string) => {
    setStatusDropdownOpen(null);
    try {
      const updated = await PipelineApi.update(recordId, { status: newStat });
      setRecords((prev) => prev.map((r) => (r.id === recordId ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    }
  };

  const handleDelete = async (recordId: string) => {
    if (!confirm("Delete this pipeline record?")) return;
    try {
      await PipelineApi.delete(recordId);
      setRecords((prev) => prev.filter((r) => r.id !== recordId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete record");
    }
  };

  return (
    <div className="md:col-span-2 rounded-xl border border-purple-100 bg-gradient-to-r from-purple-50/40 to-white overflow-hidden">
      {/* Header */}
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setIsOpen(!isOpen)}
      >
        <GitBranch className="h-4 w-4 text-purple-500 shrink-0" />
        <span className="text-sm font-medium text-slate-700 shrink-0">Outreach</span>

        {/* Inline funnel summary when collapsed */}
        <div className="flex-1 min-w-0">
          {records.length > 0 && !isOpen ? (
            <PipelineFunnel records={records} />
          ) : records.length === 0 ? (
            <span className="text-xs text-slate-400">No outreach yet</span>
          ) : null}
        </div>

        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-slate-400 shrink-0" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400 shrink-0" />
        )}
      </button>

      {isOpen && (
        <div className="border-t border-purple-100 px-4 pb-4 pt-3 space-y-3">
          {error && (
            <div className="text-xs text-rose-600 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2">
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="flex items-center justify-center gap-2 text-sm text-slate-500 py-6">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading...
            </div>
          ) : (
            <>
              {records.length > 0 && (
                <>
                  {/* Funnel summary when open */}
                  <div className="pb-2 border-b border-purple-50">
                    <PipelineFunnel records={records} />
                  </div>

                  {/* Records */}
                  <div className="space-y-2">
                    {records.map((record) => {
                      const typeConfig = OUTREACH_TYPE_CONFIG[record.outreach_type] ?? {
                        label: record.outreach_type.replace(/_/g, " "),
                        color: "bg-slate-100 text-slate-600",
                      };
                      return (
                        <div
                          key={record.id}
                          className="group flex items-start gap-3 rounded-lg border border-slate-100 bg-white p-3 hover:border-purple-100 transition-colors"
                        >
                          <div className="flex-1 min-w-0 space-y-1">
                            <div className="flex flex-wrap items-center gap-1.5">
                              {record.contact_name && (
                                <span className="text-sm font-medium text-slate-800">
                                  {record.contact_name}
                                </span>
                              )}
                              <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${typeConfig.color}`}>
                                {typeConfig.label}
                              </span>
                              {record.sender_persona && (
                                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] text-slate-500 capitalize">
                                  {record.sender_persona}
                                </span>
                              )}
                              <span className="text-[10px] text-slate-400 ml-auto">
                                {new Date(record.created_at).toLocaleDateString("en-US", {
                                  month: "short",
                                  day: "numeric",
                                })}
                              </span>
                            </div>
                            {record.notes && (
                              <p className="text-xs text-slate-500 line-clamp-1">{record.notes}</p>
                            )}
                          </div>

                          <div className="flex items-center gap-1.5 shrink-0">
                            {/* Styled status pill with dropdown */}
                            <div className="relative" onClick={(e) => e.stopPropagation()}>
                              <button
                                type="button"
                                onClick={() =>
                                  setStatusDropdownOpen(
                                    statusDropdownOpen === record.id ? null : record.id
                                  )
                                }
                                className={`rounded-full px-2.5 py-0.5 text-[10px] font-medium cursor-pointer hover:opacity-80 transition-opacity ${
                                  STATUS_COLORS[record.status] ?? "bg-slate-100 text-slate-600"
                                }`}
                              >
                                {STATUS_LABELS[record.status] ?? record.status}
                              </button>
                              {statusDropdownOpen === record.id && (
                                <div className="absolute right-0 top-full mt-1 z-20 rounded-lg border border-slate-200 bg-white shadow-lg py-1 min-w-[120px]">
                                  {STATUSES.map((s) => (
                                    <button
                                      key={s}
                                      type="button"
                                      onClick={() => handleStatusChange(record.id, s)}
                                      className={`w-full text-left px-3 py-1.5 text-xs hover:bg-slate-50 transition-colors ${
                                        record.status === s ? "font-semibold text-slate-800" : "text-slate-600"
                                      }`}
                                    >
                                      {STATUS_LABELS[s]}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>

                            {/* Hover-reveal delete */}
                            <button
                              type="button"
                              onClick={() => handleDelete(record.id)}
                              className="opacity-0 group-hover:opacity-100 text-slate-300 hover:text-rose-500 transition-all p-0.5 rounded"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              )}

              {records.length === 0 && !showForm && (
                <div className="py-6 flex flex-col items-center gap-2 text-center">
                  <GitBranch className="h-8 w-8 text-purple-200" />
                  <p className="text-sm text-slate-500">No outreach started yet.</p>
                </div>
              )}

              {/* Add entry form */}
              {showForm ? (
                <form
                  onSubmit={handleCreate}
                  className="space-y-3 rounded-lg border border-purple-100 bg-purple-50/30 p-3 mt-2"
                >
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      placeholder="Contact name"
                      value={newContactName}
                      onChange={(e) => setNewContactName(e.target.value)}
                      className="col-span-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    />
                    <select
                      value={newOutreachType}
                      onChange={(e) => setNewOutreachType(e.target.value)}
                      className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    >
                      {OUTREACH_TYPES.map((t) => (
                        <option key={t} value={t}>
                          {OUTREACH_TYPE_CONFIG[t]?.label ?? t}
                        </option>
                      ))}
                    </select>
                    <select
                      value={newPersona}
                      onChange={(e) => setNewPersona(e.target.value)}
                      className="rounded-lg border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    >
                      <option value="pranav">Pranav</option>
                      <option value="neha">Neha</option>
                    </select>
                    <select
                      value={newStatus}
                      onChange={(e) => setNewStatus(e.target.value)}
                      className="col-span-2 rounded-lg border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                      ))}
                    </select>
                  </div>
                  <textarea
                    placeholder="Notes (optional)"
                    value={newNotes}
                    onChange={(e) => setNewNotes(e.target.value)}
                    rows={2}
                    className="w-full rounded-lg border border-slate-200 px-3 py-1.5 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-purple-400"
                  />
                  <div className="flex gap-2">
                    <Button type="submit" disabled={isSaving} className="text-xs h-7">
                      {isSaving ? <Loader2 className="h-3 w-3 animate-spin" /> : "Save"}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      className="text-xs h-7"
                      onClick={() => setShowForm(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                </form>
              ) : (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setShowForm(true)}
                  className="text-xs h-7 text-purple-600 hover:bg-purple-100"
                >
                  <Plus className="h-3 w-3 mr-1" />
                  Add Entry
                </Button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
