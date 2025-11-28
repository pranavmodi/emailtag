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

// Dummy data for preview
const DUMMY_TABLE_DATA = `<tr>
<td style="border: 1px solid black; padding: 8px;">PRE1234567</td>
<td style="border: 1px solid black; padding: 8px;">MRI Brain W/O Contrast</td>
<td style="border: 1px solid black; padding: 8px;">Scheduled</td>
<td style="border: 1px solid black; padding: 8px;">Date: Monday January 15th, 2024<br/><br/>Time: 2:30 PM</td>
<td style="border: 1px solid black; padding: 8px;">Precise Imaging - Main Office - 123 Medical Blvd, Los Angeles, CA 90001</td>
<td style="border: 1px solid black; padding: 8px;">Standard</td>
<td style="border: 1px solid black; padding: 8px;">No</td>
<td style="border: 1px solid black; padding: 8px;">No</td>
</tr>
<tr>
<td style="border: 1px solid black; padding: 8px;">PRE1234568</td>
<td style="border: 1px solid black; padding: 8px;">X-Ray Chest 2 Views</td>
<td style="border: 1px solid black; padding: 8px;">Completed</td>
<td style="border: 1px solid black; padding: 8px;">Date: Friday January 5th, 2024<br/><br/>Time: 10:00 AM</td>
<td style="border: 1px solid black; padding: 8px;">Precise Imaging - Downtown - 456 Health St, Los Angeles, CA 90012</td>
<td style="border: 1px solid black; padding: 8px;">N/A</td>
<td style="border: 1px solid black; padding: 8px;">Yes</td>
<td style="border: 1px solid black; padding: 8px;">Yes</td>
</tr>`;

const DEFAULT_UNIFIED_TEMPLATE = `Dear {first_name} {last_name},<br/>
In regards to patient ID (MRN): {patient_id_confirmed}<br/><br/>

<b>How to Schedule:</b><br/><br/>

<ul>
  <li>Schedule online 24/7 via the <a href="https://app.radflow360.com/patient-portal" target="_blank">patient portal</a></li>
  <li>Call <b>800-558-2223</b></li>
</ul><br/>

<b>Rescheduling / No Show Policy:</b><br/>
**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**<br/><br/>

Here is a summary of the patient's exams we currently have entered into our system:<br/>
{appointment_table}<br/>

{personal_injury_info}

<b>What You Can Access in the RadFlow 360 Portal</b><br/><br/>

<ul>
  <li>View all patient exams and status</li>
  <li>Reports & Documents</li>
  <li>View Images, Download, and Burn to CD</li>
  <li>Provide Case Updates</li>
  <li>Submit & Approve Bill Offers</li>
  <li>Pay online via credit card and ACH</li>
</ul><br/>

<a href="https://app.radflow360.com/patient-portal" target="_blank"><b>Login or Create Your Free Account Today</b></a>`;

// Default custom placeholders (pre-populated, user can edit/delete/add more)
const DEFAULT_CUSTOM_PLACEHOLDERS: Record<string, string> = {
  scheduling_phone: "800-558-2223",
  no_show_policy: "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**",
  bills_link: "https://app.radflow360.com/patient-portal",
  reports_link: "https://app.radflow360.com/patient-portal",
};

const DEFAULT_TAG_SETTINGS = {
  // Custom placeholders (global, available across all autoresponds)
  custom_placeholders: DEFAULT_CUSTOM_PLACEHOLDERS,
  // Unified template
  unified_template: DEFAULT_UNIFIED_TEMPLATE,
  // Legacy fields (for backward compatibility)
  scheduling_phone_number: "",
  portal_link_bills: "",
  portal_link_reports: "",
  intro_text: "",
  table_intro_text: "",
  personal_injury_text: "",
  footer_text: "",
};

const getTagLabel = (value: string) =>
  TAG_OPTIONS.find((option) => option.value === value)?.label ?? value;

// Generate preview HTML
const generatePreviewHtml = (settings: typeof DEFAULT_TAG_SETTINGS, showPersonalInjury: boolean = true): string => {
  const intro = settings.intro_text || DEFAULT_TAG_SETTINGS.intro_text || "";
  const tableIntro = settings.table_intro_text || DEFAULT_TAG_SETTINGS.table_intro_text || "";
  const personalInjuryText = settings.personal_injury_text || DEFAULT_TAG_SETTINGS.personal_injury_text || "";
  const footer = settings.footer_text || DEFAULT_TAG_SETTINGS.footer_text || "";

  // Get values from custom_placeholders or use defaults
  const schedulingPhone = settings.custom_placeholders?.scheduling_phone || settings.scheduling_phone_number || "800-558-2223";
  const noShowPolicy = settings.custom_placeholders?.no_show_policy || "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees.**";
  const billsLink = settings.custom_placeholders?.bills_link || settings.portal_link_bills || "https://example.com/portal/bills";
  const reportsLink = settings.custom_placeholders?.reports_link || settings.portal_link_reports || "https://example.com/portal/reports";

  // Dummy patient data for preview
  const dummyPatient = {
    firstName: "Jane",
    lastName: "Smith",
    dob: "05/12/1985",
    address: "456 Oak Avenue, Los Angeles, CA 90210",
    homePhone: "555-123-4567",
    cellPhone: "555-987-6543",
    patientId: "PRE1234567"
  };

  // Format intro text with placeholders (including patient demographics)
  let formattedIntro = intro
    .replace(/\{patient_id_confirmed\}/g, dummyPatient.patientId)
    .replace(/\{scheduling_phone\}/g, schedulingPhone)
    .replace(/\{no_show_policy\}/g, noShowPolicy)
    .replace(/\{first_name\}/g, dummyPatient.firstName)
    .replace(/\{last_name\}/g, dummyPatient.lastName)
    .replace(/\{dob\}/g, dummyPatient.dob)
    .replace(/\{address\}/g, dummyPatient.address)
    .replace(/\{home_phone\}/g, dummyPatient.homePhone)
    .replace(/\{cell_phone\}/g, dummyPatient.cellPhone);

  // Build table
  const tableHtml = `<table border="1" style="border-collapse: collapse; width: 100%;">
<thead>
<tr>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Study ID</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Exam Description</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Status</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Study Date/Time</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Location</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">MRI Type</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Images Available</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Report Available</th>
</tr>
</thead>
<tbody>${DUMMY_TABLE_DATA}</tbody>
</table>`;

  // Check if unified template exists (new approach)
  const unifiedTemplate = settings.unified_template;

  if (unifiedTemplate) {
    // NEW APPROACH: Use unified template with all placeholders
    const personalInjuryInfo = showPersonalInjury ? (settings.personal_injury_text || "Important Information regarding personal injury cases<br/>A report containing the findings of the exam will also be sent to the attorney.<br/>A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.<br/>Please make sure to submit a negotiation offer before sending the payment.<br/><br/>") : "";

    let formattedTemplate = unifiedTemplate
      .replace(/\{appointment_table\}/g, tableHtml)
      .replace(/\{personal_injury_info\}/g, personalInjuryInfo)
      .replace(/\{patient_id_confirmed\}/g, dummyPatient.patientId)
      .replace(/\{first_name\}/g, dummyPatient.firstName)
      .replace(/\{last_name\}/g, dummyPatient.lastName)
      .replace(/\{dob\}/g, dummyPatient.dob)
      .replace(/\{address\}/g, dummyPatient.address)
      .replace(/\{home_phone\}/g, dummyPatient.homePhone)
      .replace(/\{cell_phone\}/g, dummyPatient.cellPhone);

    // Replace all custom placeholders (includes scheduling_phone, no_show_policy, bills_link, reports_link, etc.)
    if (settings.custom_placeholders) {
      Object.entries(settings.custom_placeholders).forEach(([key, value]) => {
        const regex = new RegExp(`\\{${key}\\}`, 'g');
        formattedTemplate = formattedTemplate.replace(regex, value);
      });
    }

    return formattedTemplate;
  } else {
    // LEGACY APPROACH: Assemble from separate parts (backward compatibility)
    const personalInjuryInfo = showPersonalInjury ? personalInjuryText : "";
    let formattedFooter = footer
      .replace(/\{personal_injury_info\}/g, personalInjuryInfo)
      .replace(/\{bills_link\}/g, billsLink)
      .replace(/\{reports_link\}/g, reportsLink)
      .replace(/\{first_name\}/g, dummyPatient.firstName)
      .replace(/\{last_name\}/g, dummyPatient.lastName)
      .replace(/\{dob\}/g, dummyPatient.dob)
      .replace(/\{address\}/g, dummyPatient.address)
      .replace(/\{home_phone\}/g, dummyPatient.homePhone)
      .replace(/\{cell_phone\}/g, dummyPatient.cellPhone);

    return formattedIntro + tableIntro + tableHtml + formattedFooter;
  }
};

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
  const [showPreview, setShowPreview] = useState(true);
  const [showPersonalInjuryInPreview, setShowPersonalInjuryInPreview] = useState(true);

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

      // Merge custom placeholders with any legacy separate fields for backward compatibility
      const customPlaceholders = (response.settings.custom_placeholders as unknown as Record<string, string>) || {};

      // If old separate fields exist, merge them into custom_placeholders
      if (response.settings.scheduling_phone) customPlaceholders.scheduling_phone = response.settings.scheduling_phone;
      if (response.settings.no_show_policy) customPlaceholders.no_show_policy = response.settings.no_show_policy;
      if (response.settings.bills_link) customPlaceholders.bills_link = response.settings.bills_link;
      if (response.settings.reports_link) customPlaceholders.reports_link = response.settings.reports_link;

      // If custom_placeholders is empty, use defaults
      const finalCustomPlaceholders = Object.keys(customPlaceholders).length > 0
        ? customPlaceholders
        : DEFAULT_CUSTOM_PLACEHOLDERS;

      const nextSettings = {
        // Custom placeholders (global, available across all autoresponds)
        custom_placeholders: finalCustomPlaceholders,
        // Unified template
        unified_template: response.settings.unified_template ?? "",
        // Legacy fields (for backward compatibility)
        scheduling_phone_number: response.settings.scheduling_phone_number ?? "",
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
              showPreview={showPreview}
              setShowPreview={setShowPreview}
              showPersonalInjuryInPreview={showPersonalInjuryInPreview}
              setShowPersonalInjuryInPreview={setShowPersonalInjuryInPreview}
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
  onFieldChange: (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string | Record<string, string>) => void;
  tagMeta: TagSettingsResponse | null;
  tagStatus: StatusMessage | null;
  tagLoading: boolean;
  onSave: () => void;
  onReset: () => void;
  showPreview: boolean;
  setShowPreview: (show: boolean) => void;
  showPersonalInjuryInPreview: boolean;
  setShowPersonalInjuryInPreview: (show: boolean) => void;
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
  showPreview,
  setShowPreview,
  showPersonalInjuryInPreview,
  setShowPersonalInjuryInPreview,
}: TagSettingsFormProps) {
  const selectedTagLabel = getTagLabel(selectedTag);
  const previewHtml = generatePreviewHtml(tagSettings, showPersonalInjuryInPreview);

  // State for expandable custom placeholders section
  const [isPlaceholdersExpanded, setIsPlaceholdersExpanded] = useState(false);
  const [selectedPlaceholder, setSelectedPlaceholder] = useState<string>("");

  // Initialize selected placeholder when custom_placeholders change
  useEffect(() => {
    if (tagSettings.custom_placeholders && Object.keys(tagSettings.custom_placeholders).length > 0) {
      const firstKey = Object.keys(tagSettings.custom_placeholders)[0];
      if (!selectedPlaceholder || !(selectedPlaceholder in tagSettings.custom_placeholders)) {
        setSelectedPlaceholder(firstKey);
      }
    }
  }, [tagSettings.custom_placeholders]);

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
          {/* Placeholder Management Section */}
          <div className="group overflow-hidden rounded-2xl border border-amber-200 bg-gradient-to-br from-amber-50 via-orange-50 to-amber-50 shadow-sm transition-all duration-200 hover:shadow-md">
            <button
              onClick={() => setIsPlaceholdersExpanded(!isPlaceholdersExpanded)}
              className="w-full p-5 text-left transition-colors duration-200 hover:bg-amber-100/50"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-500 to-orange-500 text-white shadow-sm">
                    <span className="text-sm font-bold">{ }</span>
                  </div>
                  <div>
                    <h3 className="text-sm font-semibold text-slate-900">
                      Custom Placeholders
                    </h3>
                    <p className="text-xs text-slate-600">
                      {Object.keys(tagSettings.custom_placeholders || {}).length} placeholder{Object.keys(tagSettings.custom_placeholders || {}).length !== 1 ? 's' : ''} defined
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-amber-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm">
                    {Object.keys(tagSettings.custom_placeholders || {}).length}
                  </span>
                  <svg
                    className={`h-5 w-5 text-amber-700 transition-transform duration-300 ${isPlaceholdersExpanded ? 'rotate-180' : ''}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </div>
            </button>

            <div className={`transition-all duration-300 ease-in-out ${isPlaceholdersExpanded ? 'max-h-[800px] opacity-100' : 'max-h-0 opacity-0'}`}>
              <div className="border-t border-amber-200 bg-white/50 p-5">
                <p className="mb-4 text-xs text-slate-600">
                  Define custom placeholders available across all autorespond templates. Values are replaced when emails are sent.
                </p>

                {/* Placeholder Selector and Editor */}
                {tagSettings.custom_placeholders && Object.keys(tagSettings.custom_placeholders).length > 0 ? (
                  <div className="space-y-4">
                    {/* Dropdown Selector */}
                    <div className="space-y-2">
                      <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                        Select Placeholder
                      </label>
                      <select
                        value={selectedPlaceholder}
                        onChange={(e) => setSelectedPlaceholder(e.target.value)}
                        className="w-full rounded-xl border-2 border-amber-200 bg-white px-4 py-3 font-mono text-sm font-medium text-slate-800 shadow-sm transition-all focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
                      >
                        {Object.keys(tagSettings.custom_placeholders).map((key) => (
                          <option key={key} value={key}>
                            {`{${key}}`}
                          </option>
                        ))}
                      </select>
                    </div>

                    {/* Value Editor */}
                    {selectedPlaceholder && (
                      <div className="space-y-3 rounded-xl border-2 border-amber-200 bg-gradient-to-br from-white to-amber-50/30 p-4 shadow-sm">
                        <div className="flex items-center justify-between">
                          <label className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-amber-800">
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                            </svg>
                            Value for <code className="ml-1 rounded bg-amber-200 px-1.5 py-0.5 font-mono text-xs text-amber-900">{`{${selectedPlaceholder}}`}</code>
                          </label>
                          <button
                            onClick={() => {
                              const customPlaceholders = { ...tagSettings.custom_placeholders };
                              delete customPlaceholders[selectedPlaceholder];
                              onFieldChange("custom_placeholders", customPlaceholders);
                              const remaining = Object.keys(customPlaceholders);
                              setSelectedPlaceholder(remaining.length > 0 ? remaining[0] : "");
                            }}
                            className="flex items-center gap-1 rounded-lg bg-red-100 px-3 py-1.5 text-xs font-medium text-red-700 shadow-sm transition-all hover:bg-red-200 hover:shadow active:scale-95"
                          >
                            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Delete
                          </button>
                        </div>
                        <textarea
                          value={tagSettings.custom_placeholders[selectedPlaceholder] || ""}
                          onChange={(e) => {
                            const customPlaceholders = { ...tagSettings.custom_placeholders };
                            customPlaceholders[selectedPlaceholder] = e.target.value;
                            onFieldChange("custom_placeholders", customPlaceholders);
                          }}
                          placeholder={`Enter value for {${selectedPlaceholder}}`}
                          rows={7}
                          className="w-full rounded-lg border-2 border-amber-200 bg-white px-4 py-3 text-sm leading-relaxed text-slate-800 shadow-inner transition-all placeholder:text-slate-400 focus:border-amber-500 focus:outline-none focus:ring-2 focus:ring-amber-200"
                        />
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="rounded-xl border-2 border-dashed border-amber-300 bg-amber-50/50 p-8 text-center">
                    <svg className="mx-auto mb-3 h-12 w-12 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                    </svg>
                    <p className="text-sm font-medium text-slate-700">No placeholders yet</p>
                    <p className="mt-1 text-xs text-slate-500">Create your first custom placeholder below</p>
                  </div>
                )}

                {/* Add New Placeholder Button */}
                <button
                  onClick={() => {
                    const name = prompt("Enter placeholder name (without braces):");
                    if (name && /^[a-z_][a-z0-9_]*$/i.test(name)) {
                      const customPlaceholders = tagSettings.custom_placeholders || {};
                      onFieldChange("custom_placeholders", {
                        ...customPlaceholders,
                        [name]: ""
                      });
                      setSelectedPlaceholder(name);
                    } else if (name) {
                      alert("Invalid placeholder name. Use only letters, numbers, and underscores, starting with a letter.");
                    }
                  }}
                  className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border-2 border-dashed border-amber-400 bg-gradient-to-br from-amber-50 to-orange-50 px-4 py-3 text-sm font-semibold text-amber-700 shadow-sm transition-all hover:border-amber-500 hover:from-amber-100 hover:to-orange-100 hover:shadow active:scale-[0.98]"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                  </svg>
                  Add New Placeholder
                </button>

                {/* Save Buttons */}
                <div className="mt-6 flex justify-end gap-3 border-t-2 border-amber-200 pt-4">
                  <button
                    onClick={onReset}
                    className="flex items-center gap-2 rounded-xl border-2 border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 shadow-sm transition-all hover:border-slate-400 hover:bg-slate-50 hover:shadow active:scale-95"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Reset
                  </button>
                  <button
                    onClick={onSave}
                    className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 px-5 py-2.5 text-sm font-semibold text-white shadow-md transition-all hover:from-amber-700 hover:to-orange-700 hover:shadow-lg active:scale-95"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Save Placeholders
                  </button>
                </div>
              </div>
            </div>
          </div>

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
            <div className="rounded-2xl border border-indigo-200 bg-indigo-50/50 p-4">
              <h3 className="mb-3 text-sm font-semibold text-slate-900">
                📧 Complete Email Template
              </h3>
              <p className="mb-4 text-xs text-slate-600">
                Customize the complete autoresponse email template. Use {"{appointment_table}"} where you want the appointment information to appear.
              </p>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <label className="text-sm font-medium text-slate-700">
                    Email Template
                  </label>
                  <button
                    onClick={() => onFieldChange("unified_template", DEFAULT_UNIFIED_TEMPLATE)}
                    className="rounded-lg bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-200 hover:text-slate-900"
                  >
                    ↻ Restore to Default
                  </button>
                </div>
                <textarea
                  value={tagSettings.unified_template || ""}
                  onChange={(event) =>
                    onFieldChange("unified_template", event.target.value)
                  }
                  placeholder="Patient ID: {patient_id_confirmed}&#10;&#10;Dear {first_name} {last_name},&#10;&#10;Our phone: {scheduling_phone}&#10;{no_show_policy}&#10;&#10;Here are your appointments:&#10;{appointment_table}&#10;&#10;{personal_injury_info}&#10;&#10;Access bills: {bills_link}"
                  className="min-h-[400px] w-full rounded-xl border border-slate-300 bg-white/80 p-3 font-mono text-sm shadow-inner focus:border-brand.indigo focus:outline-none"
                />
                <span className="text-xs text-slate-500">
                  HTML and placeholders supported. Use {"{appointment_table}"} for the appointment table. See all available placeholders below.
                </span>
              </div>

              {/* Save Button for Template */}
              <div className="mt-4 flex justify-end gap-2 border-t border-indigo-300 pt-4">
                <button
                  onClick={onReset}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Reset
                </button>
                <button
                  onClick={onSave}
                  className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-800"
                >
                  Save Template
                </button>
              </div>
            </div>
          </div>

          {/* Placeholder Reference Card */}
          <div className="rounded-2xl border border-emerald-200 bg-gradient-to-br from-emerald-50 to-teal-50 p-5">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-900">
              <span className="text-lg">📋</span>
              Available Placeholders
              <span className="ml-auto rounded-full bg-emerald-600 px-2 py-0.5 text-xs text-white">
                Copy & Paste
              </span>
            </h3>
            <p className="mb-4 text-xs text-slate-600">
              Use these placeholders in any text field above. They will be automatically replaced with actual patient data when sending autoresponds.
            </p>

            <div className="space-y-3">
              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-emerald-700">
                  Patient Information
                </h4>
                <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{first_name}"}
                  </code>
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{last_name}"}
                  </code>
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{dob}"}
                  </code>
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{address}"}
                  </code>
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{home_phone}"}
                  </code>
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{cell_phone}"}
                  </code>
                  <code className="block rounded-lg border border-emerald-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-emerald-500 hover:shadow-md">
                    {"{patient_id_confirmed}"}
                  </code>
                </div>
              </div>

              <div>
                <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-blue-700">
                  Special Placeholders
                </h4>
                <div className="grid grid-cols-1 gap-2">
                  <code className="block rounded-lg border-2 border-blue-400 bg-blue-50 px-3 py-2 text-xs font-mono font-semibold text-blue-900 shadow-sm transition hover:border-blue-600 hover:shadow-md">
                    {"{appointment_table}"} - Complete appointment information table
                  </code>
                  <code className="block rounded-lg border border-blue-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-blue-500 hover:shadow-md">
                    {"{personal_injury_info}"} - Shown only for PI cases
                  </code>
                </div>
              </div>

              {/* Custom Placeholders Section - Show all custom placeholders */}
              {tagSettings.custom_placeholders && Object.keys(tagSettings.custom_placeholders).length > 0 && (
                <div>
                  <h4 className="mb-2 text-xs font-semibold uppercase tracking-wide text-amber-700">
                    Custom Placeholders
                  </h4>
                  <div className="grid grid-cols-2 gap-2 lg:grid-cols-3">
                    {Object.keys(tagSettings.custom_placeholders).map((key) => (
                      <code
                        key={key}
                        className="block rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-mono text-slate-800 shadow-sm transition hover:border-amber-500 hover:shadow-md"
                      >
                        {`{${key}}`}
                      </code>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50/50 p-3 text-xs text-amber-800">
              <span className="font-semibold">💡 Tip:</span> If a patient field is missing, it will display as &ldquo;Not Available&rdquo; in the email.
            </div>
          </div>

          {/* Preview Section */}
          <div className="rounded-2xl border border-purple-200 bg-gradient-to-br from-purple-50 to-indigo-50 p-4">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                👁️ Live Preview
                <span className="text-xs font-normal text-slate-500">
                  (using dummy patient data)
                </span>
              </h3>
              <div className="flex items-center gap-3">
                <label className="flex items-center gap-2 text-xs text-slate-600">
                  <input
                    type="checkbox"
                    checked={showPersonalInjuryInPreview}
                    onChange={(e) => setShowPersonalInjuryInPreview(e.target.checked)}
                    className="rounded border-slate-300"
                  />
                  Show Personal Injury Info
                </label>
                <button
                  onClick={() => setShowPreview(!showPreview)}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  {showPreview ? "Hide" : "Show"} Preview
                </button>
              </div>
            </div>

            {showPreview && (
              <div className="rounded-xl border border-slate-300 bg-white p-4 shadow-inner">
                <div
                  className="prose prose-sm max-w-none"
                  dangerouslySetInnerHTML={{ __html: previewHtml }}
                />
              </div>
            )}
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
