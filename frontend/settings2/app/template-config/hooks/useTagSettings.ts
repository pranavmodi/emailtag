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
  DEFAULT_APT_STATUS_TEMPLATES,
} from "../constants/template-config.constants";
import { getTagLabel } from "../utils/template-helpers";

/**
 * Extract custom placeholders from tag settings.
 *
 * Standard approach: All custom placeholders are stored in settings.custom_placeholders
 * No legacy field migration - custom_placeholders is the single source of truth.
 */
export function normalizeCustomPlaceholdersFromSettings(
  settings: Record<string, any> = {}
): Record<string, string> {
  const customPlaceholders = settings.custom_placeholders as Record<string, string> || {};

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

      const nextSettings = {
        // Apt status req templates (multi-scenario)
        apt_status_unified_template: response.settings.apt_status_unified_template ?? response.settings.unified_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_unified_template,
        apt_status_not_found_template: response.settings.apt_status_not_found_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_not_found_template,
        apt_status_db_error_template: response.settings.apt_status_db_error_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_db_error_template,
        apt_status_request_id_template: response.settings.apt_status_request_id_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_request_id_template,
        apt_status_request_id_escalate_template: response.settings.apt_status_request_id_escalate_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_request_id_escalate_template,
        apt_status_hipaa_template: response.settings.apt_status_hipaa_template ?? response.settings.hipaa_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_hipaa_template,
        apt_status_unauthorized_template: response.settings.apt_status_unauthorized_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_unauthorized_template,

        // Legacy aliases / workspace-level templates
        unified_template: response.settings.apt_status_unified_template ?? response.settings.unified_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_unified_template,
        hipaa_template: response.settings.hipaa_template ?? response.settings.apt_status_hipaa_template ?? DEFAULT_APT_STATUS_TEMPLATES.apt_status_hipaa_template,

        // Lien templates (multi-scenario tag)
        lien_success_template: response.settings.lien_success_template ?? DEFAULT_LIEN_TEMPLATES.lien_success_template,
        lien_patient_not_found_template: response.settings.lien_patient_not_found_template ?? DEFAULT_LIEN_TEMPLATES.lien_patient_not_found_template,
        lien_reject_no_changes_template: response.settings.lien_reject_no_changes_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_no_changes_template,
        lien_reject_not_readable_template: response.settings.lien_reject_not_readable_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_not_readable_template,
        lien_reject_sig_not_valid_template: response.settings.lien_reject_sig_not_valid_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_sig_not_valid_template,
        lien_reject_cover_letter_conditional_template: response.settings.lien_reject_cover_letter_conditional_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_cover_letter_conditional_template,
        lien_reject_email_conditional_template: response.settings.lien_reject_email_conditional_template ?? DEFAULT_LIEN_TEMPLATES.lien_reject_email_conditional_template,
        lien_multi_patient_wrapper_template: response.settings.lien_multi_patient_wrapper_template ?? DEFAULT_LIEN_TEMPLATES.lien_multi_patient_wrapper_template,
        lien_multi_patient_section_template: response.settings.lien_multi_patient_section_template ?? DEFAULT_LIEN_TEMPLATES.lien_multi_patient_section_template,

        // Bill Balance templates (multi-scenario tag)
        bill_balance_found_template: response.settings.bill_balance_found_template ?? "",
        bill_balance_not_found_template: response.settings.bill_balance_not_found_template ?? "",
        bill_balance_lien_reminder_template: response.settings.bill_balance_lien_reminder_template ?? "",
        bill_balance_no_data_template: response.settings.bill_balance_no_data_template ?? "",
        bill_balance_request_patient_id_template: response.settings.bill_balance_request_patient_id_template ?? "",
        bill_balance_escalation_template: response.settings.bill_balance_escalation_template ?? "",

        // Custom placeholders added for PlaceholderManager compatibility
        // (actual workspace placeholders loaded separately in page.tsx)
        custom_placeholders: DEFAULT_CUSTOM_PLACEHOLDERS,
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
