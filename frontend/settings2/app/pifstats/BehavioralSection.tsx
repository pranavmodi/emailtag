"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Loader2, BarChart2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PifApi } from "@/lib/api";
import type { BehavioralData, PifInfoResponse } from "@/lib/types";

const TOPIC_COLORS: Record<string, string> = {
  status_update_request: "bg-blue-400",
  billing_dispute: "bg-rose-400",
  scheduling_request: "bg-emerald-400",
  rush_request: "bg-orange-400",
  lien_negotiation: "bg-purple-400",
  records_request: "bg-amber-400",
  general_inquiry: "bg-slate-400",
  other: "bg-slate-300",
};

const TOPIC_LABELS: Record<string, string> = {
  status_update_request: "Status Updates",
  billing_dispute: "Billing Disputes",
  scheduling_request: "Scheduling",
  rush_request: "Rush Requests",
  lien_negotiation: "Lien Negotiation",
  records_request: "Records Requests",
  general_inquiry: "General Inquiry",
  other: "Other",
};

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  return (
    <div className="flex items-end gap-0.5 h-10">
      {values.map((v, i) => (
        <div
          key={i}
          className="flex-1 bg-indigo-400 rounded-sm opacity-80"
          style={{ height: `${Math.max((v / max) * 40, 2)}px` }}
          title={`${v} emails`}
        />
      ))}
    </div>
  );
}

export function BehavioralSection({
  firm,
  onAnalyzeComplete,
}: {
  firm: PifInfoResponse;
  onAnalyzeComplete: (firmId: string) => void;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [analyzeMsg, setAnalyzeMsg] = useState<string | null>(null);

  const bd: BehavioralData | null = firm.behavioral_data as BehavioralData | null;

  const handleAnalyze = async (e: React.MouseEvent) => {
    e.stopPropagation();
    setIsAnalyzing(true);
    setAnalyzeError(null);
    setAnalyzeMsg(null);

    try {
      const result = await PifApi.analyzeBehavior(firm.id);
      setAnalyzeMsg(`Analysis queued (task: ${result.task_id}). Refresh in a moment.`);
      // Notify parent after a short delay so user sees the message
      setTimeout(() => onAnalyzeComplete(firm.id), 3000);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const topicEntries = bd
    ? Object.entries(bd.topic_distribution)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
    : [];
  const totalTopics = topicEntries.reduce((s, [, v]) => s + v, 0) || 1;

  return (
    <div className="md:col-span-2 rounded-lg border border-indigo-100 bg-indigo-50/30">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left"
        onClick={() => setIsOpen(!isOpen)}
      >
        <div className="flex items-center gap-2">
          <BarChart2 className="h-4 w-4 text-indigo-500" />
          <span className="text-sm font-medium text-slate-700">
            Behavioral Intelligence
          </span>
          {bd && (
            <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-xs text-indigo-700">
              {bd.total_email_count} emails analyzed
            </span>
          )}
          {!bd && (
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
              Not analyzed yet
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="h-7 px-2 text-xs text-indigo-600 hover:bg-indigo-100"
          >
            {isAnalyzing ? (
              <><Loader2 className="h-3 w-3 mr-1 animate-spin" /> Analyzing...</>
            ) : (
              bd ? "Re-Analyze" : "Analyze"
            )}
          </Button>
          {isOpen ? (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </button>

      {analyzeError && (
        <div className="px-4 pb-2 text-xs text-rose-600">{analyzeError}</div>
      )}
      {analyzeMsg && (
        <div className="px-4 pb-2 text-xs text-emerald-600">{analyzeMsg}</div>
      )}

      {isOpen && bd && (
        <div className="border-t border-indigo-100 px-4 pb-4 pt-3 space-y-4">
          {/* Volume Sparkline */}
          <div>
            <p className="text-xs font-medium text-slate-600 mb-1">
              Monthly Email Volume (last 3 months)
            </p>
            <Sparkline values={bd.monthly_email_volume} />
            <div className="flex justify-between text-xs text-slate-400 mt-1">
              {["3mo ago", "2mo ago", "last month"].map((l) => (
                <span key={l}>{l}</span>
              ))}
            </div>
          </div>

          {/* Recency */}
          {bd.days_since_last_contact !== null && (
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-600">Last contact:</span>
              <span
                className={`text-xs font-medium rounded-full px-2 py-0.5 ${
                  bd.days_since_last_contact > 60
                    ? "bg-rose-100 text-rose-700"
                    : bd.days_since_last_contact > 30
                    ? "bg-amber-100 text-amber-700"
                    : "bg-emerald-100 text-emerald-700"
                }`}
              >
                {bd.days_since_last_contact} days ago
              </span>
              {bd.peak_contact_days.length > 0 && (
                <span className="text-xs text-slate-500">
                  Peak: {bd.peak_contact_days.join(", ")}
                </span>
              )}
              {bd.after_hours_ratio > 0 && (
                <span className="text-xs text-slate-500">
                  {Math.round(bd.after_hours_ratio * 100)}% after-hours
                </span>
              )}
            </div>
          )}

          {/* Topic Distribution */}
          {topicEntries.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-600 mb-2">Topic Distribution</p>
              <div className="space-y-1.5">
                {topicEntries.map(([topic, count]) => {
                  const pct = Math.round((count / totalTopics) * 100);
                  return (
                    <div key={topic} className="flex items-center gap-2">
                      <span className="text-xs text-slate-600 w-36 shrink-0">
                        {TOPIC_LABELS[topic] ?? topic}
                      </span>
                      <div className="flex-1 h-2 rounded-full bg-slate-100">
                        <div
                          className={`h-2 rounded-full ${TOPIC_COLORS[topic] ?? "bg-slate-400"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                      <span className="text-xs text-slate-500 w-8 text-right">{pct}%</span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Sender Roles */}
          {Object.keys(bd.sender_roles).length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-600 mb-1">Sender Roles</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(bd.sender_roles).map(([role, count]) => (
                  <span
                    key={role}
                    className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600"
                  >
                    {role.replace("_", " ")}: {count}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {isOpen && !bd && (
        <div className="border-t border-indigo-100 px-4 pb-4 pt-3 text-sm text-slate-500">
          No behavioral data yet. Click &quot;Analyze&quot; to start analysis.
        </div>
      )}
    </div>
  );
}
