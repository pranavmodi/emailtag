"use client";

import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronUp, Loader2, Plus, GitBranch } from "lucide-react";
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

const STATUSES = [
  "not_started",
  "sent",
  "replied",
  "meeting_booked",
  "closed_won",
  "closed_lost",
];

const OUTREACH_TYPES = [
  "linkedin_connection",
  "linkedin_inmail",
  "email",
  "referral",
];

export function PipelineSection({ pifId }: { pifId: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [records, setRecords] = useState<PipelineRecord[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // New record form state
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
    if (isOpen && records.length === 0) {
      loadRecords();
    }
  }, [isOpen, loadRecords, records.length]);

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
    try {
      const updated = await PipelineApi.update(recordId, { status: newStat });
      setRecords((prev) =>
        prev.map((r) => (r.id === recordId ? updated : r))
      );
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
    <div className="md:col-span-2 rounded-lg border border-purple-100 bg-purple-50/20">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-purple-500" />
          <span className="text-sm font-medium text-slate-700">
            Outreach Pipeline
          </span>
          {records.length > 0 && (
            <span className="rounded-full bg-purple-100 px-2 py-0.5 text-xs text-purple-700">
              {records.length} records
            </span>
          )}
        </div>
        {isOpen ? (
          <ChevronUp className="h-4 w-4 text-slate-400" />
        ) : (
          <ChevronDown className="h-4 w-4 text-slate-400" />
        )}
      </button>

      {isOpen && (
        <div className="border-t border-purple-100 px-4 pb-4 pt-3 space-y-3">
          {error && (
            <div className="text-xs text-rose-600 rounded border border-rose-100 bg-rose-50 px-3 py-2">
              {error}
            </div>
          )}

          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading...
            </div>
          ) : (
            <>
              {/* Records Timeline */}
              {records.length > 0 && (
                <div className="space-y-2">
                  {records.map((record) => (
                    <div
                      key={record.id}
                      className="flex items-start gap-3 rounded-lg border border-slate-100 bg-white p-3"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          {record.contact_name && (
                            <span className="text-sm font-medium text-slate-800">
                              {record.contact_name}
                            </span>
                          )}
                          <span className="text-xs text-slate-500">
                            {record.outreach_type.replace("_", " ")}
                          </span>
                          {record.sender_persona && (
                            <span className="text-xs rounded bg-slate-100 px-1.5 py-0.5 text-slate-600">
                              {record.sender_persona}
                            </span>
                          )}
                        </div>
                        {record.notes && (
                          <p className="mt-1 text-xs text-slate-500 line-clamp-2">
                            {record.notes}
                          </p>
                        )}
                        <div className="mt-1 text-xs text-slate-400">
                          {new Date(record.created_at).toLocaleDateString()}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <select
                          value={record.status}
                          onChange={(e) => handleStatusChange(record.id, e.target.value)}
                          className={`rounded-full px-2 py-0.5 text-xs border-0 cursor-pointer ${
                            STATUS_COLORS[record.status] ?? "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {STATUSES.map((s) => (
                            <option key={s} value={s}>
                              {s.replace("_", " ")}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => handleDelete(record.id)}
                          className="text-slate-300 hover:text-rose-500 text-xs"
                        >
                          ×
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {records.length === 0 && !showForm && (
                <p className="text-sm text-slate-500">No outreach records yet.</p>
              )}

              {/* Add Entry Form */}
              {showForm ? (
                <form onSubmit={handleCreate} className="space-y-3 rounded-lg border border-purple-100 bg-purple-50/30 p-3">
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      type="text"
                      placeholder="Contact name"
                      value={newContactName}
                      onChange={(e) => setNewContactName(e.target.value)}
                      className="col-span-2 rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    />
                    <select
                      value={newOutreachType}
                      onChange={(e) => setNewOutreachType(e.target.value)}
                      className="rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    >
                      {OUTREACH_TYPES.map((t) => (
                        <option key={t} value={t}>{t.replace("_", " ")}</option>
                      ))}
                    </select>
                    <select
                      value={newPersona}
                      onChange={(e) => setNewPersona(e.target.value)}
                      className="rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    >
                      <option value="pranav">Pranav</option>
                      <option value="neha">Neha</option>
                    </select>
                    <select
                      value={newStatus}
                      onChange={(e) => setNewStatus(e.target.value)}
                      className="rounded border border-slate-200 px-2 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400"
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{s.replace("_", " ")}</option>
                      ))}
                    </select>
                  </div>
                  <textarea
                    placeholder="Notes (optional)"
                    value={newNotes}
                    onChange={(e) => setNewNotes(e.target.value)}
                    rows={2}
                    className="w-full rounded border border-slate-200 px-2 py-1.5 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-purple-400"
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
