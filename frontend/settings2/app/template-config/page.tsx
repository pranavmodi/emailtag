"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { BadgeCheck, Cog, FileEdit, Info } from "lucide-react";

import { ApiError, SettingsApi, TemplatesApi } from "@/lib/api";
import type {
  MessageTemplateResponse,
  TagSettingsResponse,
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

import "react-quill/dist/quill.snow.css";

const ReactQuill = dynamic(() => import("react-quill"), { ssr: false });

type StatusMessage = { type: "success" | "error" | "info"; message: string };

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
    active: true,
  },
  {
    href: "/tag-statistics",
    label: "Tag Statistics",
    description: "Analyze tag retention and changes",
    icon: "📊",
  },
] as const;

const SHOW_TEMPLATE_EDITOR = false;

const TEMPLATE_DEFINITIONS = {
  apt_status_req_found: {
    key: "apt_status_req_found",
    name: "Appointment Found - Detailed View",
    description:
      "Used when an appointment is located for the patient. Includes exam details, welfare guidance, and portal links.",
    placeholders: [
      "{patient_id_confirmed}",
      "{no_show_policy}",
      "{studies_table_rows}",
      "{personal_injury_info}",
      "{bills_link}",
      "{reports_link}",
    ],
    defaultContent: `Patient ID: {patient_id_confirmed}<br/><br/>
<b>Our direct scheduling phone # is 800-558-2223 and we can assist with directions, rescheduling, canceling, or any other scheduling-related questions.</b><br/>
{no_show_policy}<br/><br/>
Here is a summary of the patient's exams we currently have entered into our system:<table border="1" style="border-collapse: collapse; width: 100%;"><thead><tr><th style="border: 1px solid black; padding: 8px; text-align: left;">Study ID</th><th style="border: 1px solid black; padding: 8px; text-align: left;">Exam Description</th><th style="border: 1px solid black; padding: 8px; text-align: left;">Status</th><th style="border: 1px solid black; padding: 8px; text-align: left;">Study Date/Time</th><th style="border: 1px solid black; padding: 8px; text-align: left;">Location</th><th style="border: 1px solid black; padding: 8px; text-align: left;">MRI Type</th><th style="border: 1px solid black; padding: 8px; text-align: left;">Images Available</th><th style="border: 1px solid black; padding: 8px; text-align: left;">Report Available</th></tr></thead><tbody>{studies_table_rows}</tbody></table>
<br/>
{personal_injury_info}
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account): <a href="{bills_link}">Click Here</a><br/>
Access reports & images (Request login here for reports): <a href="{reports_link}">Click Here</a><br/>`,
  },
  apt_status_req_not_found: {
    key: "apt_status_req_not_found",
    name: "Appointment Not Found",
    description:
      "Sent when a patient ID exists but no appointments are attached. Requests extra information from the sender.",
    placeholders: ["{patient_id}"],
    defaultContent:
      "We found your Patient ID: {patient_id}, but could not find any upcoming appointments. If you believe this is an error, please provide the approximate date and type of your exam so our team can investigate further. A member of our team will also review this request.",
  },
  apt_status_req_db_error: {
    key: "apt_status_req_db_error",
    name: "Database Error",
    description:
      "Recovers gracefully when we can't reach the appointment database.",
    placeholders: ["{patient_id}"],
    defaultContent:
      "We encountered a technical difficulty while trying to fetch your appointment details for Patient ID: {patient_id}. Our team has been notified and will look into this.",
  },
} as const;

type TemplateKey = keyof typeof TEMPLATE_DEFINITIONS;

const TAG_OPTIONS = [{ value: "Apt status req", label: "Apt Status Req" }];

const DEFAULT_TAG_SETTINGS = {
  scheduling_phone_number: "",
  no_show_policy: "",
  portal_link_bills: "",
  portal_link_reports: "",
  intro_text: "",
  table_intro_text: "",
  personal_injury_text: "",
  footer_text: "",
};

const getTagLabel = (value: string) =>
  TAG_OPTIONS.find((option) => option.value === value)?.label ?? value;

export default function TemplateConfigPage() {
  const [currentUser, setCurrentUser] = useState("Admin");
  const [activeTab, setActiveTab] = useState<"templates" | "tag-settings">(
    SHOW_TEMPLATE_EDITOR ? "templates" : "tag-settings"
  );

  // Template state
  const [selectedTemplate, setSelectedTemplate] = useState<
    TemplateKey | ""
  >("");
  const [templateContent, setTemplateContent] = useState("");
  const [templateStatus, setTemplateStatus] =
    useState<StatusMessage | null>(null);
  const [templateMeta, setTemplateMeta] =
    useState<MessageTemplateResponse | null>(null);
  const [templateLoading, setTemplateLoading] = useState(false);
  const [templateExists, setTemplateExists] = useState(false);
  const [templateOriginal, setTemplateOriginal] = useState("");

  // Tag settings state
  const [selectedTag, setSelectedTag] = useState(TAG_OPTIONS[0].value);
  const [tagSettings, setTagSettings] = useState(DEFAULT_TAG_SETTINGS);
  const [tagOriginal, setTagOriginal] = useState(DEFAULT_TAG_SETTINGS);
  const [tagMeta, setTagMeta] = useState<TagSettingsResponse | null>(null);
  const [tagStatus, setTagStatus] = useState<StatusMessage | null>(null);
  const [tagLoading, setTagLoading] = useState(false);

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
    if (activeTab === "tag-settings") {
      void loadTagSettings(selectedTag);
    }
  }, [activeTab, selectedTag]);

  const quillModules = useMemo(
    () => ({
      toolbar: [
        ["bold", "italic", "underline", "strike"],
        [{ header: 1 }, { header: 2 }],
        [{ list: "ordered" }, { list: "bullet" }],
        [{ indent: "-1" }, { indent: "+1" }],
        [{ size: ["small", false, "large", "huge"] }],
        [{ color: [] }, { background: [] }],
        [{ align: [] }],
        ["blockquote", "code-block"],
        ["link", "clean"],
      ],
    }),
    []
  );

  const handleTemplateSelect = async (value: string) => {
    setSelectedTemplate(value as TemplateKey);
    setTemplateStatus(null);
    if (!value) {
      setTemplateContent("");
      setTemplateMeta(null);
      setTemplateExists(false);
      return;
    }

    const definition = TEMPLATE_DEFINITIONS[value as TemplateKey];
    setTemplateLoading(true);
    try {
      const template = await TemplatesApi.getTemplate(definition.key);
      setTemplateContent(template.template_body);
      setTemplateOriginal(template.template_body);
      setTemplateExists(true);
      setTemplateMeta(template);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setTemplateContent(definition.defaultContent);
        setTemplateOriginal(definition.defaultContent);
        setTemplateExists(false);
        setTemplateMeta(null);
        setTemplateStatus({
          type: "info",
          message: "No saved version yet. Using default scaffold.",
        });
      } else {
        setTemplateStatus({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to load template.",
        });
      }
    } finally {
      setTemplateLoading(false);
    }
  };

  const handleSaveTemplate = async () => {
    if (!selectedTemplate) return;
    const definition = TEMPLATE_DEFINITIONS[selectedTemplate];
    setTemplateStatus(null);

    const payload = {
      template_name: definition.name,
      template_body: templateContent,
      description: definition.description,
      updated_by: currentUser,
    };

    try {
      let response: MessageTemplateResponse;
      if (templateExists) {
        response = await TemplatesApi.updateTemplate(definition.key, payload);
      } else {
        response = await TemplatesApi.createTemplate(definition.key, payload);
        setTemplateExists(true);
      }
      setTemplateMeta(response);
      setTemplateOriginal(response.template_body);
      setTemplateStatus({
        type: "success",
        message: "Template saved successfully.",
      });
    } catch (error) {
      setTemplateStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to save template.",
      });
    }
  };

  const handleResetTemplate = () => {
    setTemplateContent(templateOriginal);
    setTemplateStatus({
      type: "info",
      message: "Editor reset to the last loaded version.",
    });
  };

  const loadTagSettings = async (tagName: string) => {
    setTagLoading(true);
    setTagStatus(null);
    try {
      const response = await TemplatesApi.getTagSettings(tagName);
      const nextSettings = {
        scheduling_phone_number:
          response.settings.scheduling_phone_number ?? "",
        no_show_policy: response.settings.no_show_policy ?? "",
        portal_link_bills: response.settings.portal_link_bills ?? "",
        portal_link_reports: response.settings.portal_link_reports ?? "",
        intro_text: response.settings.intro_text ?? "",
        table_intro_text: response.settings.table_intro_text ?? "",
        personal_injury_text: response.settings.personal_injury_text ?? "",
        footer_text: response.settings.footer_text ?? "",
      };
      setTagSettings(nextSettings);
      setTagOriginal(nextSettings);
      setTagMeta(response);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        setTagSettings(DEFAULT_TAG_SETTINGS);
        setTagOriginal(DEFAULT_TAG_SETTINGS);
        setTagMeta(null);
        setTagStatus({
          type: "info",
          message: `No settings saved yet for ${getTagLabel(tagName)}. Fill in the fields below.`,
        });
      } else {
        setTagStatus({
          type: "error",
          message:
            error instanceof Error
              ? error.message
              : "Failed to load tag settings.",
        });
      }
    } finally {
      setTagLoading(false);
    }
  };

  const handleSaveTagSettings = async () => {
    setTagStatus(null);
    try {
      const payload = {
        settings: tagSettings,
        updated_by: currentUser,
      };
      const response = await TemplatesApi.updateTagSettings(
        selectedTag,
        payload
      );
      setTagMeta(response);
      setTagOriginal(tagSettings);
      setTagStatus({
        type: "success",
        message: `${getTagLabel(selectedTag)} settings saved.`,
      });
    } catch (error) {
      setTagStatus({
        type: "error",
        message:
          error instanceof Error ? error.message : "Failed to save settings.",
      });
    }
  };

  const handleResetTagSettings = () => {
    setTagSettings(tagOriginal);
    setTagStatus({
      type: "info",
      message: "Form reset to the last loaded values.",
    });
  };

  const logout = async () => {
    try {
      await SettingsApi.logout();
    } catch (error) {
      console.error("Logout failed", error);
    } finally {
      window.location.href = "/login";
    }
  };

  return (
    <div className="mx-auto flex min-h-screen max-w-6xl flex-col gap-8 px-6 py-10">
      <nav className="grid gap-3 rounded-3xl border border-white/60 bg-white/80 p-3 shadow-xl shadow-slate-900/5 backdrop-blur lg:grid-cols-3">
        {MENU_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded-2xl border p-4 transition hover:-translate-y-1 hover:shadow-lg ${
              item.active
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
                item.active ? "text-white/80" : "text-slate-500"
              }`}
            >
              {item.description}
            </p>
          </Link>
        ))}
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
        <CardHeader className="flex flex-wrap gap-4">
          <CardTitle className="flex items-center gap-3 text-xl text-slate-900">
            <FileEdit className="h-5 w-5 text-brand.indigo" /> Workspace
          </CardTitle>
          {SHOW_TEMPLATE_EDITOR && (
            <div className="flex gap-2 rounded-full bg-slate-100 p-1 text-sm font-semibold text-slate-500">
              <button
                onClick={() => setActiveTab("templates")}
                className={`rounded-full px-4 py-1 transition ${
                  activeTab === "templates"
                    ? "bg-white text-slate-900 shadow"
                    : "hover:text-slate-700"
                }`}
              >
                📝 Message templates
              </button>
              <button
                onClick={() => setActiveTab("tag-settings")}
                className={`rounded-full px-4 py-1 transition ${
                  activeTab === "tag-settings"
                    ? "bg-white text-slate-900 shadow"
                    : "hover:text-slate-700"
                }`}
              >
                ⚙️ Tag settings
              </button>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-8">
          {SHOW_TEMPLATE_EDITOR && activeTab === "templates" ? (
            <TemplateEditor
              selectedTemplate={selectedTemplate}
              onSelectTemplate={handleTemplateSelect}
              templateContent={templateContent}
              setTemplateContent={setTemplateContent}
              templateMeta={templateMeta}
              templateStatus={templateStatus}
              templateLoading={templateLoading}
              onSave={handleSaveTemplate}
              onReset={handleResetTemplate}
              quillModules={quillModules}
            />
          ) : (
            <TagSettingsForm
              selectedTag={selectedTag}
              tagOptions={TAG_OPTIONS}
              onTagSelect={(value) => setSelectedTag(value)}
              tagSettings={tagSettings}
              onFieldChange={(key, value) =>
                setTagSettings((prev) => ({ ...prev, [key]: value }))
              }
              tagMeta={tagMeta}
              tagStatus={tagStatus}
              tagLoading={tagLoading}
              onSave={handleSaveTagSettings}
              onReset={handleResetTagSettings}
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface TemplateEditorProps {
  selectedTemplate: TemplateKey | "";
  onSelectTemplate: (key: string) => void;
  templateContent: string;
  setTemplateContent: (value: string) => void;
  templateMeta: MessageTemplateResponse | null;
  templateStatus: StatusMessage | null;
  templateLoading: boolean;
  onSave: () => void;
  onReset: () => void;
  quillModules: Record<string, unknown>;
}

function TemplateEditor({
  selectedTemplate,
  onSelectTemplate,
  templateContent,
  setTemplateContent,
  templateMeta,
  templateStatus,
  templateLoading,
  onSave,
  onReset,
  quillModules,
}: TemplateEditorProps) {
  const definition = selectedTemplate
    ? TEMPLATE_DEFINITIONS[selectedTemplate]
    : null;

  return (
    <div className="space-y-6">
      <label className="space-y-2 text-sm font-medium text-slate-700">
        Select template to edit
        <select
          value={selectedTemplate}
          onChange={(event) => onSelectTemplate(event.target.value)}
          className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
        >
          <option value="">-- Choose a scenario --</option>
          {Object.values(TEMPLATE_DEFINITIONS).map((template) => (
            <option key={template.key} value={template.key}>
              {template.name}
            </option>
          ))}
        </select>
      </label>

      {definition && (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-600">
            <div className="flex items-center gap-2 text-slate-900">
              <Info className="h-4 w-4 text-brand.indigo" /> {definition.name}
            </div>
            <p className="mt-2">{definition.description}</p>
            <div className="mt-3">
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Placeholders
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {definition.placeholders.map((placeholder) => (
                  <span
                    key={placeholder}
                    className="rounded-full bg-white px-3 py-1 text-xs font-semibold text-slate-600 shadow-sm"
                  >
                    {placeholder}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {templateStatus && <StatusBanner status={templateStatus} />}

          {templateLoading ? (
            <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-10 text-center text-slate-500">
              Loading template...
            </div>
          ) : (
            <>
              <div className="rounded-2xl border border-slate-200 p-2">
                <ReactQuill
                  value={templateContent}
                  onChange={setTemplateContent}
                  modules={quillModules}
                  theme="snow"
                  className="min-h-[300px]"
                />
              </div>

              {templateMeta && (
                <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3 text-sm text-slate-600">
                  <div className="flex flex-wrap gap-4">
                    <span>
                      Last updated:{" "}
                      {new Date(templateMeta.updated_at).toLocaleString()}
                    </span>
                    <span>By: {templateMeta.updated_by ?? "Unknown"}</span>
                  </div>
                </div>
              )}

              <div className="flex flex-wrap justify-end gap-3">
                <Button variant="ghost" onClick={onReset}>
                  Reset Changes
                </Button>
                <Button onClick={onSave} className="bg-slate-900 text-white">
                  Save Template
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

interface TagSettingsFormProps {
  selectedTag: string;
  tagOptions: typeof TAG_OPTIONS;
  onTagSelect: (value: string) => void;
  tagSettings: typeof DEFAULT_TAG_SETTINGS;
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string) => void;
  tagMeta: TagSettingsResponse | null;
  tagStatus: StatusMessage | null;
  tagLoading: boolean;
  onSave: () => void;
  onReset: () => void;
}

function TagSettingsForm({
  selectedTag,
  tagOptions,
  onTagSelect,
  tagSettings,
  onFieldChange,
  tagMeta,
  tagStatus,
  tagLoading,
  onSave,
  onReset,
}: TagSettingsFormProps) {
  const selectedTagLabel = getTagLabel(selectedTag);
  return (
    <div className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-slate-50/80 p-4 text-sm text-slate-600">
        <div className="flex items-center gap-2 text-slate-900">
          <Cog className="h-4 w-4 text-brand.indigo" /> {selectedTagLabel} settings
        </div>
        <p className="mt-2">
          These values feed the autoresponder when the {selectedTagLabel} agent
          drafts replies (phone numbers, policy text, and portal links).
        </p>
      </div>

      {tagStatus && <StatusBanner status={tagStatus} />}

      {tagLoading ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-10 text-center text-slate-500">
          Loading settings...
        </div>
      ) : (
        <>
          <label className="space-y-2 text-sm font-medium text-slate-700">
            Select autorespond tag
            <select
              value={selectedTag}
              onChange={(event) => onTagSelect(event.target.value)}
              className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
            >
              {tagOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="space-y-4">
            <label className="space-y-2 text-sm font-medium text-slate-700">
              Scheduling phone number
              <input
                type="tel"
                value={tagSettings.scheduling_phone_number}
                onChange={(event) =>
                  onFieldChange(
                    "scheduling_phone_number",
                    event.target.value
                  )
                }
                placeholder="800-558-2223"
                className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
              />
              <span className="text-xs text-slate-500">
                Displayed as the primary call-to-action.
              </span>
            </label>

            <label className="space-y-2 text-sm font-medium text-slate-700">
              No show policy
              <textarea
                value={tagSettings.no_show_policy}
                onChange={(event) =>
                  onFieldChange("no_show_policy", event.target.value)
                }
                className="min-h-[120px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
              />
              <span className="text-xs text-slate-500">
                HTML supported. Appears under the scheduling guidance block.
              </span>
            </label>

            <label className="space-y-2 text-sm font-medium text-slate-700">
              Bills & portal link
              <input
                type="url"
                value={tagSettings.portal_link_bills}
                onChange={(event) =>
                  onFieldChange("portal_link_bills", event.target.value)
                }
                placeholder="https://..."
                className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
              />
            </label>

            <label className="space-y-2 text-sm font-medium text-slate-700">
              Reports & images link
              <input
                type="url"
                value={tagSettings.portal_link_reports}
                onChange={(event) =>
                  onFieldChange("portal_link_reports", event.target.value)
                }
                placeholder="https://..."
                className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
              />
            </label>

            <div className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-4">
              <h3 className="mb-3 text-sm font-semibold text-slate-900">
                📧 Response Body Configuration
              </h3>
              <p className="mb-4 text-xs text-slate-600">
                Customize the text sections of the autoresponse email. The table structure itself is not configurable.
              </p>

              <label className="space-y-2 text-sm font-medium text-slate-700">
                Intro Text (before table)
                <textarea
                  value={tagSettings.intro_text}
                  onChange={(event) =>
                    onFieldChange("intro_text", event.target.value)
                  }
                  placeholder="Patient ID: {patient_id_confirmed}&#10;&#10;Our direct scheduling phone # is {scheduling_phone}..."
                  className="min-h-[150px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 font-mono text-sm shadow-inner focus:border-brand.indigo focus:outline-none"
                />
                <span className="text-xs text-slate-500">
                  HTML and placeholders supported: {"{patient_id_confirmed}"}, {"{scheduling_phone}"}, {"{no_show_policy}"}
                </span>
              </label>

              <label className="mt-4 space-y-2 text-sm font-medium text-slate-700">
                Table Introduction Text
                <input
                  type="text"
                  value={tagSettings.table_intro_text}
                  onChange={(event) =>
                    onFieldChange("table_intro_text", event.target.value)
                  }
                  placeholder="Here is a summary of the patient's exams..."
                  className="w-full rounded-xl border border-slate-300 bg-white/80 p-3 text-base shadow-inner focus:border-brand.indigo focus:outline-none"
                />
                <span className="text-xs text-slate-500">
                  Text displayed immediately before the appointment table.
                </span>
              </label>

              <label className="mt-4 space-y-2 text-sm font-medium text-slate-700">
                Personal Injury Text
                <textarea
                  value={tagSettings.personal_injury_text}
                  onChange={(event) =>
                    onFieldChange("personal_injury_text", event.target.value)
                  }
                  placeholder="If this is also a personal injury case:&#10;A report containing the findings..."
                  className="min-h-[120px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 font-mono text-sm shadow-inner focus:border-brand.indigo focus:outline-none"
                />
                <span className="text-xs text-slate-500">
                  HTML supported. Shown only when patient is flagged as personal injury case.
                </span>
              </label>

              <label className="mt-4 space-y-2 text-sm font-medium text-slate-700">
                Footer Text (after table)
                <textarea
                  value={tagSettings.footer_text}
                  onChange={(event) =>
                    onFieldChange("footer_text", event.target.value)
                  }
                  placeholder="{personal_injury_info}&#10;Access bills: <a href='{bills_link}'>Click Here</a>..."
                  className="min-h-[120px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 font-mono text-sm shadow-inner focus:border-brand.indigo focus:outline-none"
                />
                <span className="text-xs text-slate-500">
                  HTML and placeholders supported: {"{personal_injury_info}"}, {"{bills_link}"}, {"{reports_link}"}
                </span>
              </label>
            </div>
          </div>

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

          <div className="flex flex-wrap justify-end gap-3">
            <Button variant="ghost" onClick={onReset}>
              Reset Changes
            </Button>
            <Button onClick={onSave} className="bg-slate-900 text-white">
              Save Settings
            </Button>
          </div>
        </>
      )}
    </div>
  );
}

function StatusBanner({ status }: { status: StatusMessage }) {
  const styles: Record<StatusMessage["type"], string> = {
    success: "border-emerald-200 bg-emerald-50 text-emerald-700",
    error: "border-rose-200 bg-rose-50 text-rose-600",
    info: "border-slate-200 bg-slate-50 text-slate-700",
  };

  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${styles[status.type]}`}>
      {status.message}
    </div>
  );
}
