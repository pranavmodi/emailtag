"use client";

import type { ReactNode } from "react";
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  AlertCircle,
  ArrowLeft,
  BarChart3,
  Building2,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Database,
  Download,
  ExternalLink,
  Globe,
  Loader2,
  LogOut,
  Mail,
  MapPin,
  MessageSquare,
  Phone,
  PlayCircle,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Users,
} from "lucide-react";

import { ApiError, PifApi, PifStatsAuthApi } from "@/lib/api";
import type { PifInfoListResponse, PifInfoResponse, VendorStackEntry } from "@/lib/types";
import { ENTITY_TYPE_LABELS } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

type PresenceFilter = "any" | "has" | "missing" | "resolved" | "unresolved";
type StatusFilter = "any" | "completed" | "missing" | "queued_or_running" | "failed";
type EnrichmentRun = {
  taskId: string;
  status: string;
  message: string;
};
type WorkflowStepState = "completed" | "running" | "failed" | "waiting" | "skipped";
type WorkflowStepInfo = {
  label: string;
  detail: string;
  state: WorkflowStepState;
};

const PAGE_SIZE = 25;

const websiteOptions: Array<{ value: PresenceFilter; label: string }> = [
  { value: "any", label: "Any website" },
  { value: "has", label: "Has website" },
  { value: "missing", label: "Missing website" },
  { value: "resolved", label: "Resolved" },
  { value: "unresolved", label: "Unresolved" },
];

const statusOptions: Array<{ value: StatusFilter; label: string }> = [
  { value: "any", label: "Any status" },
  { value: "completed", label: "Completed" },
  { value: "missing", label: "Missing" },
  { value: "queued_or_running", label: "Queued/running" },
  { value: "failed", label: "Failed" },
];

const binaryOptions = [
  { value: "any", label: "Any" },
  { value: "has", label: "Has data" },
  { value: "missing", label: "Missing" },
];

const firstContactOptions = [
  { value: "any", label: "Any first contact" },
  { value: "has", label: "First contacted" },
  { value: "missing", label: "Not contacted" },
];

const entityOptions = Object.entries(ENTITY_TYPE_LABELS);

const formatDate = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString() : "Never";

const displayWebsite = (firm: PifInfoResponse) =>
  firm.canonical_website || firm.website || "";

const normalizeWebsiteHref = (website: string) =>
  website.startsWith("http") ? website : `https://${website}`;

const frontConversationHref = (conversationId: string) =>
  `https://app.frontapp.com/open/${encodeURIComponent(conversationId)}`;

const safeJson = (value: unknown) => {
  if (!value) return "No data";
  return JSON.stringify(value, null, 2);
};

export default function FirmsDashboardPage() {
  const [data, setData] = useState<PifInfoListResponse | null>(null);
  const [expandedFirmId, setExpandedFirmId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("updated_at");
  const [entityType, setEntityType] = useState("");
  const [websitePresence, setWebsitePresence] = useState<PresenceFilter>("any");
  const [researchPresence, setResearchPresence] = useState<StatusFilter>("any");
  const [staffPresence, setStaffPresence] = useState<StatusFilter>("any");
  const [behaviorPresence, setBehaviorPresence] = useState("any");
  const [icpPresence, setIcpPresence] = useState("any");
  const [vendorPresence, setVendorPresence] = useState("any");
  const [firstContactPresence, setFirstContactPresence] = useState("any");
  const [vendorBusy, setVendorBusy] = useState<Record<string, boolean>>({});
  const [exportBusy, setExportBusy] = useState(false);
  const [activeOnly, setActiveOnly] = useState(true);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [enrichmentRuns, setEnrichmentRuns] = useState<Record<string, EnrichmentRun>>({});

  const loadFirms = useCallback(async () => {
    setIsLoading(true);
    try {
      const payload = await PifApi.list({
        search: search || undefined,
        page,
        pageSize: PAGE_SIZE,
        sortBy,
        entityType: entityType || undefined,
        websitePresence,
        researchPresence,
        staffPresence,
        behaviorPresence,
        icpPresence,
        vendorPresence,
        firstContactPresence,
        activeOnly,
      });
      setData(payload);
      setExpandedFirmId((current) => {
        if (!current) return null;
        return payload.items.some((firm) => firm.id === current) ? current : null;
      });
      setError(null);
    } catch (err) {
      const message =
        err instanceof ApiError ? err.message : "Unable to load firms";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [
    activeOnly,
    behaviorPresence,
    entityType,
    firstContactPresence,
    icpPresence,
    page,
    researchPresence,
    search,
    sortBy,
    staffPresence,
    vendorPresence,
    websitePresence,
  ]);

  useEffect(() => {
    loadFirms();
  }, [loadFirms]);

  const startFullEnrichment = async (firm: PifInfoResponse) => {
    setEnrichmentRuns((current) => ({
      ...current,
      [firm.id]: {
        taskId: current[firm.id]?.taskId ?? "",
        status: "queued",
        message: "Starting full enrichment...",
      },
    }));
    try {
      const response = await PifApi.enrichAll(firm.id);
      setEnrichmentRuns((current) => ({
        ...current,
        [firm.id]: {
          taskId: response.task_id,
          status: response.status,
          message: response.message,
        },
      }));
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start full enrichment";
      setEnrichmentRuns((current) => ({
        ...current,
        [firm.id]: {
          taskId: current[firm.id]?.taskId ?? "",
          status: "failed",
          message,
        },
      }));
    }
  };

  const handleExportAll = async (format: "json" | "csv") => {
    setExportBusy(true);
    try {
      await PifApi.exportAll(format);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Export failed");
    } finally {
      setExportBusy(false);
    }
  };

  const startVendorDetection = async (firm: PifInfoResponse) => {
    setVendorBusy((current) => ({ ...current, [firm.id]: true }));
    const before = firm.updated_at;
    try {
      await PifApi.detectVendors(firm.id);
      // Vendor detection is async (all 3 tiers). Poll until the row's
      // updated_at bumps — reliable even when no vendors are found (stays null).
      for (let i = 0; i < 30; i += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 4000));
        const fresh = await PifApi.get(firm.id);
        if (fresh.updated_at !== before) break;
      }
      await loadFirms();
    } catch {
      // Surface nothing intrusive; button re-enables in finally.
    } finally {
      setVendorBusy((current) => ({ ...current, [firm.id]: false }));
    }
  };

  useEffect(() => {
    const activeRuns = Object.entries(enrichmentRuns).filter(([, run]) =>
      isWorkflowRunning(run.status) && run.taskId
    );
    if (activeRuns.length === 0) return;

    const interval = window.setInterval(async () => {
      const updates = await Promise.all(
        activeRuns.map(async ([firmId, run]) => {
          try {
            const statusResponse = await PifApi.getEnrichmentStatus(run.taskId);
            let firm: PifInfoResponse | null = null;
            try {
              firm = await PifApi.get(firmId);
            } catch {
              firm = null;
            }
            return [
              firmId,
              {
                taskId: run.taskId,
                status: statusResponse.status,
                message: statusResponse.message,
              },
              firm,
            ] as const;
          } catch (err) {
            return [
              firmId,
              {
                taskId: run.taskId,
                status: "failed",
                message: err instanceof Error ? err.message : "Failed to poll enrichment status",
              },
              null,
            ] as const;
          }
        })
      );

      setEnrichmentRuns((current) => {
        const next = { ...current };
        for (const [firmId, run] of updates) {
          next[firmId] = run;
        }
        return next;
      });

      const refreshedFirms = updates
        .map(([, , firm]) => firm)
        .filter((firm): firm is PifInfoResponse => Boolean(firm));

      if (refreshedFirms.length > 0) {
        setData((current) => {
          if (!current) return current;
          const refreshedById = new Map(refreshedFirms.map((firm) => [firm.id, firm]));
          return {
            ...current,
            items: current.items.map((firm) => refreshedById.get(firm.id) ?? firm),
          };
        });
      }
    }, 5000);

    return () => window.clearInterval(interval);
  }, [enrichmentRuns]);

  const resetToFirstPage = <T,>(setter: (value: T) => void, value: T) => {
    setter(value);
    setPage(1);
    setExpandedFirmId(null);
  };

  const clearFilters = () => {
    setSearch("");
    setEntityType("");
    setWebsitePresence("any");
    setResearchPresence("any");
    setStaffPresence("any");
    setBehaviorPresence("any");
    setIcpPresence("any");
    setVendorPresence("any");
    setFirstContactPresence("any");
    setActiveOnly(true);
    setSortBy("updated_at");
    setPage(1);
    setExpandedFirmId(null);
  };

  const visibleRange = useMemo(() => {
    if (!data || data.total === 0) return "0";
    const start = (data.page - 1) * data.page_size + 1;
    const end = Math.min(data.page * data.page_size, data.total);
    return `${start}-${end}`;
  }, [data]);

  const pageSummary = useMemo(() => {
    const items = data?.items ?? [];
    return {
      missingWebsite: items.filter((firm) => !displayWebsite(firm)).length,
      firstContacted: items.filter((firm) => firm.first_contacted_precise_at).length,
      researched: items.filter((firm) => firm.research_status === "completed").length,
      scored: items.filter((firm) => firm.icp_score != null).length,
    };
  }, [data]);

  const handleLogout = async () => {
    try {
      await PifStatsAuthApi.logout();
    } finally {
      window.location.href = "/pifstats/login";
    }
  };

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-5">
          <div>
            <Link
              href="/pifstats"
              className="mb-2 inline-flex items-center gap-2 text-sm text-slate-500 hover:text-slate-900"
            >
              <ArrowLeft className="h-4 w-4" />
              PIFStats
            </Link>
            <h1 className="text-2xl font-semibold tracking-tight">Firms</h1>
            <p className="text-sm text-slate-500">
              Filter firm records and expand a row to inspect website resolution, research, people, and scoring.
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button onClick={loadFirms} disabled={isLoading} className="gap-2">
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Refresh
            </Button>
            <div className="flex items-center overflow-hidden rounded-md border border-slate-300">
              <span className="px-2 text-xs font-medium text-slate-500">Export all</span>
              <Button
                type="button"
                variant="ghost"
                onClick={() => handleExportAll("json")}
                disabled={exportBusy}
                className="h-9 gap-1 rounded-none border-l border-slate-300 px-3 text-xs"
              >
                {exportBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}
                JSON
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => handleExportAll("csv")}
                disabled={exportBusy}
                className="h-9 gap-1 rounded-none border-l border-slate-300 px-3 text-xs"
              >
                <Download className="h-3.5 w-3.5" />
                CSV
              </Button>
            </div>
            <Button type="button" variant="ghost" onClick={handleLogout} className="gap-2 border border-slate-300">
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-6">
        <div className="grid gap-3 md:grid-cols-4">
          <MetricTile icon={<Database className="h-4 w-4" />} label="Matching firms" value={data?.total ?? 0} />
          <MetricTile icon={<SlidersHorizontal className="h-4 w-4" />} label="Showing" value={visibleRange} />
          <MetricTile icon={<Globe className="h-4 w-4" />} label="Missing websites on page" value={pageSummary.missingWebsite} />
          <MetricTile icon={<Mail className="h-4 w-4" />} label="First contacted on page" value={pageSummary.firstContacted} />
        </div>

        <div className="mt-5 rounded-lg border border-slate-200 bg-white p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-700">
            <SlidersHorizontal className="h-4 w-4" />
            Filters
          </div>
          <div className="grid gap-3 lg:grid-cols-[minmax(260px,1.4fr)_repeat(4,minmax(150px,1fr))]">
            <label className="relative block">
              <span className="sr-only">Search firms</span>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                value={search}
                onChange={(event) => resetToFirstPage(setSearch, event.target.value)}
                placeholder="Search firm, website, email"
                className="h-10 w-full rounded-md border border-slate-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-slate-900"
              />
            </label>
            <FilterSelect
              value={websitePresence}
              onChange={(value) => resetToFirstPage(setWebsitePresence, value as PresenceFilter)}
              options={websiteOptions}
            />
            <FilterSelect
              value={researchPresence}
              onChange={(value) => resetToFirstPage(setResearchPresence, value as StatusFilter)}
              options={statusOptions}
              prefix="Research"
            />
            <FilterSelect
              value={staffPresence}
              onChange={(value) => resetToFirstPage(setStaffPresence, value as StatusFilter)}
              options={statusOptions}
              prefix="Staff"
            />
            <label className="flex h-10 items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-sm">
              <input
                type="checkbox"
                checked={activeOnly}
                onChange={(event) => resetToFirstPage(setActiveOnly, event.target.checked)}
                className="h-4 w-4"
              />
              Active only
            </label>
            <FilterSelect
              value={behaviorPresence}
              onChange={(value) => resetToFirstPage(setBehaviorPresence, value)}
              options={binaryOptions}
              prefix="Behavior"
            />
            <FilterSelect
              value={icpPresence}
              onChange={(value) => resetToFirstPage(setIcpPresence, value)}
              options={binaryOptions}
              prefix="ICP"
            />
            <FilterSelect
              value={vendorPresence}
              onChange={(value) => resetToFirstPage(setVendorPresence, value)}
              options={binaryOptions}
              prefix="Vendors"
            />
            <FilterSelect
              value={firstContactPresence}
              onChange={(value) => resetToFirstPage(setFirstContactPresence, value)}
              options={firstContactOptions}
            />
            <select
              value={entityType}
              onChange={(event) => resetToFirstPage(setEntityType, event.target.value)}
              className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
            >
              <option value="">All entity types</option>
              {entityOptions.map(([value, label]) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <select
              value={sortBy}
              onChange={(event) => resetToFirstPage(setSortBy, event.target.value)}
              className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
            >
              <option value="updated_at">Recently updated</option>
              <option value="first_contacted_precise_at">First contacted</option>
              <option value="firm_name">Firm name</option>
              <option value="conversation_count">Conversation count</option>
            </select>
            <Button
              type="button"
              variant="ghost"
              onClick={clearFilters}
              className="h-10 border border-slate-300"
            >
              Clear
            </Button>
          </div>
        </div>

        {error && (
          <div className="mt-4 rounded-md border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {error}
          </div>
        )}

        <div className="mt-5 overflow-hidden rounded-lg border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-4 py-3">
            <div className="text-sm font-medium text-slate-900">Firm records</div>
            <div className="text-xs text-slate-500">
              Select a row to expand details directly below it.
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-sm">
              <thead className="bg-slate-100 text-left text-xs font-semibold uppercase text-slate-500">
                <tr>
                  <th className="w-10 px-4 py-3" />
                  <th className="min-w-[260px] px-4 py-3">Firm</th>
                  <th className="min-w-[220px] px-4 py-3">Website</th>
                  <th className="px-4 py-3">Research</th>
                  <th className="px-4 py-3">Staff</th>
                  <th className="px-4 py-3">First contacted</th>
                  <th className="px-4 py-3">ICP</th>
                  <th className="px-4 py-3">Signals</th>
                  <th className="px-4 py-3">Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {isLoading && (
                  <tr>
                    <td className="px-4 py-10 text-center text-slate-500" colSpan={9}>
                      <Loader2 className="mx-auto mb-2 h-5 w-5 animate-spin" />
                      Loading firms
                    </td>
                  </tr>
                )}
                {!isLoading && data?.items.length === 0 && (
                  <tr>
                    <td className="px-4 py-10 text-center text-slate-500" colSpan={9}>
                      No firms match these filters.
                    </td>
                  </tr>
                )}
                {!isLoading && data?.items.map((firm) => {
                  const expanded = expandedFirmId === firm.id;
                  return (
                    <Fragment key={firm.id}>
                      <FirmRow
                        firm={firm}
                        expanded={expanded}
                        onToggle={() => setExpandedFirmId(expanded ? null : firm.id)}
                      />
                      {expanded && (
                        <tr className="bg-slate-50">
                          <td colSpan={9} className="px-4 pb-5 pt-0">
                            <FirmDetail
                              firm={firm}
                              enrichmentRun={enrichmentRuns[firm.id]}
                              onRunFullEnrichment={() => startFullEnrichment(firm)}
                              onDetectVendors={() => startVendorDetection(firm)}
                              vendorBusy={Boolean(vendorBusy[firm.id])}
                            />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 px-4 py-3 text-sm">
            <Button
              variant="ghost"
              className="border border-slate-300"
              disabled={!data || page <= 1 || isLoading}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </Button>
            <span className="text-slate-500">
              Page {data?.page ?? page} of {data?.total_pages ?? 1}
            </span>
            <Button
              variant="ghost"
              className="border border-slate-300"
              disabled={!data || page >= data.total_pages || isLoading}
              onClick={() => setPage((current) => current + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}

function FirmRow({
  firm,
  expanded,
  onToggle,
}: {
  firm: PifInfoResponse;
  expanded: boolean;
  onToggle: () => void;
}) {
  const website = displayWebsite(firm);
  const hasBehavior = Boolean(firm.behavioral_data);
  const conversationCount = firm.conversation_ids?.length ?? 0;

  return (
    <tr
      onClick={onToggle}
      className={`cursor-pointer transition hover:bg-slate-50 ${
        expanded ? "bg-slate-50" : "bg-white"
      }`}
    >
      <td className="px-4 py-4 align-top">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onToggle();
          }}
          className="rounded-md p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-900"
          aria-label={expanded ? "Collapse firm details" : "Expand firm details"}
        >
          {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        </button>
      </td>
      <td className="px-4 py-4 align-top">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-900 text-white">
            <Building2 className="h-4 w-4" />
          </span>
          <div className="min-w-0">
            <div className="font-medium text-slate-950">{firm.firm_name}</div>
            <div className="mt-1 text-xs text-slate-500">
              {ENTITY_TYPE_LABELS[firm.entity_type] ?? firm.entity_type}
            </div>
          </div>
        </div>
      </td>
      <td className="px-4 py-4 align-top">
        {website ? (
          <a
            href={normalizeWebsiteHref(website)}
            target="_blank"
            rel="noreferrer"
            onClick={(event) => event.stopPropagation()}
            className="inline-flex max-w-[260px] items-center gap-1 truncate text-slate-700 hover:text-slate-950"
          >
            <span className="truncate">{website}</span>
            <ExternalLink className="h-3.5 w-3.5 shrink-0" />
          </a>
        ) : (
          <span className="text-slate-400">Missing</span>
        )}
        <div className="mt-1">
          <WebsiteStatusBadge status={firm.website_status} />
        </div>
      </td>
      <td className="px-4 py-4 align-top">
        <StatusBadge status={firm.research_status} />
      </td>
      <td className="px-4 py-4 align-top">
        <StatusBadge status={firm.staff_research_status} />
      </td>
      <td className="px-4 py-4 align-top text-slate-500">
        {firm.first_contacted_precise_at ? (
          <div>
            <div className="text-slate-700">{formatDate(firm.first_contacted_precise_at)}</div>
            <div className="mt-1 text-xs text-slate-400">from linked email</div>
          </div>
        ) : (
          <span className="text-slate-400">Not contacted</span>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        {firm.icp_score == null ? (
          <span className="text-slate-400">Missing</span>
        ) : (
          <Badge className="border-indigo-200 bg-indigo-50 text-indigo-700">
            {firm.icp_tier ?? "-"} / {firm.icp_score}
          </Badge>
        )}
      </td>
      <td className="px-4 py-4 align-top">
        <div className="flex flex-wrap gap-1.5">
          <SignalPill icon={<Mail className="h-3 w-3" />} value={firm.emails?.length ?? 0} label="emails" />
          <SignalPill icon={<Users className="h-3 w-3" />} value={firm.contacts?.length ?? 0} label="contacts" />
          <SignalPill icon={<Activity className="h-3 w-3" />} value={conversationCount} label="conversations" />
          {hasBehavior && <SignalPill icon={<BarChart3 className="h-3 w-3" />} value="yes" label="behavior" />}
        </div>
      </td>
      <td className="px-4 py-4 align-top text-slate-500">
        {formatDate(firm.updated_at)}
      </td>
    </tr>
  );
}

function FirmDetail({
  firm,
  enrichmentRun,
  onRunFullEnrichment,
  onDetectVendors,
  vendorBusy,
}: {
  firm: PifInfoResponse;
  enrichmentRun?: EnrichmentRun;
  onRunFullEnrichment: () => void;
  onDetectVendors: () => void;
  vendorBusy: boolean;
}) {
  const website = displayWebsite(firm);
  const contactCount = (firm.contacts?.length ?? 0) + (firm.leadership?.length ?? 0) + (firm.staff?.length ?? 0);
  const workflowRunning = Boolean(enrichmentRun && isWorkflowRunning(enrichmentRun.status));
  const enrichmentSteps = buildEnrichmentSteps(firm, enrichmentRun);

  return (
    <div className="rounded-b-lg border border-t-0 border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-200 pb-4">
        <div>
          <div className="text-lg font-semibold text-slate-950">{firm.firm_name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-slate-500">
            <span>{ENTITY_TYPE_LABELS[firm.entity_type] ?? firm.entity_type}</span>
            <span className="text-slate-300">|</span>
            <span>{firm.conversation_ids?.length ?? 0} conversations</span>
            <span className="text-slate-300">|</span>
            <span>{contactCount} people records</span>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            onClick={(event) => {
              event.stopPropagation();
              onRunFullEnrichment();
            }}
            disabled={workflowRunning}
            className="gap-2"
          >
            {workflowRunning ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <PlayCircle className="h-4 w-4" />
            )}
            {workflowRunning ? "Enriching..." : "Run full enrichment"}
          </Button>
          <div className="flex items-center overflow-hidden rounded-md border border-slate-300">
            <span className="px-2 text-xs font-medium text-slate-500">Export</span>
            <Button
              type="button"
              variant="ghost"
              onClick={(event) => {
                event.stopPropagation();
                void PifApi.exportFirm(firm.id, "json");
              }}
              className="h-9 gap-1 rounded-none border-l border-slate-300 px-3 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              JSON
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={(event) => {
                event.stopPropagation();
                void PifApi.exportFirm(firm.id, "csv");
              }}
              className="h-9 gap-1 rounded-none border-l border-slate-300 px-3 text-xs"
            >
              <Download className="h-3.5 w-3.5" />
              CSV
            </Button>
          </div>
          {website && (
            <a
              href={normalizeWebsiteHref(website)}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:border-slate-900 hover:text-slate-950"
            >
              Open website
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
      </div>

      <section className="mt-5 rounded-lg border border-slate-200 bg-slate-50/70 p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">Full enrichment workflow</h2>
            <p className="text-xs text-slate-500">
              Runs website resolution, research, staff, behavior, signatures, and ICP scoring in order.
            </p>
          </div>
          {enrichmentRun && (
            <Badge className={workflowStatusClass(enrichmentRun.status)}>
              {enrichmentRun.status}
            </Badge>
          )}
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          {enrichmentSteps.map((step) => (
            <WorkflowStep key={step.label} {...step} />
          ))}
        </div>
        {enrichmentRun?.message && (
          <div className="mt-3 text-xs text-slate-500">{enrichmentRun.message}</div>
        )}
      </section>

      <section className="mt-5 rounded-lg border border-slate-200 bg-white p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <MessageSquare className="h-4 w-4" />
            Front Conversations
          </h2>
          <Badge className="border-slate-200 bg-slate-50 text-slate-600">
            {firm.conversation_ids?.length ?? 0}
          </Badge>
        </div>
        {firm.conversation_ids?.length ? (
          <div className="flex flex-wrap gap-2">
            {firm.conversation_ids.map((conversationId) => (
              <a
                key={conversationId}
                href={frontConversationHref(conversationId)}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1.5 font-mono text-xs text-slate-700 hover:border-slate-400 hover:bg-white hover:text-slate-950"
              >
                <span className="truncate">{conversationId}</span>
                <ExternalLink className="h-3.5 w-3.5 shrink-0" />
              </a>
            ))}
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
            No linked Front conversations.
          </div>
        )}
      </section>

      <div className="mt-5 grid gap-4 lg:grid-cols-3">
        <DetailSection icon={<Globe className="h-4 w-4" />} title="Website Resolution">
          <dl className="grid gap-3 sm:grid-cols-2">
            <DetailItem label="Canonical" value={firm.canonical_website || "Missing"} />
            <DetailItem label="Raw website" value={firm.website || "Missing"} />
            <DetailItem label="Status" value={firm.website_status || "Missing"} />
            <DetailItem label="Source" value={firm.website_source || "Unknown"} />
            <DetailItem label="Confidence" value={firm.website_confidence?.toString() ?? "Unknown"} />
            <DetailItem label="First contacted" value={formatDate(firm.first_contacted_precise_at)} />
            <DetailItem label="Updated" value={formatDate(firm.updated_at)} />
          </dl>
        </DetailSection>

        <DetailSection icon={<Mail className="h-4 w-4" />} title="Contact Data">
          <div className="space-y-3">
            <IconList icon={<Mail className="h-4 w-4" />} label="Emails" values={firm.emails} />
            <IconList icon={<Phone className="h-4 w-4" />} label="Phones" values={firm.phones} />
            <IconList icon={<MapPin className="h-4 w-4" />} label="Addresses" values={firm.addresses} />
          </div>
        </DetailSection>

        <DetailSection icon={<BarChart3 className="h-4 w-4" />} title="Research Status">
          <dl className="grid gap-3 sm:grid-cols-2">
            <DetailItem label="Firm research" value={firm.research_status || "Missing"} />
            <DetailItem label="Staff research" value={firm.staff_research_status || "Missing"} />
            <DetailItem label="Last researched" value={formatDate(firm.last_researched_at)} />
            <DetailItem
              label="ICP score"
              value={firm.icp_score == null ? "Missing" : `${firm.icp_tier ?? "-"} / ${firm.icp_score}`}
            />
          </dl>
        </DetailSection>
      </div>

      <div className="mt-4">
        <VendorStackSection
          vendors={firm.vendor_stack ?? []}
          onDetect={onDetectVendors}
          busy={vendorBusy}
        />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <PeopleSection title="Leadership" people={firm.leadership ?? []} />
        <PeopleSection title="Staff" people={firm.staff ?? []} />
        <PeopleSection title="Extracted Contacts" people={firm.contacts ?? []} />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <JsonSection title="Research Data" value={firm.research_data} />
        <JsonSection title="Behavioral Data" value={firm.behavioral_data} />
      </div>
    </div>
  );
}

function isWorkflowRunning(status: string) {
  return status === "queued" || status === "in_progress" || status === "pending";
}

function buildEnrichmentSteps(
  firm: PifInfoResponse,
  enrichmentRun?: EnrichmentRun
): WorkflowStepInfo[] {
  const workflowRunning = Boolean(enrichmentRun && isWorkflowRunning(enrichmentRun.status));
  const workflowFailed = enrichmentRun?.status === "failed";
  const leadershipHistory = firm.research_data?.leadership_email_history;
  const contactProfiles = firm.behavioral_data?.contact_profiles;

  return [
    {
      label: "Website",
      detail: firm.canonical_website
        ? firm.canonical_website
        : firm.website_status === "pending"
          ? "Needs review"
          : "Resolve canonical website",
      state: firm.website_status === "resolved" && Boolean(firm.canonical_website)
        ? "completed"
        : workflowFailed
          ? "failed"
          : workflowRunning
            ? "running"
            : "waiting",
    },
    {
      label: "Firm research",
      detail: firm.research_status || "Not researched",
      state: statusToStepState(firm.research_status, workflowRunning),
    },
    {
      label: "Leadership email history",
      detail: Array.isArray(leadershipHistory)
        ? `${leadershipHistory.length} leaders analyzed`
        : firm.leadership?.length
          ? "Waiting for email history"
          : "Needs leadership first",
      state: Array.isArray(leadershipHistory)
        ? "completed"
        : firm.research_status === "completed" && !firm.leadership?.length
          ? "skipped"
          : workflowRunning
            ? "running"
            : "waiting",
    },
    {
      label: "Staff research",
      detail: firm.staff_research_status || "Not researched",
      state: statusToStepState(firm.staff_research_status, workflowRunning),
    },
    {
      label: "Behavior",
      detail: firm.behavioral_data
        ? `${firm.behavioral_data.total_email_count ?? 0} emails analyzed`
        : "Analyze email behavior",
      state: firm.behavioral_data ? "completed" : workflowRunning ? "running" : "waiting",
    },
    {
      label: "Signatures",
      detail: contactProfiles
        ? `${Object.keys(contactProfiles).length} contact profiles`
        : "Extract signature profiles",
      state: contactProfiles
        ? "completed"
        : firm.behavioral_data && !workflowRunning
          ? "waiting"
          : workflowRunning
            ? "running"
            : "waiting",
    },
    {
      label: "ICP score",
      detail: firm.icp_score == null ? "Not scored" : `${firm.icp_tier ?? "-"} / ${firm.icp_score}`,
      state: firm.icp_score == null ? (workflowRunning ? "running" : "waiting") : "completed",
    },
  ];
}

function statusToStepState(
  status: string | null,
  workflowRunning: boolean
): WorkflowStepState {
  if (status === "completed") return "completed";
  if (status === "failed") return "failed";
  if (status === "queued" || status === "in_progress") return "running";
  return workflowRunning ? "running" : "waiting";
}

function WorkflowStep({ label, detail, state }: WorkflowStepInfo) {
  const Icon =
    state === "completed" ? CheckCircle2 : state === "failed" ? AlertCircle : state === "running" ? Loader2 : ChevronRight;
  const iconClass =
    state === "completed"
      ? "text-emerald-600"
      : state === "failed"
        ? "text-rose-600"
        : state === "running"
          ? "animate-spin text-amber-600"
          : "text-slate-400";

  return (
    <div className="rounded-md border border-slate-200 bg-white px-3 py-3">
      <div className="flex items-center gap-2">
        <Icon className={`h-4 w-4 ${iconClass}`} />
        <span className="text-sm font-medium text-slate-900">{label}</span>
      </div>
      <div className="mt-1 truncate text-xs text-slate-500" title={detail}>
        {detail}
      </div>
    </div>
  );
}

function workflowStatusClass(status: string) {
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "failed") return "border-rose-200 bg-rose-50 text-rose-700";
  return "border-amber-200 bg-amber-50 text-amber-700";
}

function FilterSelect({
  value,
  onChange,
  options,
  prefix,
}: {
  value: string;
  onChange: (value: string) => void;
  options: Array<{ value: string; label: string }>;
  prefix?: string;
}) {
  return (
    <select
      value={value}
      onChange={(event) => onChange(event.target.value)}
      className="h-10 rounded-md border border-slate-300 bg-white px-3 text-sm"
    >
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {prefix ? `${prefix}: ${option.label}` : option.label}
        </option>
      ))}
    </select>
  );
}

function MetricTile({ icon, label, value }: { icon: ReactNode; label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <div className="flex items-center gap-2 text-xs font-medium uppercase text-slate-500">
        {icon}
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold text-slate-950">{value}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-slate-400">Missing</span>;
  const className =
    status === "completed"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : status === "failed"
        ? "border-rose-200 bg-rose-50 text-rose-700"
        : status === "queued" || status === "in_progress"
          ? "border-amber-200 bg-amber-50 text-amber-700"
          : "border-slate-200 bg-slate-50 text-slate-600";
  return <Badge className={className}>{status}</Badge>;
}

function WebsiteStatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="text-xs text-slate-400">unknown</span>;
  const className =
    status === "resolved"
      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
      : "border-amber-200 bg-amber-50 text-amber-700";
  return <Badge className={className}>{status}</Badge>;
}

function SignalPill({
  icon,
  value,
  label,
}: {
  icon: ReactNode;
  value: string | number;
  label: string;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-1 text-xs text-slate-600">
      {icon}
      <span className="font-medium text-slate-800">{value}</span>
      {label}
    </span>
  );
}

function DetailSection({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        {icon}
        {title}
      </h2>
      {children}
    </section>
  );
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase text-slate-400">{label}</dt>
      <dd className="mt-1 break-words text-sm text-slate-700">{value}</dd>
    </div>
  );
}

function IconList({ icon, label, values }: { icon: ReactNode; label: string; values: string[] }) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase text-slate-400">
        {icon}
        {label}
      </div>
      <div className="break-words text-sm text-slate-700">
        {values?.length ? values.join(", ") : "None"}
      </div>
    </div>
  );
}

function PeopleSection({ title, people }: { title: string; people: Array<Record<string, any>> }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Users className="h-4 w-4" />
        {title}
        <span className="ml-auto rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
          {people.length}
        </span>
      </h2>
      {people.length ? (
        <ul className="space-y-2">
          {people.slice(0, 8).map((person, index) => (
            <li key={`${title}-${index}`} className="rounded-md bg-slate-50 px-3 py-2">
              <div className="font-medium text-slate-900">{person.name || "Unknown"}</div>
              {person.title && <div className="text-xs text-slate-500">{person.title}</div>}
              {person.email && <div className="mt-1 break-words text-xs text-slate-500">{person.email}</div>}
              {person.phone && <div className="mt-1 text-xs text-slate-500">{person.phone}</div>}
            </li>
          ))}
          {people.length > 8 && (
            <li className="text-xs text-slate-500">+{people.length - 8} more</li>
          )}
        </ul>
      ) : (
        <div className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
          No records.
        </div>
      )}
    </section>
  );
}

function VendorStackSection({
  vendors,
  onDetect,
  busy,
}: {
  vendors: VendorStackEntry[];
  onDetect: () => void;
  busy: boolean;
}) {
  return (
    <section className="rounded-lg border border-slate-200 bg-slate-50/60 p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Database className="h-4 w-4" />
        Vendor Stack
        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
          {vendors.length}
        </span>
        <Button
          type="button"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation();
            onDetect();
          }}
          disabled={busy}
          className="ml-auto h-8 gap-2 border border-slate-300 px-3 text-xs"
        >
          {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          {busy ? "Detecting..." : "Detect vendors"}
        </Button>
      </h2>
      {vendors.length ? (
        <div className="flex flex-wrap gap-2">
          {vendors.map((v, index) => (
            <div
              key={`vendor-${index}`}
              className="flex items-center gap-2 rounded-md border border-slate-200 bg-white px-3 py-1.5"
              title={v.evidence || undefined}
            >
              <span className="text-sm font-medium capitalize text-slate-900">{v.vendor}</span>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
                {v.source}
              </span>
              {v.confidence && (
                <span className="text-xs text-slate-400">{v.confidence}</span>
              )}
              {v.known === false && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-700">
                  new
                </span>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-slate-200 px-3 py-4 text-sm text-slate-500">
          No vendors detected.
        </div>
      )}
    </section>
  );
}

function JsonSection({ title, value }: { title: string; value: unknown }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Activity className="h-4 w-4" />
        {title}
      </h2>
      <pre className="max-h-80 overflow-auto rounded-md bg-slate-950 p-3 text-xs leading-5 text-slate-100">
        {safeJson(value)}
      </pre>
    </section>
  );
}
