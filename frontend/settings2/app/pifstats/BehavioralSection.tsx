"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Loader2, BarChart2, Clock, Zap } from "lucide-react";
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

function getMonthLabels(): string[] {
  const now = new Date();
  return [2, 1, 0].map((offset) => {
    const d = new Date(now.getFullYear(), now.getMonth() - offset, 1);
    return d.toLocaleString("default", { month: "short" });
  });
}

function Sparkline({ values }: { values: number[] }) {
  const max = Math.max(...values, 1);
  const months = getMonthLabels();
  return (
    <div>
      <div className="flex items-end gap-1.5 h-12">
        {values.map((v, i) => (
          <div key={i} className="flex-1 flex flex-col justify-end">
            <div
              className="w-full rounded-t-sm bg-indigo-400 opacity-75 transition-all"
              style={{ height: `${Math.max((v / max) * 44, 3)}px` }}
              title={`${v} emails`}
            />
          </div>
        ))}
      </div>
      <div className="flex gap-1.5 mt-1">
        {months.map((m, i) => (
          <span key={i} className="flex-1 text-center text-[10px] text-slate-400">{m}</span>
        ))}
      </div>
    </div>
  );
}

function RecencyPill({ days }: { days: number }) {
  if (days > 60)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-700">
        <Clock className="h-3 w-3" /> {days}d ago
      </span>
    );
  if (days > 30)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
        <Clock className="h-3 w-3" /> {days}d ago
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700">
      <Clock className="h-3 w-3" /> {days}d ago
    </span>
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
      setAnalyzeMsg(`Queued (task: ${result.task_id}). Refresh in a moment.`);
      setTimeout(() => onAnalyzeComplete(firm.id), 3000);
    } catch (err) {
      setAnalyzeError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const topicEntries = bd
    ? Object.entries(bd.topic_distribution).sort((a, b) => b[1] - a[1]).slice(0, 6)
    : [];
  const totalTopics = topicEntries.reduce((s, [, v]) => s + v, 0) || 1;
  const topPain = topicEntries[0]?.[0];

  return (
    <div className="md:col-span-2 rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50/50 to-white overflow-hidden">
      {/* Header row */}
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
        onClick={() => setIsOpen(!isOpen)}
      >
        <BarChart2 className="h-4 w-4 text-indigo-500 shrink-0" />
        <span className="text-sm font-medium text-slate-700 shrink-0">Behavioral</span>

        {/* Inline summary — visible when collapsed */}
        <div className="flex flex-wrap items-center gap-2 flex-1 min-w-0">
          {bd ? (
            <>
              <span className="text-xs text-slate-400">{bd.total_email_count} emails</span>
              {bd.days_since_last_contact !== null && (
                <RecencyPill days={bd.days_since_last_contact} />
              )}
              {topPain && (
                <span className="hidden sm:inline-flex items-center gap-1 text-xs text-slate-500 truncate">
                  <Zap className="h-3 w-3 text-orange-400 shrink-0" />
                  {TOPIC_LABELS[topPain] ?? topPain}
                </span>
              )}
            </>
          ) : (
            <span className="text-xs text-slate-400">Not analyzed</span>
          )}
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="ghost"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="h-7 px-2 text-xs text-indigo-600 hover:bg-indigo-100"
          >
            {isAnalyzing ? (
              <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Analyzing...</>
            ) : bd ? "Re-Analyze" : "Analyze"}
          </Button>
          {isOpen ? (
            <ChevronUp className="h-4 w-4 text-slate-400" />
          ) : (
            <ChevronDown className="h-4 w-4 text-slate-400" />
          )}
        </div>
      </button>

      {(analyzeError || analyzeMsg) && (
        <div className={`px-4 pb-2 text-xs ${analyzeError ? "text-rose-600" : "text-emerald-600"}`}>
          {analyzeError ?? analyzeMsg}
        </div>
      )}

      {/* Expanded: has data */}
      {isOpen && bd && (
        <div className="border-t border-indigo-100 px-4 pb-4 pt-3 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            {/* Sparkline */}
            <div>
              <p className="text-xs font-medium text-slate-500 mb-2">Monthly Volume</p>
              <Sparkline values={bd.monthly_email_volume} />
            </div>

            {/* Quick stats */}
            <div className="space-y-2">
              <p className="text-xs font-medium text-slate-500">Signals</p>
              {bd.days_since_last_contact !== null && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Last contact</span>
                  <RecencyPill days={bd.days_since_last_contact} />
                </div>
              )}
              {bd.peak_contact_days.length > 0 && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">Peak days</span>
                  <span className="text-xs text-slate-600">{bd.peak_contact_days.join(", ")}</span>
                </div>
              )}
              {bd.after_hours_ratio > 0.05 && (
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-500">After-hours</span>
                  <span className="text-xs font-medium text-amber-600">
                    {Math.round(bd.after_hours_ratio * 100)}%
                  </span>
                </div>
              )}
              {Object.keys(bd.sender_roles).length > 0 && (
                <div className="flex items-start justify-between gap-2">
                  <span className="text-xs text-slate-500 shrink-0">Senders</span>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {Object.entries(bd.sender_roles).slice(0, 3).map(([role, count]) => (
                      <span
                        key={role}
                        className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-600 capitalize"
                      >
                        {role.replace(/_/g, " ")} {count}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Topic bars */}
          {topicEntries.length > 0 && (
            <div>
              <p className="text-xs font-medium text-slate-500 mb-2">Email Topics</p>
              <div className="space-y-2">
                {topicEntries.map(([topic, count]) => {
                  const pct = Math.round((count / totalTopics) * 100);
                  return (
                    <div key={topic}>
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-xs text-slate-600">{TOPIC_LABELS[topic] ?? topic}</span>
                        <span className="text-[10px] text-slate-400">{count} · {pct}%</span>
                      </div>
                      <div className="h-1.5 rounded-full bg-slate-100">
                        <div
                          className={`h-1.5 rounded-full transition-all ${TOPIC_COLORS[topic] ?? "bg-slate-400"}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Expanded: no data */}
      {isOpen && !bd && (
        <div className="border-t border-indigo-100 px-4 py-8 flex flex-col items-center gap-3 text-center">
          <BarChart2 className="h-8 w-8 text-indigo-200" />
          <p className="text-sm text-slate-500">No behavioral data yet.</p>
          <p className="text-xs text-slate-400">
            Analyzes email patterns, topic distribution, and contact frequency.
          </p>
          <Button
            variant="ghost"
            onClick={handleAnalyze}
            disabled={isAnalyzing}
            className="text-xs text-indigo-600 hover:bg-indigo-100"
          >
            {isAnalyzing ? (
              <><Loader2 className="h-3 w-3 mr-1 animate-spin" />Analyzing...</>
            ) : "Run Analysis"}
          </Button>
        </div>
      )}
    </div>
  );
}
