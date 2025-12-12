/**
 * useTagSettings hook - manages tag settings state and API calls
 */

import { useEffect, useState } from "react";
import { ApiError, TemplatesApi } from "@/lib/api";
import type { TagSettingsResponse } from "@/lib/types";
import { StatusMessage } from "../components/StatusBanner";
import {
  DEFAULT_TAG_SETTINGS,
  DEFAULT_CUSTOM_PLACEHOLDERS,
  DEFAULT_LIEN_TEMPLATES,
} from "../constants/template-config.constants";
import { getTagLabel } from "../utils/template-helpers";

export function normalizeCustomPlaceholdersFromSettings(
  settings: Record<string, any> = {}
): Record<string, string> {
  const customPlaceholders = {
    ...((settings.custom_placeholders as Record<string, string>) || {}),
  };

  if (settings.scheduling_phone) customPlaceholders.scheduling_phone = settings.scheduling_phone;
  if (settings.no_show_policy) customPlaceholders.no_show_policy = settings.no_show_policy;
  if (settings.bills_link) customPlaceholders.bills_link = settings.bills_link;
  if (settings.reports_link) customPlaceholders.reports_link = settings.reports_link;

  return Object.keys(customPlaceholders).length > 0
    ? customPlaceholders
    : { ...DEFAULT_CUSTOM_PLACEHOLDERS };
}

export function useTagSettings(selectedTag: string, currentUser: string) {
  const [tagSettings, setTagSettings] = useState(DEFAULT_TAG_SETTINGS);
  const [tagOriginal, setTagOriginal] = useState(DEFAULT_TAG_SETTINGS);
  const [tagMeta, setTagMeta] = useState<TagSettingsResponse | null>(null);
  const [tagStatus, setTagStatus] = useState<StatusMessage | null>(null);
  const [tagLoading, setTagLoading] = useState(false);

  const loadTagSettings = async (tagName: string) => {
    setTagLoading(true);
    setTagStatus(null);
    try {
      const response = await TemplatesApi.getTagSettings(tagName);
      const finalCustomPlaceholders = normalizeCustomPlaceholdersFromSettings(response.settings);

      const nextSettings = {
        // Custom placeholders (global, available across all autoresponds)
        custom_placeholders: finalCustomPlaceholders,
        // Unified template (for Apt status req)
        unified_template: response.settings.unified_template ?? "",
        // Lien templates (for ASL/PSL lien agents)
        lien_success_template: response.settings.lien_success_template ?? DEFAULT_LIEN_TEMPLATES.lien_success_template,
        lien_patient_not_found_template: response.settings.lien_patient_not_found_template ?? DEFAULT_LIEN_TEMPLATES.lien_patient_not_found_template,
        lien_reject_no_changes_template: response.settings.lien_reject_no_changes_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_no_changes_template,
        lien_reject_not_readable_template: response.settings.lien_reject_not_readable_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_not_readable_template,
        lien_reject_sig_not_valid_template: response.settings.lien_reject_sig_not_valid_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_sig_not_valid_template,
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

  const handleFieldChange = (key: keyof typeof DEFAULT_TAG_SETTINGS, value: string | Record<string, string>) => {
    setTagSettings((prev) => ({ ...prev, [key]: value }));
  };

  // Load settings when selectedTag changes
  useEffect(() => {
    void loadTagSettings(selectedTag);
  }, [selectedTag]);

  return {
    tagSettings,
    tagMeta,
    tagStatus,
    tagLoading,
    handleSaveTagSettings,
    handleResetTagSettings,
    handleFieldChange,
  };
}
