"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BadgeCheck } from "lucide-react";

import { ApiError, SettingsApi, TemplatesApi } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";

import {
  DEFAULT_CUSTOM_PLACEHOLDERS,
  MENU_ITEMS,
  TAG_OPTIONS,
} from "./constants/template-config.constants";
import { getTagLabel } from "./utils/template-helpers";
import { StatusBanner } from "./components/StatusBanner";
import { PlaceholderManager } from "./components/PlaceholderManager";
import { LienTemplatesEditor } from "./components/LienTemplatesEditor";
import { BillBalanceTemplatesEditor } from "./components/BillBalanceTemplatesEditor";
import { UnifiedTemplateEditor } from "./components/UnifiedTemplateEditor";
import { AptStatusReqTemplatesEditor } from "./components/AptStatusReqTemplatesEditor";
import PlaceholderSection from "./components/PlaceholderSection";
import { DocumentAttachments } from "./components/DocumentAttachments";
import { useTagSettings, normalizeCustomPlaceholdersFromSettings } from "./hooks/useTagSettings";

export default function TemplateConfigPage() {
  const [currentUser, setCurrentUser] = useState("Admin");
  const [selectedTag, setSelectedTag] = useState(TAG_OPTIONS[0].value);
  const [baseCustomPlaceholders, setBaseCustomPlaceholders] = useState<Record<string, string>>({
    ...DEFAULT_CUSTOM_PLACEHOLDERS,
  });
  const [workspaceStatus, setWorkspaceStatus] = useState<{type: "success" | "error" | "info", message: string} | null>(null);

  const {
    tagSettings,
    tagMeta,
    tagStatus,
    tagLoading,
    handleSaveTagSettings,
    handleResetTagSettings,
    handleFieldChange,
  } = useTagSettings(selectedTag, currentUser);

  useEffect(() => {
    let mounted = true;
    const bootstrap = async () => {
      try {
        const auth = await SettingsApi.getAuthStatus();
        if (!auth.authenticated) {
          window.location.href = "/login";
          return;
        }
        if (mounted) {
          setCurrentUser(auth.username ?? "Admin");
        }
      } catch (error) {
        if (
          error instanceof ApiError &&
          (error.status === 401 || error.status === 403)
        ) {
          window.location.href = "/login";
          return;
        }
        console.error("Failed to load auth status", error);
      }
    };
    bootstrap();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    let mounted = true;
    const loadWorkspacePlaceholders = async () => {
      try {
        // Load from WORKSPACE tag entry (workspace-wide custom placeholders)
        const workspaceSettings = await TemplatesApi.getTagSettings("WORKSPACE");
        if (!mounted) return;
        const placeholders = workspaceSettings.settings.custom_placeholders || {};
        setBaseCustomPlaceholders(
          Object.keys(placeholders).length > 0 ? placeholders : { ...DEFAULT_CUSTOM_PLACEHOLDERS }
        );
      } catch (error) {
        // If WORKSPACE doesn't exist, use defaults
        console.warn("Failed to load workspace custom placeholders, using defaults", error);
        setBaseCustomPlaceholders({ ...DEFAULT_CUSTOM_PLACEHOLDERS });
      }
    };
    void loadWorkspacePlaceholders();
    return () => {
      mounted = false;
    };
  }, []);

  // Custom placeholders are workspace-wide (loaded from WORKSPACE tag)
  // Individual tags no longer have their own custom_placeholders
  const mergedCustomPlaceholders = baseCustomPlaceholders;

  const logout = async () => {
    try {
      await SettingsApi.logout();
    } catch (error) {
      console.error("Logout failed", error);
    } finally {
      window.location.href = "/login";
    }
  };

  const selectedTagLabel = getTagLabel(selectedTag);

  // Workspace custom placeholders save handler
  const handleSaveWorkspacePlaceholders = async (placeholders?: Record<string, string>) => {
    try {
      // Use provided placeholders or fall back to current state
      const placeholdersToSave = placeholders !== undefined ? placeholders : baseCustomPlaceholders;

      const payload = {
        settings: { custom_placeholders: placeholdersToSave },
        updated_by: currentUser,
      };
      await TemplatesApi.updateTagSettings("WORKSPACE", payload);

      // Update local state with saved placeholders
      setBaseCustomPlaceholders(placeholdersToSave);

      setWorkspaceStatus({
        type: "success",
        message: "Workspace custom placeholders saved successfully.",
      });
    } catch (error) {
      setWorkspaceStatus({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to save workspace placeholders.",
      });
    }
  };

  const handleWorkspacePlaceholderChange = (placeholders: Record<string, string>) => {
    setBaseCustomPlaceholders(placeholders);
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
      <nav className="grid gap-3 rounded-3xl border border-white/60 bg-white/80 p-3 shadow-xl shadow-slate-900/5 backdrop-blur sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-6">
        {MENU_ITEMS.map((item) => {
          const isActive = item.href === "/template-config";
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

      <Card className="rounded-3xl border border-white/40 bg-gradient-to-br from-indigo-500 via-purple-500 to-sky-500 p-8 text-white shadow-2xl">
        <CardHeader className="p-0">
          <CardTitle className="flex flex-wrap items-center justify-between gap-4 text-3xl">
            <div>
              <p className="text-sm uppercase tracking-[0.3em] text-white/70">
                EmailTag authoring
              </p>
              Template & Tag Configuration
            </div>
            <div className="flex items-center gap-3 rounded-2xl bg-white/15 px-4 py-2 text-sm backdrop-blur">
              <BadgeCheck className="h-4 w-4 text-emerald-200" />
              <span>{currentUser}</span>
              <span className="text-white/60">•</span>
              <Button
                variant="ghost"
                onClick={logout}
                className="border-white/30 text-white/90 hover:bg-white/10 hover:text-white"
              >
                Logout
              </Button>
            </div>
          </CardTitle>
          <CardDescription className="text-white/80">
            Update AI-generated autorespond templates and keep Apt status req
            contact data in sync without hand-editing JSON.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-xl text-slate-900">
            ⚙️ Tag Settings Workspace
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-8">
          {/* Placeholder Manager - Works with WORKSPACE custom placeholders */}
          <PlaceholderManager
            tagSettings={{ ...tagSettings, custom_placeholders: baseCustomPlaceholders }}
            onFieldChange={(key, value) => {
              if (key === "custom_placeholders") {
                handleWorkspacePlaceholderChange(value as Record<string, string>);
              }
            }}
            onSave={handleSaveWorkspacePlaceholders}
            onReset={() => {
              // Reload workspace placeholders
              window.location.reload();
            }}
          />

          {/* Tag Selector */}
          <label className="space-y-2 text-sm font-medium text-slate-700">
            Select autorespond tag
            <select
              value={selectedTag}
              onChange={(event) => setSelectedTag(event.target.value)}
              className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
            >
              {TAG_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          {/* Status Banner */}
          {tagStatus && <StatusBanner status={tagStatus} />}

          {/* Loading State */}
          {tagLoading ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-10 text-center text-slate-500">
              Loading settings...
            </div>
          ) : (
            <>
              {/* Placeholder Section - Dynamic based on selected tag */}
              <PlaceholderSection
                selectedTag={selectedTag}
                customPlaceholders={mergedCustomPlaceholders}
              />

              {/* Lien Templates Editor - Show for Lien Templates tag */}
              {selectedTag === "Lien Templates" && (
                <>
                  <LienTemplatesEditor
                    tagSettings={tagSettings}
                    customPlaceholders={mergedCustomPlaceholders}
                    onFieldChange={handleFieldChange}
                    onSave={handleSaveTagSettings}
                    onReset={handleResetTagSettings}
                  />
                  <DocumentAttachments
                    tagName={selectedTag}
                    currentUser={currentUser}
                  />
                </>
              )}

              {/* Bill Balance Templates Editor - Show for Bill or Balance Request tag */}
              {selectedTag === "Bill or Balance Request" && (
                <>
                  <BillBalanceTemplatesEditor
                    tagSettings={tagSettings}
                    customPlaceholders={mergedCustomPlaceholders}
                    onFieldChange={handleFieldChange}
                    onSave={handleSaveTagSettings}
                    onReset={handleResetTagSettings}
                  />
                  <DocumentAttachments
                    tagName={selectedTag}
                    currentUser={currentUser}
                  />
                </>
              )}

              {/* Apt Status Req Templates Editor - Show for Apt status req */}
              {selectedTag === "Apt status req" && (
                <>
                  <AptStatusReqTemplatesEditor
                    tagSettings={tagSettings}
                    customPlaceholders={mergedCustomPlaceholders}
                    onFieldChange={handleFieldChange}
                    onSave={handleSaveTagSettings}
                    onReset={handleResetTagSettings}
                  />
                  <DocumentAttachments
                    tagName={selectedTag}
                    currentUser={currentUser}
                  />
                </>
              )}

              {/* Metadata */}
              {tagMeta && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
                  <div className="flex flex-wrap gap-4">
                    <span>
                      Last updated:{" "}
                      {new Date(tagMeta.updated_at).toLocaleString()}
                    </span>
                    <span>By: {tagMeta.updated_by ?? "Unknown"}</span>
                  </div>
                </div>
              )}

              {/* Save/Reset Buttons */}
              <div className="flex flex-wrap justify-end gap-3">
                <Button variant="ghost" onClick={handleResetTagSettings}>
                  Reset Changes
                </Button>
                <Button onClick={handleSaveTagSettings} className="bg-slate-900 text-white">
                  Save Settings
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
