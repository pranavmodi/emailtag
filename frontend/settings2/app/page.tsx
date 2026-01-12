"use client";

import type { ComponentType, SVGProps } from "react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import {
  BadgeCheck,
  CalendarDays,
  ClipboardList,
  FileWarning,
  FolderOpen,
  LogOut,
  MailSearch,
  MessageSquare,
  PiggyBank,
  ShieldCheck,
} from "lucide-react";

import { ApiError, SettingsApi } from "@/lib/api";
import { cn } from "@/lib/utils";
import type {
  AutorespondSettingsResponse,
  EmailProcessingStatus,
} from "@/lib/types";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SegmentedControl, type SegmentOption } from "@/components/ui/segmented-control";

// Lien mode options for 3-way toggle
type LienMode = "off" | "sandbox" | "production";
const LIEN_MODE_OPTIONS: SegmentOption<LienMode>[] = [
  { value: "off", label: "Off", description: "Lien autorespond disabled" },
  { value: "sandbox", label: "Sandbox", description: "Save to local directory for testing" },
  { value: "production", label: "Production", description: "Upload to RadFlow patient files" },
];

// Bill Balance mode options for 3-way toggle
type BillBalanceMode = "off" | "sandbox" | "production";
const BILL_BALANCE_MODE_OPTIONS: SegmentOption<BillBalanceMode>[] = [
  { value: "off", label: "Off", description: "Bill balance autorespond disabled" },
  { value: "sandbox", label: "Sandbox", description: "Save to local directory for testing" },
  { value: "production", label: "Production", description: "Send via Front API" },
];

const easing = { duration: 0.45, ease: [0.16, 1, 0.3, 1] };

const AUTORESPOND_LAYOUT: Array<{
  key: keyof Omit<AutorespondSettingsResponse, "global_autorespond_enabled">;
  settingKey: string;
  accent: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}> = [
  {
    key: "apt_status_req",
    settingKey: "autorespond_apt_status_req",
    accent: "from-indigo-500 to-purple-500",
    icon: ClipboardList,
  },
  {
    key: "medical_records",
    settingKey: "autorespond_medical_records",
    accent: "from-emerald-500 to-teal-500",
    icon: FolderOpen,
  },
  // Note: bill_balance_request removed from here - now uses custom 3-way toggle (off/sandbox/production)
  {
    key: "case_updates",
    settingKey: "autorespond_case_updates",
    accent: "from-pink-500 to-rose-500",
    icon: MessageSquare,
  },
  {
    key: "missing_lien_request",
    settingKey: "autorespond_missing_lien_request",
    accent: "from-fuchsia-500 to-rose-500",
    icon: FileWarning,
  },
  // Note: liens removed from here - now uses custom 3-way toggle (off/sandbox/production)
];

const AUTORESPOND_LOOKUP = AUTORESPOND_LAYOUT.reduce(
  (acc, item) => {
    acc[item.settingKey] = item.key;
    return acc;
  },
  {} as Record<string, keyof Omit<AutorespondSettingsResponse, "global_autorespond_enabled">>
);

const STATUS_BADGE = {
  enabled: "bg-emerald-50 text-emerald-600 border-emerald-200",
  disabled: "bg-rose-50 text-rose-600 border-rose-200",
} as const;

const MENU_ITEMS = [
  {
    href: "/",
    label: "System Settings",
    description: "Configure email processing behavior",
    icon: "⚙️",
  },
  {
    href: "/template-config",
    label: "Autorespond Templates",
    description: "Edit message templates",
    icon: "📝",
  },
  {
    href: "/tag-statistics",
    label: "Tag Statistics",
    description: "Analyze tag retention and changes",
    icon: "📊",
  },
  {
    href: "/sandbox",
    label: "Autorespond Sandbox",
    description: "Test autorespond outputs locally",
    icon: "🧪",
  },
];

const formatDate = (value: string | null) =>
  value ? new Date(value).toLocaleString() : "Never";

const ErrorBanner = ({ message }: { message: string }) => (
  <div className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-600">
    {message}
  </div>
);

export default function Settings2Page() {
  const [user, setUser] = useState<string>("Admin");
  const [status, setStatus] = useState<EmailProcessingStatus | null>(null);
  const [autorespond, setAutorespond] =
    useState<AutorespondSettingsResponse | null>(null);
  const [senderVerificationEnabled, setSenderVerificationEnabled] = useState<boolean>(true);
  const [skipInternalDomains, setSkipInternalDomains] = useState<boolean>(false);
  const [lienMode, setLienMode] = useState<LienMode>("off");
  const [billBalanceMode, setBillBalanceMode] = useState<BillBalanceMode>("off");
  const [isLoading, setIsLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [autorespondError, setAutorespondError] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [internalDomainsError, setInternalDomainsError] = useState<string | null>(null);
  const [lienModeError, setLienModeError] = useState<string | null>(null);
  const [billBalanceModeError, setBillBalanceModeError] = useState<string | null>(null);
  const [busy, setBusy] = useState<Record<string, boolean>>({});

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

        const [processingPayload, autorespondPayload, workspacePayload, internalDomainsPayload, lienTestModePayload, billBalanceTestModePayload] = await Promise.all([
          SettingsApi.getProcessingStatus(),
          SettingsApi.getAutorespondSettings(),
          SettingsApi.getWorkspaceSettings(),
          SettingsApi.getSkipInternalDomainsStatus(),
          SettingsApi.getLienTestModeStatus(),
          SettingsApi.getBillBalanceTestModeStatus(),
        ]);
        if (!mounted) return;
        setStatus(processingPayload);
        setAutorespond(autorespondPayload);
        setSenderVerificationEnabled(workspacePayload.enable_sender_verification);
        setSkipInternalDomains(internalDomainsPayload.skip_internal_domains);
        // Derive lienMode from two backend settings
        const liensEnabled = autorespondPayload.liens?.enabled ?? false;
        const lienTestMode = lienTestModePayload.lien_test_mode ?? false;
        if (!liensEnabled) {
          setLienMode("off");
        } else if (lienTestMode) {
          setLienMode("sandbox");
        } else {
          setLienMode("production");
        }
        // Derive billBalanceMode from two backend settings
        const billBalanceEnabled = autorespondPayload.bill_balance_request?.enabled ?? false;
        const billBalanceTestMode = billBalanceTestModePayload.bill_balance_test_mode ?? false;
        if (!billBalanceEnabled) {
          setBillBalanceMode("off");
        } else if (billBalanceTestMode) {
          setBillBalanceMode("sandbox");
        } else {
          setBillBalanceMode("production");
        }
        setStatusError(null);
        setAutorespondError(null);
        setWorkspaceError(null);
        setInternalDomainsError(null);
        setLienModeError(null);
        setBillBalanceModeError(null);
      } catch (error) {
        if (!mounted) return;
        if (error instanceof ApiError && error.status === 401) {
          window.location.href = "/login";
          return;
        }
        const message =
          error instanceof Error ? error.message : "Unexpected error occurred";
        setStatusError(message);
        setAutorespondError(message);
      } finally {
        if (mounted) setIsLoading(false);
      }
    };

    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  const setBusyFlag = (key: string, value: boolean) =>
    setBusy((prev) => ({ ...prev, [key]: value }));

  const isGlobalDisabled = useMemo(
    () => !autorespond?.global_autorespond_enabled,
    [autorespond]
  );
  const globalEnabled = autorespond?.global_autorespond_enabled ?? false;

  const handleProcessingToggle = async (enabled: boolean) => {
    setBusyFlag("processing", true);
    try {
      const payload = await SettingsApi.toggleProcessing(enabled);
      setStatus(payload);
      setStatusError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to update setting";
      setStatusError(message);
    } finally {
      setBusyFlag("processing", false);
    }
  };

  const handleGlobalAutorespondToggle = async (enabled: boolean) => {
    setBusyFlag("global", true);
    try {
      const payload = await SettingsApi.toggleGlobalAutorespond(enabled);
      setAutorespond((prev) =>
        prev
          ? {
              ...prev,
              global_autorespond_enabled: payload.global_autorespond_enabled,
            }
          : prev
      );
      setAutorespondError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error ? error.message : "Failed to update global toggle";
      setAutorespondError(message);
    } finally {
      setBusyFlag("global", false);
    }
  };

  const handleSenderVerificationToggle = async (enabled: boolean) => {
    setBusyFlag("sender_verification", true);
    try {
      await SettingsApi.toggleSenderVerification(enabled);
      setSenderVerificationEnabled(enabled);
      setWorkspaceError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update sender verification";
      setWorkspaceError(message);
    } finally {
      setBusyFlag("sender_verification", false);
    }
  };

  const handleSkipInternalDomainsToggle = async (enabled: boolean) => {
    setBusyFlag("skip_internal_domains", true);
    try {
      await SettingsApi.toggleSkipInternalDomains(enabled);
      setSkipInternalDomains(enabled);
      setInternalDomainsError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update internal domain filtering";
      setInternalDomainsError(message);
    } finally {
      setBusyFlag("skip_internal_domains", false);
    }
  };

  const handleLienModeChange = async (mode: LienMode) => {
    setBusyFlag("lien_mode", true);
    try {
      // Derive the two backend settings from the mode
      const liensEnabled = mode !== "off";
      const testMode = mode === "sandbox";

      // Update both settings
      await Promise.all([
        SettingsApi.toggleAutorespond("autorespond_liens", liensEnabled),
        SettingsApi.toggleLienTestMode(testMode),
      ]);

      // Update local state
      setLienMode(mode);
      setAutorespond((prev) =>
        prev
          ? {
              ...prev,
              liens: prev.liens ? { ...prev.liens, enabled: liensEnabled } : prev.liens,
            }
          : prev
      );
      setLienModeError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update lien mode";
      setLienModeError(message);
    } finally {
      setBusyFlag("lien_mode", false);
    }
  };

  const handleBillBalanceModeChange = async (mode: BillBalanceMode) => {
    setBusyFlag("bill_balance_mode", true);
    try {
      // Derive the two backend settings from the mode
      const billBalanceEnabled = mode !== "off";
      const testMode = mode === "sandbox";

      // Update both settings
      await Promise.all([
        SettingsApi.toggleAutorespond("autorespond_bill_balance_request", billBalanceEnabled),
        SettingsApi.toggleBillBalanceTestMode(testMode),
      ]);

      // Update local state
      setBillBalanceMode(mode);
      setAutorespond((prev) =>
        prev
          ? {
              ...prev,
              bill_balance_request: prev.bill_balance_request
                ? { ...prev.bill_balance_request, enabled: billBalanceEnabled }
                : prev.bill_balance_request,
            }
          : prev
      );
      setBillBalanceModeError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update bill balance mode";
      setBillBalanceModeError(message);
    } finally {
      setBusyFlag("bill_balance_mode", false);
    }
  };

  const handleAutorespondToggle = async (type: string, enabled: boolean) => {
    setBusyFlag(type, true);
    try {
      await SettingsApi.toggleAutorespond(type, enabled);
      setAutorespond((prev) =>
        prev
          ? {
              ...prev,
              ...mapAutorespondUpdate(prev, type, enabled),
            }
          : prev
      );
      setAutorespondError(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        window.location.href = "/login";
        return;
      }
      const message =
        error instanceof Error
          ? error.message
          : "Failed to update autorespond";
      setAutorespondError(message);
    } finally {
      setBusyFlag(type, false);
    }
  };

  const logout = async () => {
    try {
      await SettingsApi.logout();
    } catch (error) {
      console.error("Failed to logout", error);
    } finally {
      window.location.href = "/login";
    }
  };

  if (isLoading) {
    return (
      <section className="flex min-h-screen items-center justify-center px-6 py-16">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
          className="rounded-3xl border border-slate-200/80 bg-white/80 px-10 py-12 text-center shadow-2xl"
        >
          <p className="text-base font-medium text-slate-500">Loading settings…</p>
        </motion.div>
      </section>
    );
  }

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
      <nav className="grid gap-3 rounded-3xl border border-white/60 bg-white/80 p-3 shadow-xl shadow-slate-900/5 backdrop-blur lg:grid-cols-4">
        {MENU_ITEMS.map((item) => {
          const isActive = item.href === "/";
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded-2xl border p-4 transition hover:-translate-y-1 hover:shadow-lg ${
                isActive
                  ? "border-slate-900 bg-slate-900 text-white shadow-lg"
                  : "border-slate-200 bg-white text-slate-700"
              }`}
            >
              <div className="flex items-center gap-3 text-lg font-semibold">
                <span>{item.icon}</span>
                {item.label}
              </div>
              <p
                className={`mt-1 text-sm ${
                  isActive ? "text-white/80" : "text-slate-500"
                }`}
              >
                {item.description}
              </p>
            </Link>
          );
        })}
      </nav>

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={easing}
        className="flex flex-col gap-4 rounded-3xl border border-white/40 bg-gradient-to-br from-indigo-500 via-purple-500 to-sky-500 p-8 text-white shadow-2xl"
      >
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-white/70">EmailTag Control Center</p>
            <h1 className="text-3xl font-semibold">Automation Switchboard</h1>
            <p className="text-white/80">
              Toggle core processing pipelines and autorespond teams without redeploying the
              backend.
            </p>
          </div>
          <div className="flex items-center gap-3 rounded-2xl bg-white/15 px-4 py-2 text-sm backdrop-blur">
            <BadgeCheck className="h-4 w-4 text-emerald-200" />
            <span>{user}</span>
            <span className="text-white/60">•</span>
            <Button
              onClick={logout}
              variant="ghost"
              className="border-white/30 text-white/90 hover:bg-white/10 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              Logout
            </Button>
          </div>
        </div>
        <div className="grid gap-3 text-sm text-white/80 sm:grid-cols-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Processing</p>
            <p className="text-lg font-semibold">
              {status?.processing_enabled ? "Enabled" : "Paused"}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Last Updated</p>
            <p className="text-lg font-semibold">{formatDate(status?.last_updated ?? null)}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-white/60">Updated by</p>
            <p className="text-lg font-semibold">{status?.updated_by ?? "System"}</p>
          </div>
        </div>
      </motion.div>

      <div className="space-y-8">
        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={easing}
        >
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl">
                <ShieldCheck className="h-6 w-6 text-brand.indigo" /> Email Processing Master Switch
              </CardTitle>
              <CardDescription>
                {status?.description ??
                  "This toggle pauses the entire classification + tagging pipeline while still accepting webhook payloads."}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-900">Status</p>
                  <Badge
                    className={
                      status?.processing_enabled ? STATUS_BADGE.enabled : STATUS_BADGE.disabled
                    }
                  >
                    {status?.processing_enabled ? "Enabled" : "Disabled"}
                  </Badge>
                  <p className="text-xs text-slate-500">
                    Last updated {formatDate(status?.last_updated ?? null)} by{" "}
                    {status?.updated_by ?? "system"}
                  </p>
                </div>
                <ToggleRail
                  checked={status?.processing_enabled ?? false}
                  disabled={busy.processing}
                  onCheckedChange={handleProcessingToggle}
                />
              </div>
              <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
                When the switch is ON, inbound Front conversations are handed to Celery queues for
                tag/agent processing. Turning it OFF keeps the webhook listener alive but stops
                classification so you can perform maintenance safely.
              </div>
              {statusError && <ErrorBanner message={statusError} />}
            </CardContent>
          </Card>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.05 }}
        >
          <Card className="h-full border-amber-200 bg-gradient-to-br from-amber-50 to-orange-50">
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl">
                <ShieldCheck className="h-6 w-6 text-amber-600" /> Security Settings
              </CardTitle>
              <CardDescription>
                Configure security features for PHI protection
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-900">Sender Verification</p>
                  <Badge
                    className={
                      senderVerificationEnabled
                        ? "bg-green-50 text-green-700 border-green-200"
                        : "bg-amber-50 text-amber-700 border-amber-200"
                    }
                  >
                    {senderVerificationEnabled ? "Enabled (Production)" : "Disabled (Testing)"}
                  </Badge>
                  <p className="text-xs text-slate-500">
                    {senderVerificationEnabled
                      ? "Only authorized senders can receive patient information"
                      : "⚠️ All senders can receive patient information (Testing mode)"}
                  </p>
                </div>
                <ToggleRail
                  checked={senderVerificationEnabled}
                  disabled={busy.sender_verification}
                  onCheckedChange={handleSenderVerificationToggle}
                />
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900">
                <strong>Production Mode (ON):</strong> Sender email is verified against study participants before sharing PHI. Unauthorized senders receive HIPAA form.
                <br /><br />
                <strong>Testing Mode (OFF):</strong> Sender verification is disabled. All senders can receive patient information. ⚠️ Use only for testing!
              </div>
              {workspaceError && <ErrorBanner message={workspaceError} />}

              <hr className="border-amber-200" />

              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-900">Internal Domain Filtering</p>
                  <Badge
                    className={
                      skipInternalDomains
                        ? "bg-green-50 text-green-700 border-green-200"
                        : "bg-amber-50 text-amber-700 border-amber-200"
                    }
                  >
                    {skipInternalDomains ? "Enabled (Production)" : "Disabled (Testing)"}
                  </Badge>
                  <p className="text-xs text-slate-500">
                    {skipInternalDomains
                      ? "Internal emails (@preciseimaging.com, @mediflow.com) are skipped"
                      : "⚠️ Internal emails are processed (Testing mode)"}
                  </p>
                </div>
                <ToggleRail
                  checked={skipInternalDomains}
                  disabled={busy.skip_internal_domains}
                  onCheckedChange={handleSkipInternalDomainsToggle}
                />
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-900">
                <strong>Production Mode (ON):</strong> Emails from @preciseimaging.com and @mediflow.com are automatically skipped and not processed by AI.
                <br /><br />
                <strong>Testing Mode (OFF):</strong> All emails are processed regardless of sender domain. ⚠️ Use only for testing!
              </div>
              {internalDomainsError && <ErrorBanner message={internalDomainsError} />}
            </CardContent>
          </Card>
        </motion.section>

        <motion.section
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...easing, delay: 0.1 }}
        >
          <Card className="h-full">
            <CardHeader>
              <CardTitle className="flex items-center gap-3 text-2xl">
                <MailSearch className="h-6 w-6 text-brand.indigo" /> Global Autorespond
              </CardTitle>
              <CardDescription>
                Acts as the fail-safe for every autorespond workflow powered by `app/agents`.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-slate-900">Status</p>
                  <Badge
                    className={
                      globalEnabled ? STATUS_BADGE.enabled : STATUS_BADGE.disabled
                    }
                  >
                    {globalEnabled ? "Enabled" : "Disabled"}
                  </Badge>
                  <p className="text-xs text-slate-500">
                    {globalEnabled
                      ? "Automation is live for all autorespond teams."
                      : "All autorespond teams are paused until you re-enable this switch."}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1">
                  <span className="text-xs font-semibold uppercase tracking-[0.3em] text-slate-500">
                    Master toggle
                  </span>
                  <div className="rounded-2xl bg-gradient-to-r from-slate-900 to-indigo-900 p-2 shadow-lg shadow-indigo-900/30">
                    <ToggleRail
                      checked={globalEnabled}
                      disabled={busy.global}
                      onCheckedChange={handleGlobalAutorespondToggle}
                      variant="dark"
                    />
                  </div>
                </div>
              </div>
              <div className="rounded-2xl border border-amber-200 bg-amber-50/80 px-4 py-3 text-sm text-amber-800">
                When disabled, all autorespond toggles below are locked. Re-enable this switch to
                tune per-tag experiences.
              </div>
              {autorespondError && <ErrorBanner message={autorespondError} />}
            </CardContent>
          </Card>
        </motion.section>
      </div>

      <motion.section
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...easing, delay: 0.1 }}
        className="space-y-6"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-2xl font-semibold text-slate-900">Autorespond Teams</h2>
            <p className="text-sm text-slate-500">
              Toggle the AI agent that drafts each outbound reply. Settings inherit the global
              master switch.
            </p>
          </div>
          <Badge className="bg-slate-900 text-white border-slate-900">
            {autorespond?.global_autorespond_enabled ? "Live" : "Paused"}
          </Badge>
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          {AUTORESPOND_LAYOUT.map(({ key, settingKey, accent, icon: Icon }) => {
            const detail = autorespond?.[key];
            const toggleKey = settingKey;
            const disabled = isGlobalDisabled || busy[settingKey];
            return (
              <motion.div
                key={key}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ ...easing, delay: 0.08 }}
                className="h-full"
              >
                <Card className={isGlobalDisabled ? "opacity-60" : "opacity-100"}>
                  <CardContent className="space-y-4 pt-6">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div className="space-y-1">
                        <div className="flex items-center gap-3">
                          <span
                            className={`flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br ${accent} text-white shadow-lg`}
                          >
                            <Icon className="h-5 w-5" />
                          </span>
                          <div>
                            <p className="text-base font-semibold text-slate-900">
                              {detail?.label}
                            </p>
                            <p className="text-xs uppercase tracking-wide text-slate-400">
                              {settingKey.replace("autorespond_", "").replace(/_/g, " ")}
                            </p>
                          </div>
                        </div>
                        <p className="text-sm text-slate-500">{detail?.description}</p>
                      </div>
                      <ToggleRail
                        checked={detail?.enabled ?? false}
                        disabled={disabled}
                        onCheckedChange={(value) => handleAutorespondToggle(settingKey, value)}
                      />
                    </div>
                    <Badge
                      className={detail?.enabled ? STATUS_BADGE.enabled : STATUS_BADGE.disabled}
                    >
                      {detail?.enabled ? "Enabled" : "Disabled"}
                    </Badge>
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}

          {/* Liens 3-way toggle (Off / Sandbox / Production) */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...easing, delay: 0.08 }}
            className="h-full"
          >
            <Card className={isGlobalDisabled ? "opacity-60" : "opacity-100"}>
              <CardContent className="space-y-4 pt-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-500 to-indigo-600 text-white shadow-lg">
                        <ShieldCheck className="h-5 w-5" />
                      </span>
                      <div>
                        <p className="text-base font-semibold text-slate-900">
                          {autorespond?.liens?.label ?? "Liens (ASL & PSL)"}
                        </p>
                        <p className="text-xs uppercase tracking-wide text-slate-400">
                          liens
                        </p>
                      </div>
                    </div>
                    <p className="text-sm text-slate-500">
                      {autorespond?.liens?.description ?? "Automatically upload lien documents and send confirmation responses"}
                    </p>
                  </div>
                  <SegmentedControl
                    options={LIEN_MODE_OPTIONS}
                    value={lienMode}
                    onChange={handleLienModeChange}
                    disabled={isGlobalDisabled || busy.lien_mode}
                  />
                </div>
                {lienModeError && <ErrorBanner message={lienModeError} />}
              </CardContent>
            </Card>
          </motion.div>

          {/* Bill Balance 3-way toggle (Off / Sandbox / Production) */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...easing, delay: 0.1 }}
            className="h-full"
          >
            <Card className={isGlobalDisabled ? "opacity-60" : "opacity-100"}>
              <CardContent className="space-y-4 pt-6">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-3">
                      <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-lg">
                        <PiggyBank className="h-5 w-5" />
                      </span>
                      <div>
                        <p className="text-base font-semibold text-slate-900">
                          {autorespond?.bill_balance_request?.label ?? "Bill or Balance Request"}
                        </p>
                        <p className="text-xs uppercase tracking-wide text-slate-400">
                          bill balance
                        </p>
                      </div>
                    </div>
                    <p className="text-sm text-slate-500">
                      {autorespond?.bill_balance_request?.description ?? "Automatically respond to bill or balance request emails"}
                    </p>
                  </div>
                  <SegmentedControl
                    options={BILL_BALANCE_MODE_OPTIONS}
                    value={billBalanceMode}
                    onChange={handleBillBalanceModeChange}
                    disabled={isGlobalDisabled || busy.bill_balance_mode}
                  />
                </div>
                {billBalanceModeError && <ErrorBanner message={billBalanceModeError} />}
              </CardContent>
            </Card>
          </motion.div>
        </div>
      </motion.section>
    </div>
  );
}

function mapAutorespondUpdate(
  prev: AutorespondSettingsResponse,
  type: string,
  enabled: boolean
): Partial<AutorespondSettingsResponse> {
  const mapped = AUTORESPOND_LOOKUP[type];
  if (mapped) {
    return {
      [mapped]: {
        ...prev[mapped],
        enabled,
      },
    } as Partial<AutorespondSettingsResponse>;
  }

  return {};
}

interface ToggleRailProps {
  checked: boolean;
  disabled?: boolean;
  onCheckedChange: (value: boolean) => void;
  variant?: "light" | "dark";
}

function ToggleRail({
  checked,
  disabled,
  onCheckedChange,
  variant = "light",
}: ToggleRailProps) {
  const baseClass =
    variant === "dark"
      ? "bg-gradient-to-r from-slate-900 via-slate-800 to-slate-900 text-white shadow-[0_10px_25px_rgba(12,14,40,0.65)] border border-white/20"
      : "border border-slate-200 bg-white/90 text-slate-700 shadow-inner";
  const offActive =
    variant === "dark" ? "bg-white/25 text-white" : "bg-rose-50 text-rose-600";
  const onActive =
    variant === "dark" ? "bg-lime-200 text-slate-900" : "bg-emerald-50 text-emerald-700";

  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full p-1 text-xs font-semibold uppercase tracking-[0.2em]",
        baseClass,
        disabled && "opacity-60"
      )}
      role="group"
      aria-label="Toggle"
    >
      <button
        type="button"
        disabled={disabled || !checked}
        onClick={() => onCheckedChange(false)}
        className={cn(
          "min-w-[4.5rem] rounded-full px-3 py-2 transition",
          checked ? "text-slate-400" : offActive
        )}
      >
        Off
      </button>
      <button
        type="button"
        disabled={disabled || checked}
        onClick={() => onCheckedChange(true)}
        className={cn(
          "min-w-[4.5rem] rounded-full px-3 py-2 transition",
          checked ? onActive : "text-slate-400"
        )}
      >
        On
      </button>
    </div>
  );
}
