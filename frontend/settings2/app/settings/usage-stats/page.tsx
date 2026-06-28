"use client";

import { useEffect, useState, useCallback } from "react";
import { motion } from "framer-motion";
import {
  Activity,
  BarChart3,
  Clock,
  Eye,
  Globe,
  Loader2,
  MessageSquare,
  MousePointer,
  Settings,
  TrendingUp,
  Users,
} from "lucide-react";

import { ApiError, SettingsApi, UsageApi, UsageStatsResponse, UsageEventResponse } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Header } from "@/components/layout/Header";

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

// Config change event names we want to surface
const CONFIG_CHANGE_EVENTS = [
  "toggle_",
  "lien_mode_change",
  "bill_balance_mode_change",
  "add_no_action_item",
  "remove_no_action_item",
];

function isConfigChangeEvent(eventName: string): boolean {
  return CONFIG_CHANGE_EVENTS.some(
    (pattern) =>
      eventName.startsWith(pattern) || eventName === pattern
  );
}

// Friendly labels for toggle settings
const TOGGLE_LABELS: Record<string, string> = {
  email_processing: "Email Processing",
  global_autorespond: "Global Autorespond",
  sender_verification: "Sender Verification",
  skip_internal_domains: "Skip Internal Domains",
  autorespond_apt_status_req: "Autorespond: Apt Status Req",
  autorespond_medical_records: "Autorespond: Medical Records",
  autorespond_case_updates: "Autorespond: Case Updates",
  autorespond_missing_lien_request: "Autorespond: Missing Lien Request",
};

function getToggleSettingName(eventName: string): string {
  const key = eventName.replace(/^toggle_/, "");
  return TOGGLE_LABELS[key] || key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatConfigChange(event: UsageEventResponse): {
  description: string;
  badge: { text: string; className: string };
} {
  const details = event.details || {};

  if (event.event_name.startsWith("toggle_")) {
    const setting = getToggleSettingName(event.event_name);
    const enabled = details.new_value as boolean;
    return {
      description: setting,
      badge: enabled
        ? { text: "Turned ON", className: "bg-emerald-100 text-emerald-700" }
        : { text: "Turned OFF", className: "bg-rose-100 text-rose-700" },
    };
  }

  if (event.event_name === "lien_mode_change" || event.event_name === "bill_balance_mode_change") {
    const label = event.event_name === "lien_mode_change" ? "Lien Mode" : "Bill Balance Mode";
    const mode = (details.new_mode as string) || "unknown";
    const modeStyles: Record<string, string> = {
      off: "bg-slate-100 text-slate-600",
      sandbox: "bg-amber-100 text-amber-700",
      production: "bg-emerald-100 text-emerald-700",
    };
    return {
      description: label,
      badge: {
        text: mode.charAt(0).toUpperCase() + mode.slice(1),
        className: modeStyles[mode] || "bg-slate-100 text-slate-600",
      },
    };
  }

  if (event.event_name === "add_no_action_item") {
    const item = (details.item as string) || "unknown";
    return {
      description: `Added "${item}" to No-Action List`,
      badge: { text: "Added", className: "bg-blue-100 text-blue-700" },
    };
  }

  if (event.event_name === "remove_no_action_item") {
    const item = (details.item as string) || "unknown";
    return {
      description: `Removed "${item}" from No-Action List`,
      badge: { text: "Removed", className: "bg-orange-100 text-orange-700" },
    };
  }

  // Fallback
  return {
    description: event.event_name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
    badge: { text: "Changed", className: "bg-slate-100 text-slate-600" },
  };
}

export default function UsageStatsPage() {
  const [user, setUser] = useState<string>("Admin");
  const [authLoading, setAuthLoading] = useState(true);
  const [authError, setAuthError] = useState<string | null>(null);

  const [usageStats, setUsageStats] = useState<UsageStatsResponse | null>(null);
  const [usageStatsLoading, setUsageStatsLoading] = useState(false);
  const [usageStatsError, setUsageStatsError] = useState<string | null>(null);
  const [usageStatsDays, setUsageStatsDays] = useState(30);

  const [configEvents, setConfigEvents] = useState<UsageEventResponse[]>([]);
  const [configEventsLoading, setConfigEventsLoading] = useState(false);
  const [configEventsDays, setConfigEventsDays] = useState(30);

  // Auth check
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const auth = await SettingsApi.getAuthStatus();
        if (!auth.authenticated) {
          window.location.href = "/login";
          return;
        }
        setUser(auth.username ?? "Admin");
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          window.location.href = "/login";
          return;
        }
        setAuthError(err instanceof Error ? err.message : "Auth check failed");
      } finally {
        setAuthLoading(false);
      }
    };
    checkAuth();
  }, []);

  const fetchUsageStats = useCallback(async () => {
    setUsageStatsLoading(true);
    setUsageStatsError(null);
    try {
      const stats = await UsageApi.getStats("admin", usageStatsDays);
      setUsageStats(stats);
    } catch (err) {
      setUsageStatsError(err instanceof Error ? err.message : "Failed to load usage stats");
    } finally {
      setUsageStatsLoading(false);
    }
  }, [usageStatsDays]);

  const fetchConfigEvents = useCallback(async () => {
    setConfigEventsLoading(true);
    try {
      const events = await UsageApi.getEvents({
        event_type: "action",
        days: configEventsDays,
        limit: 200,
      });
      setConfigEvents(events.filter((e) => isConfigChangeEvent(e.event_name)));
    } catch (err) {
      console.error("Failed to fetch config events:", err);
    } finally {
      setConfigEventsLoading(false);
    }
  }, [configEventsDays]);

  // Initial fetch
  useEffect(() => {
    if (!authLoading && !authError) {
      fetchUsageStats();
      fetchConfigEvents();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [authLoading, authError]);

  // Re-fetch when days filter changes
  useEffect(() => {
    if (!authLoading && !authError) {
      fetchUsageStats();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [usageStatsDays]);

  useEffect(() => {
    if (!authLoading && !authError) {
      fetchConfigEvents();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [configEventsDays]);

  if (authLoading) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16 bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="rounded-3xl border border-slate-200/80 bg-white/80 px-10 py-12 text-center shadow-2xl"
        >
          <Loader2 className="mx-auto h-8 w-8 animate-spin text-indigo-600" />
          <p className="mt-4 text-base font-medium text-slate-500">Loading...</p>
        </motion.div>
      </section>
    );
  }

  if (authError) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16 bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-6 py-4 text-sm text-rose-600">
          {authError}
        </div>
      </section>
    );
  }

  const dayOptions = [
    { value: 1, label: "24h" },
    { value: 7, label: "7d" },
    { value: 30, label: "30d" },
    { value: 90, label: "90d" },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-slate-100 to-slate-50">
      <Header user={user} currentPage={{ label: "Usage Stats", icon: "📈" }} />

      <main className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-10">
        {/* Usage Statistics Section */}
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
        >
          <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-3 text-xl">
                <Activity className="h-5 w-5 text-indigo-600" />
                Admin Usage Statistics
              </CardTitle>
              <CardDescription>
                Track how the admin user interacts with the /settings page
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Time range selector */}
              <div className="mb-6 flex flex-wrap items-center gap-2">
                {dayOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setUsageStatsDays(opt.value)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      usageStatsDays === opt.value
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
                <div className="ml-2 flex items-center">
                  {usageStatsLoading && <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />}
                </div>
              </div>

              {usageStatsError && (
                <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
                  {usageStatsError}
                </div>
              )}

              {usageStatsLoading && !usageStats ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                </div>
              ) : usageStats ? (
                <div className="space-y-6">
                  {/* Overview Stats */}
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-6">
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <BarChart3 className="h-3.5 w-3.5" />
                        Total Events
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_events.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Eye className="h-3.5 w-3.5" />
                        Page Views
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_page_views.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <MousePointer className="h-3.5 w-3.5" />
                        Actions
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_actions.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Users className="h-3.5 w-3.5" />
                        Sessions
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.total_sessions.toLocaleString()}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Globe className="h-3.5 w-3.5" />
                        Unique Pages
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {usageStats.unique_pages_visited}
                      </div>
                    </div>
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
                        <Clock className="h-3.5 w-3.5" />
                        Avg Session
                      </div>
                      <div className="mt-1 text-2xl font-bold text-slate-800">
                        {Math.round(usageStats.average_session_duration_ms / 1000 / 60)}m
                      </div>
                    </div>
                  </div>

                  {/* Recent Activity */}
                  <div className="grid gap-6 md:grid-cols-2">
                    {/* Time-based activity */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <TrendingUp className="h-4 w-4 text-indigo-500" />
                        Activity Summary
                      </h4>
                      <div className="space-y-2 text-sm">
                        <div className="flex justify-between">
                          <span className="text-slate-600">Today</span>
                          <span className="font-medium text-slate-800">{usageStats.events_today} events</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-600">This Week</span>
                          <span className="font-medium text-slate-800">{usageStats.events_this_week} events</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-600">This Month</span>
                          <span className="font-medium text-slate-800">{usageStats.events_this_month} events</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-slate-600">Total Time</span>
                          <span className="font-medium text-slate-800">
                            {Math.round(usageStats.total_time_spent_ms / 1000 / 60)} minutes
                          </span>
                        </div>
                      </div>
                    </div>

                    {/* Most visited pages */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <Eye className="h-4 w-4 text-indigo-500" />
                        Most Visited Pages
                      </h4>
                      <div className="space-y-2 text-sm">
                        {usageStats.most_visited_pages.slice(0, 5).map((page, i) => (
                          <div key={i} className="flex justify-between">
                            <span className="text-slate-600 truncate max-w-[150px]" title={page.page}>
                              {page.page || "/"}
                            </span>
                            <span className="font-medium text-slate-800">{page.count} views</span>
                          </div>
                        ))}
                        {usageStats.most_visited_pages.length === 0 && (
                          <div className="text-slate-400">No page visits recorded</div>
                        )}
                      </div>
                    </div>

                    {/* Most common actions */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <MousePointer className="h-4 w-4 text-indigo-500" />
                        Most Common Actions
                      </h4>
                      <div className="space-y-2 text-sm">
                        {usageStats.most_common_actions.slice(0, 5).map((action, i) => (
                          <div key={i} className="flex justify-between">
                            <span className="text-slate-600 truncate max-w-[150px]" title={action.action}>
                              {action.action.replace(/_/g, " ")}
                            </span>
                            <span className="font-medium text-slate-800">{action.count}x</span>
                          </div>
                        ))}
                        {usageStats.most_common_actions.length === 0 && (
                          <div className="text-slate-400">No actions recorded</div>
                        )}
                      </div>
                    </div>

                    {/* Hourly activity */}
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <Clock className="h-4 w-4 text-indigo-500" />
                        Activity by Hour
                      </h4>
                      <div className="flex h-16 items-end gap-0.5">
                        {Array.from({ length: 24 }, (_, hour) => {
                          const count = usageStats.hourly_activity[String(hour)] || 0;
                          const maxCount = Math.max(...Object.values(usageStats.hourly_activity), 1);
                          const height = Math.max((count / maxCount) * 100, 2);
                          return (
                            <div
                              key={hour}
                              className="flex-1 bg-indigo-400 rounded-t transition-all hover:bg-indigo-600"
                              style={{ height: `${height}%` }}
                              title={`${hour}:00 - ${count} events`}
                            />
                          );
                        })}
                      </div>
                      <div className="mt-1 flex justify-between text-xs text-slate-400">
                        <span>0h</span>
                        <span>12h</span>
                        <span>24h</span>
                      </div>
                    </div>
                  </div>

                  {/* Recent Sessions */}
                  {usageStats.sessions.length > 0 && (
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <Activity className="h-4 w-4 text-indigo-500" />
                        Recent Sessions
                      </h4>
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                          <thead>
                            <tr className="text-left text-xs text-slate-500">
                              <th className="pb-2 pr-4">Session ID</th>
                              <th className="pb-2 pr-4">Start</th>
                              <th className="pb-2 pr-4">End</th>
                              <th className="pb-2 pr-4">Events</th>
                              <th className="pb-2">Pages</th>
                            </tr>
                          </thead>
                          <tbody>
                            {usageStats.sessions.slice(0, 5).map((session, i) => (
                              <tr key={i} className="border-t border-slate-100">
                                <td className="py-2 pr-4 font-mono text-xs text-slate-600">
                                  {session.session_id?.slice(0, 12)}...
                                </td>
                                <td className="py-2 pr-4 text-slate-600">
                                  {session.start ? new Date(session.start).toLocaleString() : "-"}
                                </td>
                                <td className="py-2 pr-4 text-slate-600">
                                  {session.end ? new Date(session.end).toLocaleString() : "-"}
                                </td>
                                <td className="py-2 pr-4 font-medium text-slate-800">
                                  {session.events_count}
                                </td>
                                <td className="py-2 font-medium text-slate-800">
                                  {session.pages_visited}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}

                  {/* Recent Events */}
                  {usageStats.recent_events.length > 0 && (
                    <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                      <h4 className="mb-3 flex items-center gap-2 font-medium text-slate-700">
                        <MessageSquare className="h-4 w-4 text-indigo-500" />
                        Recent Events
                      </h4>
                      <div className="max-h-64 overflow-y-auto space-y-2">
                        {usageStats.recent_events.slice(0, 20).map((event, i) => (
                          <div
                            key={i}
                            className="flex items-center justify-between rounded-lg bg-white px-3 py-2 text-sm border border-slate-100"
                          >
                            <div className="flex items-center gap-3">
                              <Badge className={
                                event.event_type === "page_view"
                                  ? "bg-blue-100 text-blue-700"
                                  : event.event_type === "action"
                                  ? "bg-green-100 text-green-700"
                                  : event.event_type === "click"
                                  ? "bg-amber-100 text-amber-700"
                                  : event.event_type === "error"
                                  ? "bg-rose-100 text-rose-700"
                                  : "bg-slate-100 text-slate-700"
                              }>
                                {event.event_type}
                              </Badge>
                              <span className="text-slate-700">{event.event_name.replace(/_/g, " ")}</span>
                              {event.page_path && (
                                <span className="text-slate-400 text-xs">{event.page_path}</span>
                              )}
                            </div>
                            <span className="text-xs text-slate-400">
                              {new Date(event.created_at).toLocaleString()}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-12 text-center text-slate-500">
                  No usage data available yet
                </div>
              )}
            </CardContent>
          </Card>
        </motion.section>

        {/* Config Changes Section */}
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.1 }}
        >
          <Card className="rounded-2xl border border-slate-200/70 bg-white/90">
            <CardHeader className="pb-4">
              <CardTitle className="flex items-center gap-3 text-xl">
                <Settings className="h-5 w-5 text-indigo-600" />
                Config Changes
              </CardTitle>
              <CardDescription>
                Log of configuration changes — toggles, mode switches, and no-action list edits
              </CardDescription>
            </CardHeader>
            <CardContent>
              {/* Time range selector */}
              <div className="mb-6 flex flex-wrap items-center gap-2">
                {dayOptions.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setConfigEventsDays(opt.value)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-lg transition-colors ${
                      configEventsDays === opt.value
                        ? "bg-indigo-600 text-white"
                        : "bg-slate-100 text-slate-600 hover:bg-slate-200"
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
                <div className="ml-2 flex items-center">
                  {configEventsLoading && <Loader2 className="h-4 w-4 animate-spin text-indigo-600" />}
                </div>
              </div>

              {configEventsLoading && configEvents.length === 0 ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="h-8 w-8 animate-spin text-indigo-600" />
                </div>
              ) : configEvents.length > 0 ? (
                <div className="space-y-2 max-h-[500px] overflow-y-auto">
                  {configEvents.map((event, i) => {
                    const { description, badge } = formatConfigChange(event);
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-4 rounded-lg border border-slate-100 bg-white px-4 py-3"
                      >
                        <div className="flex-shrink-0 w-40 text-xs text-slate-400">
                          {new Date(event.created_at).toLocaleString()}
                        </div>
                        <div className="flex-shrink-0 text-sm font-medium text-slate-700 w-20">
                          {event.username}
                        </div>
                        <div className="flex items-center gap-2 flex-1 min-w-0">
                          <Badge className={badge.className}>
                            {badge.text}
                          </Badge>
                          <span className="text-sm text-slate-700 truncate">
                            {description}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="py-12 text-center text-slate-500">
                  No config changes recorded in this time range
                </div>
              )}
            </CardContent>
          </Card>
        </motion.section>
      </main>
    </div>
  );
}
