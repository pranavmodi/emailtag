import type {
  AITrainingConversationsResponse,
  AllTagsStatisticsResponse,
  ArchivedConversationsResponse,
  AuthCheckResponse,
  AutorespondSettingsResponse,
  ConversationReplayResponse,
  ConversationReplaySendResponse,
  EmailProcessingStatus,
  EvalClassificationEntry,
  EvalClassificationResponse,
  ExtractConversationResponse,
  GlobalAutorespondToggleResponse,
  MessageTemplateResponse,
  NoActionListResponse,
  NoActionListUpdateResponse,
  FirmLookupCreateRequest,
  FirmLookupCreateResponse,
  FirmLookupRequest,
  FirmLookupResponse,
  FrontConversationDetailResponse,
  FrontConversationListResponse,
  FrontInboxListResponse,
  FrontInboxExportStartResponse,
  FrontInboxExportStatus,
  FullEnrichmentStatusResponse,
  OutreachResponse,
  PeopleSearchResponse,
  PifInfoListResponse,
  PifInfoResponse,
  PipelineListResponse,
  PipelineRecord,
  AnalyticsSummary,
  ProcessDayResponse,
  RecentConversationsResponse,
  ResearchStartResponse,
  ResearchStatusResponse,
  TagSettingsResponse,
  TagSettingsListResponse,
  TagStatisticsResponse,
  TemplateAttachmentListResponse,
  TemplateAttachmentUploadResponse,
  ToggleAutorespondResponse,
  TestEmailScenariosResponse,
  SendTestEmailResponse,
  TestEmailConfigResponse,
  AutorespondEventListResponse,
  AutorespondEventSummary,
  BillOfferAgentLogListResponse,
  BillOfferCorrectionAuditListResponse,
  BillOfferIntake,
  BillOfferIntakeListResponse,
  BillOfferRunAgentResponse,
  BillOfferSettingsResponse,
  BillOfferTaggedEmailListResponse,
} from "./types";

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
    this.name = "ApiError";
  }
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8444";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    credentials: "include",
    headers: {
      Accept: "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      // Read as text first to avoid consuming the stream twice
      const text = await response.text();
      try {
        // Try to parse as JSON
        const body = JSON.parse(text);
        detail = body.detail || JSON.stringify(body);
      } catch {
        // If not JSON, use the raw text
        detail = text || response.statusText;
      }
    } catch (err) {
      // If we can't read the response at all, use statusText
      detail = response.statusText;
    }
    throw new ApiError(detail || `Request failed`, response.status);
  }

  if (response.status === 204) {
    return {} as T;
  }

  return (await response.json()) as T;
}

async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, { credentials: "include" });
  if (!response.ok) {
    throw new ApiError(`Export failed`, response.status);
  }
  const blob = await response.blob();
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const filename = match ? match[1] : fallbackName;
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

export const SettingsApi = {
  getAuthStatus: () => request<AuthCheckResponse>("/api/v1/auth/check"),
  logout: () => request("/api/v1/auth/logout", { method: "POST" }),
  getProcessingStatus: () =>
    request<EmailProcessingStatus>("/api/v1/settings/email-processing-status"),
  toggleProcessing: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<EmailProcessingStatus>("/api/v1/settings/email-processing-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
    }),
  getAutorespondSettings: () =>
    request<AutorespondSettingsResponse>("/api/v1/settings/autorespond-settings"),
  toggleAutorespond: (type: string, enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<ToggleAutorespondResponse>("/api/v1/settings/autorespond-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        autorespond_type: type,
        setting_value: enabled,
        updated_by: "Next Settings",
        expected_updated_at: expectedUpdatedAt ?? undefined,
      }),
    }),
  toggleGlobalAutorespond: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<GlobalAutorespondToggleResponse>(
      "/api/v1/settings/global-autorespond-toggle",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
      }
    ),
  getWorkspaceSettings: () =>
    request<{ enable_sender_verification: boolean; custom_placeholders: Record<string, any> }>(
      "/api/v1/settings/workspace-settings"
    ),
  toggleSenderVerification: (enabled: boolean) =>
    request<{ success: boolean; enable_sender_verification: boolean; message: string }>(
      `/api/v1/settings/workspace-settings/sender-verification?enabled=${enabled}&updated_by=Next Settings`,
      {
        method: "POST",
      }
    ),
  getSkipInternalDomainsStatus: () =>
    request<{
      skip_internal_domains: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/skip-internal-domains-status"),
  toggleSkipInternalDomains: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<{
      skip_internal_domains: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/skip-internal-domains-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
    }),
  getCredentialScreeningStatus: () =>
    request<{
      credential_screening_enabled: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/credential-screening-status"),
  toggleCredentialScreening: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<{
      credential_screening_enabled: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/credential-screening-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
    }),
  getLienTestModeStatus: () =>
    request<{
      lien_test_mode: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/lien-test-mode-status"),
  toggleLienTestMode: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<{
      lien_test_mode: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/lien-test-mode-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
    }),
  getLienTestUploads: () =>
    request<{
      conversations: Array<{
        conversation_id: string;
        file_count: number;
        files: string[];
        subject?: string;
        sender?: string;
        email_count?: number;
        latest_upload_time?: number;
        tags?: string[];
      }>;
    }>("/api/v1/settings/lien-test-uploads"),
  getLienTestUploadsByConversation: (conversationId: string) =>
    request<{
      conversation_id: string;
      files: Array<{
        filename: string;
        size: number;
        created: number;
      }>;
      tags?: string[];
    }>(`/api/v1/settings/lien-test-uploads/${encodeURIComponent(conversationId)}`),
  downloadLienTestFile: (conversationId: string, filename: string) =>
    `${API_BASE_URL}/api/v1/settings/lien-test-uploads/${encodeURIComponent(conversationId)}/${encodeURIComponent(filename)}`,
  getLienTestResponse: (conversationId: string) =>
    request<{
      conversation_id: string;
      hasResponse: boolean;
      message?: string;
      timestamp?: string;
      response_text?: string;
      tags_to_add?: string[];
      lien_type?: string;
      signature_type?: string;
      status?: string;
    }>(`/api/v1/settings/lien-test-uploads/${encodeURIComponent(conversationId)}/response`),
  clearAllLienTestUploads: () =>
    request<{
      success: boolean;
      message: string;
      deleted_conversations: number;
      deleted_files: number;
    }>("/api/v1/settings/lien-test-uploads", {
      method: "DELETE",
    }),
  // Bill Balance Test Mode APIs
  getBillBalanceTestModeStatus: () =>
    request<{
      bill_balance_test_mode: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/bill-balance-test-mode-status"),
  toggleBillBalanceTestMode: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<{
      bill_balance_test_mode: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/bill-balance-test-mode-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
    }),
  getBillBalanceTestOutputs: () =>
    request<{
      conversations: Array<{
        conversation_id: string;
        timestamp: number;
        has_response: boolean;
        subject: string | null;
        sender: string | null;
        patient_id?: string;
        response_type?: string;
      }>;
    }>("/api/v1/settings/bill-balance-test-outputs"),
  getBillBalanceTestResponse: (conversationId: string) =>
    request<{
      conversation_id: string;
      timestamp: string;
      response_text: string;
      patient_id?: string;
      response_type?: string;
      details?: Record<string, unknown>;
      status: string;
      bill_attachment?: string | null;
      attachments?: string[];
      responses?: Array<{
        conversation_id: string;
        timestamp: string;
        response_text: string;
        patient_id?: string;
        response_type?: string;
        details?: Record<string, unknown>;
        status: string;
        bill_attachment?: string | null;
        attachments?: string[];
        _filename?: string;
      }>;
      response_count?: number;
    }>(`/api/v1/settings/bill-balance-test-outputs/${encodeURIComponent(conversationId)}/response`),
  getBillBalanceAttachmentUrl: (conversationId: string, filename: string) =>
    `${API_BASE_URL}/api/v1/settings/bill-balance-test-outputs/${encodeURIComponent(conversationId)}/attachment/${encodeURIComponent(filename)}`,
  deleteBillBalanceTestOutput: (conversationId: string) =>
    request<{
      message: string;
    }>(`/api/v1/settings/bill-balance-test-outputs/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
    }),
  clearAllBillBalanceTestOutputs: () =>
    request<{
      message: string;
    }>("/api/v1/settings/bill-balance-test-outputs", {
      method: "DELETE",
    }),
  // Apt Status Test Mode APIs
  getAptStatusTestModeStatus: () =>
    request<{
      apt_status_test_mode: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/apt-status-test-mode-status"),
  toggleAptStatusTestMode: (enabled: boolean, expectedUpdatedAt?: string | null) =>
    request<{
      apt_status_test_mode: boolean;
      description: string;
      last_updated: string | null;
      updated_by: string | null;
    }>("/api/v1/settings/apt-status-test-mode-toggle", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ setting_value: enabled, updated_by: "Next Settings", expected_updated_at: expectedUpdatedAt ?? undefined }),
    }),
  getAptStatusTestOutputs: () =>
    request<{
      conversations: Array<{
        conversation_id: string;
        timestamp: number;
        has_response: boolean;
        subject: string | null;
        sender: string | null;
        patient_ids?: string[];
        response_count?: number;
      }>;
    }>("/api/v1/settings/apt-status-test-outputs"),
  getAptStatusTestResponse: (conversationId: string) =>
    request<{
      conversation_id: string;
      timestamp: string;
      response_text: string;
      patient_id?: string;
      response_type?: string;
      details?: Record<string, unknown>;
      status: string;
      responses?: Array<{
        conversation_id: string;
        timestamp: string;
        response_text: string;
        patient_id?: string;
        response_type?: string;
        details?: Record<string, unknown>;
        status: string;
        _filename?: string;
      }>;
      response_count?: number;
    }>(`/api/v1/settings/apt-status-test-outputs/${encodeURIComponent(conversationId)}/response`),
  deleteAptStatusTestOutput: (conversationId: string) =>
    request<{
      message: string;
    }>(`/api/v1/settings/apt-status-test-outputs/${encodeURIComponent(conversationId)}`, {
      method: "DELETE",
    }),
  clearAllAptStatusTestOutputs: () =>
    request<{
      message: string;
    }>("/api/v1/settings/apt-status-test-outputs", {
      method: "DELETE",
    }),
  // No Action List APIs
  getNoActionList: () =>
    request<NoActionListResponse>("/api/v1/settings/workspace-settings/no-action-list"),
  addNoActionItem: (item: string) =>
    request<NoActionListUpdateResponse>(
      `/api/v1/settings/workspace-settings/no-action-list?item=${encodeURIComponent(item)}&updated_by=Next Settings`,
      { method: "POST" }
    ),
  removeNoActionItem: (item: string) =>
    request<NoActionListUpdateResponse>(
      `/api/v1/settings/workspace-settings/no-action-list/${encodeURIComponent(item)}?updated_by=Next Settings`,
      { method: "DELETE" }
    ),
  // Test Email APIs
  getTestEmailScenarios: () =>
    request<TestEmailScenariosResponse>("/api/v1/settings/test-email-scenarios"),
  getTestEmailConfig: () =>
    request<TestEmailConfigResponse>("/api/v1/settings/test-email-config"),
  sendTestEmails: (scenarioKeys: string[], recipientEmail?: string) =>
    request<SendTestEmailResponse>("/api/v1/settings/test-email-scenarios/send", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        scenario_keys: scenarioKeys,
        recipient_email: recipientEmail,
      }),
    }),
};

export const BillOffersApi = {
  getSettings: () =>
    request<BillOfferSettingsResponse>("/api/v1/bill-offers/settings"),
  setReviewRequired: (enabled: boolean) =>
    request<BillOfferSettingsResponse>("/api/v1/bill-offers/settings/review-required", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled, reviewed_by: "Settings2" }),
    }),
  listTaggedEmails: (params?: { skip?: number; limit?: number; search?: string; status?: string }) => {
    const search = new URLSearchParams();
    if (params?.skip !== undefined) search.set("skip", String(params.skip));
    if (params?.limit !== undefined) search.set("limit", String(params.limit));
    if (params?.search) search.set("search", params.search);
    if (params?.status) search.set("status", params.status);
    const query = search.toString();
    return request<BillOfferTaggedEmailListResponse>(
      `/api/v1/bill-offers/tagged-emails${query ? `?${query}` : ""}`
    );
  },
  listIntakes: (params?: { status?: string; skip?: number; limit?: number }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.skip !== undefined) search.set("skip", String(params.skip));
    if (params?.limit !== undefined) search.set("limit", String(params.limit));
    const query = search.toString();
    return request<BillOfferIntakeListResponse>(
      `/api/v1/bill-offers${query ? `?${query}` : ""}`
    );
  },
  getIntake: (id: string) =>
    request<BillOfferIntake>(`/api/v1/bill-offers/${encodeURIComponent(id)}`),
  updateIntake: (
    id: string,
    payload: {
      corrected_facts?: Record<string, any>;
      patient_id?: string | null;
      patient_match?: Record<string, any> | null;
      reviewed_by?: string;
    }
  ) =>
    request<BillOfferIntake>(`/api/v1/bill-offers/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        corrected_facts: payload.corrected_facts ?? {},
        patient_id: payload.patient_id,
        patient_match: payload.patient_match,
        reviewed_by: payload.reviewed_by ?? "Settings2",
      }),
    }),
  rerunCheck: (id: string) =>
    request<BillOfferIntake>(`/api/v1/bill-offers/${encodeURIComponent(id)}/rerun-check`, {
      method: "POST",
    }),
  runAgent: (conversationId: string) =>
    request<BillOfferRunAgentResponse>(
      `/api/v1/bill-offers/conversations/${encodeURIComponent(conversationId)}/run-agent`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ reviewed_by: "Settings2", send_reply: false }),
      }
    ),
  sendReply: (id: string) =>
    request<BillOfferIntake>(`/api/v1/bill-offers/${encodeURIComponent(id)}/send-reply`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed_by: "Settings2" }),
    }),
  markManualReview: (id: string, reason?: string) =>
    request<BillOfferIntake>(`/api/v1/bill-offers/${encodeURIComponent(id)}/manual-review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed_by: "Settings2", reason }),
    }),
  listLogs: (conversationId: string) =>
    request<BillOfferAgentLogListResponse>(
      `/api/v1/bill-offers/conversations/${encodeURIComponent(conversationId)}/logs`
    ),
  listCorrectionAudits: (conversationId: string) =>
    request<BillOfferCorrectionAuditListResponse>(
      `/api/v1/bill-offers/conversations/${encodeURIComponent(conversationId)}/corrections`
    ),
};

export const TagsApi = {
  getAITrainingConversations: (params: {
    page?: number;
    pageSize?: number;
    days?: number;
    filterTags?: string[];
  }) => {
    const searchParams = new URLSearchParams();
    if (params.page) searchParams.set("page", String(params.page));
    if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
    if (params.days) searchParams.set("days", String(params.days));
    if (params.filterTags && params.filterTags.length > 0) {
      searchParams.set("filter_tags", params.filterTags.join(","));
    }
    return request<AITrainingConversationsResponse>(
      `/api/v1/tags/ai-training-conversations?${searchParams.toString()}`
    );
  },
  getTagStatistics: (tagName: string, date: string) =>
    request<TagStatisticsResponse>(
      `/api/v1/tags/tag-statistics?${new URLSearchParams({
        tag_name: tagName,
        target_date: date,
      }).toString()}`
    ),
  getAllTagsStatistics: (date: string, hour?: number) =>
    request<AllTagsStatisticsResponse>(
      `/api/v1/tags/all-tags-statistics?${new URLSearchParams({
        target_date: date,
        ...(hour !== undefined ? { hour: String(hour) } : {}),
      }).toString()}`
    ),
  getArchivedConversations: (date: string, hour?: number) =>
    request<ArchivedConversationsResponse>(
      `/api/v1/tags/archived-conversations?${new URLSearchParams({
        target_date: date,
        ...(hour !== undefined ? { hour: String(hour) } : {}),
      }).toString()}`
    ),
  evalClassification: (params: { conversationId?: string; date?: string }) => {
    const search = new URLSearchParams();
    if (params.conversationId) {
      search.set("conversation_id", params.conversationId);
    }
    if (params.date) {
      search.set("target_date", params.date);
    }
    return request<EvalClassificationResponse>(
      `/api/v1/tags/eval-classification?${search.toString()}`,
      { method: "POST" }
    );
  },
  getEvalStatus: (taskId: string) =>
    request<{
      task_id: string;
      status: string;
      result?: EvalClassificationEntry;
      error?: string;
      message: string;
    }>(`/api/v1/tags/eval-status/${taskId}`),
  getAnalysisStatus: (taskId: string) =>
    request<{
      task_id: string;
      status: string;
      stage?: string;
      message: string;
      progress?: number;
      total?: number;
      current?: number;
      result?: AllTagsStatisticsResponse;
      error?: string;
    }>(`/api/v1/tags/analysis-status/${taskId}`),
};

type TemplateSavePayload = {
  template_name: string;
  template_body: string;
  description?: string;
  updated_by?: string;
};

type TagSettingsUpdatePayload = {
  settings: Record<string, string | Record<string, string>>;
  updated_by?: string;
};

export const TemplatesApi = {
  getTemplate: (key: string) =>
    request<MessageTemplateResponse>(`/api/v1/templates/templates/${encodeURIComponent(key)}`),
  createTemplate: (key: string, payload: TemplateSavePayload) =>
    request<MessageTemplateResponse>("/api/v1/templates/templates", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ template_key: key, ...payload }),
    }),
  updateTemplate: (key: string, payload: TemplateSavePayload) =>
    request<MessageTemplateResponse>(`/api/v1/templates/templates/${encodeURIComponent(key)}`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
  getAllTagSettings: () =>
    request<TagSettingsListResponse>("/api/v1/templates/tag-settings"),
  getTagSettings: (tagName: string) =>
    request<TagSettingsResponse>(
      `/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}`
    ),
  updateTagSettings: (tagName: string, payload: TagSettingsUpdatePayload) =>
    request<TagSettingsResponse>(
      `/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}`,
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      }
    ),
  createTagSettings: (tagName: string, payload: TagSettingsUpdatePayload) =>
    request<TagSettingsResponse>("/api/v1/templates/tag-settings", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ tag_name: tagName, ...payload }),
    }),
  generateHtml: (naturalText: string, placeholders?: string[]) =>
    request<{ html: string; placeholders_used: string[] }>(
      "/api/v1/templates/generate-html",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          natural_text: naturalText,
          available_placeholders: placeholders || [
            "{patient_id_confirmed}",
            "{scheduling_phone}",
            "{no_show_policy}",
            "{personal_injury_info}",
            "{bills_link}",
            "{reports_link}",
          ],
        }),
      }
    ),

  // Template Attachments
  getTagAttachments: (tagName: string, templateKey?: string) => {
    const params = new URLSearchParams();
    if (templateKey) {
      params.set("template_key", templateKey);
    }
    const queryString = params.toString();
    return request<TemplateAttachmentListResponse>(
      `/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}/attachments${queryString ? `?${queryString}` : ""}`
    );
  },

  uploadTagAttachment: async (
    tagName: string,
    file: File,
    options?: {
      templateKey?: string;
      description?: string;
      uploadedBy?: string;
    }
  ): Promise<TemplateAttachmentUploadResponse> => {
    const formData = new FormData();
    formData.append("file", file);
    if (options?.templateKey) {
      formData.append("template_key", options.templateKey);
    }
    if (options?.description) {
      formData.append("description", options.description);
    }
    if (options?.uploadedBy) {
      formData.append("uploaded_by", options.uploadedBy);
    }

    const response = await fetch(
      `${API_BASE_URL}/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}/attachments`,
      {
        method: "POST",
        credentials: "include",
        body: formData,
      }
    );

    if (!response.ok) {
      let detail = response.statusText;
      try {
        const text = await response.text();
        try {
          const body = JSON.parse(text);
          detail = body.detail || JSON.stringify(body);
        } catch {
          detail = text || response.statusText;
        }
      } catch {
        detail = response.statusText;
      }
      throw new ApiError(detail || "Upload failed", response.status);
    }

    return (await response.json()) as TemplateAttachmentUploadResponse;
  },

  deleteTagAttachment: (tagName: string, attachmentId: string) =>
    request<{ message: string }>(
      `/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}/attachments/${encodeURIComponent(attachmentId)}`,
      { method: "DELETE" }
    ),

  getAttachmentDownloadUrl: (tagName: string, attachmentId: string) =>
    `${API_BASE_URL}/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}/attachments/${encodeURIComponent(attachmentId)}/download`,

  getAttachmentViewUrl: (tagName: string, attachmentId: string) =>
    `${API_BASE_URL}/api/v1/templates/tag-settings/${encodeURIComponent(tagName)}/attachments/${encodeURIComponent(attachmentId)}/view`,

  previewTable: (patientId: string, tableType: string, signatureType?: string) => {
    const params = new URLSearchParams({
      patient_id: patientId,
      table_type: tableType,
    });
    if (signatureType) {
      params.set("signature_type", signatureType);
    }
    return request<{ html: string; table_type: string; patient_id: string }>(
      `/api/v1/templates/preview-table?${params.toString()}`
    );
  },
};

type ConversationReplaySendPayload = {
  conversation_id: string;
  message_id: string;
  recipient_email?: string;
};

export const ConversationReplayApi = {
  getConversation: (conversationId: string) =>
    request<ConversationReplayResponse>(
      `/api/v1/conversation-replay/${encodeURIComponent(conversationId)}`
    ),
  sendMessage: (payload: ConversationReplaySendPayload) =>
    request<ConversationReplaySendResponse>("/api/v1/conversation-replay/send", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    }),
};

export type ReprocessResponse = {
  status: "queued" | "created_but_not_queued";
  email_id: string;
  conversation_id: string;
  sender?: string;
  subject?: string;
  reason?: string;
};

export const ReprocessApi = {
  reprocessConversation: (conversationId: string) =>
    request<ReprocessResponse>(
      `/api/v1/webhooks/reprocess/${encodeURIComponent(conversationId)}`,
      { method: "POST" }
    ),
};

export type FullTracesResponse = {
  conversation_id: string;
  traces: import("./types").ClassificationTrace[];
  total_traces: number;
  document_processing_count: number;
  lien_validation_count: number;
  archival_count: number;
  classification_count: number;
  total_duration_ms: number;
  total_tokens: number;
};

export type LogEntry = {
  timestamp: string;
  level: string;
  module: string;
  func_name: string;
  line_no: number;
  message: string;
  extra: Record<string, unknown>;
};

export type ConversationLogsResponse = {
  conversation_id: string;
  email_id: string | null;
  log_entries: LogEntry[];
  total_entries: number;
  filtered_entries: number;
  returned_entries: number;
  error_count: number;
  warning_count: number;
  first_log_at: string | null;
  last_log_at: string | null;
};

export const ClassificationTracesApi = {
  getRecentConversations: (limit: number = 50) =>
    request<RecentConversationsResponse>(
      `/admin/classification-traces/api/recent-conversations?limit=${limit}`
    ),
  getFullTraces: (conversationId: string) =>
    request<FullTracesResponse>(
      `/admin/classification-traces/api/full?conversation_id=${encodeURIComponent(conversationId)}`
    ),
  summarize: (conversationId: string) =>
    request<{ conversation_id: string; summary: string }>(
      `/admin/classification-traces/api/summarize?conversation_id=${encodeURIComponent(conversationId)}`,
      { method: "POST" }
    ),
  getLogs: (
    conversationId: string,
    level?: string,
    search?: string,
    limit: number = 500
  ) => {
    const params = new URLSearchParams();
    params.set("conversation_id", conversationId);
    if (level) params.set("level", level);
    if (search) params.set("search", search);
    params.set("limit", String(limit));
    return request<ConversationLogsResponse>(
      `/admin/classification-traces/api/logs?${params.toString()}`
    );
  },
};

export const PifApi = {
  list: (params: {
    search?: string;
    page?: number;
    pageSize?: number;
    sortBy?: string;
    entityType?: string;
    websitePresence?: string;
    researchPresence?: string;
    staffPresence?: string;
    behaviorPresence?: string;
    icpPresence?: string;
    vendorPresence?: string;
    firstContactPresence?: string;
    activeOnly?: boolean;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.search) searchParams.set("search", params.search);
    if (params.page) searchParams.set("page", String(params.page));
    if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
    if (params.sortBy) searchParams.set("sort_by", params.sortBy);
    if (params.entityType) searchParams.set("entity_type", params.entityType);
    if (params.websitePresence) searchParams.set("website_presence", params.websitePresence);
    if (params.researchPresence) searchParams.set("research_presence", params.researchPresence);
    if (params.staffPresence) searchParams.set("staff_presence", params.staffPresence);
    if (params.behaviorPresence) searchParams.set("behavior_presence", params.behaviorPresence);
    if (params.icpPresence) searchParams.set("icp_presence", params.icpPresence);
    if (params.vendorPresence) searchParams.set("vendor_presence", params.vendorPresence);
    if (params.firstContactPresence) searchParams.set("first_contact_presence", params.firstContactPresence);
    if (params.activeOnly !== undefined) searchParams.set("active_only", String(params.activeOnly));
    return request<PifInfoListResponse>(
      `/api/v1/pif-info/?${searchParams.toString()}`
    );
  },
  searchPeople: (params: {
    title?: string;
    name?: string;
    roleCategory?: string;
    source?: string;
    page?: number;
    pageSize?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.title) searchParams.set("title", params.title);
    if (params.name) searchParams.set("name", params.name);
    if (params.roleCategory) searchParams.set("role_category", params.roleCategory);
    if (params.source) searchParams.set("source", params.source);
    if (params.page) searchParams.set("page", String(params.page));
    if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
    return request<PeopleSearchResponse>(
      `/api/v1/pif-info/people?${searchParams.toString()}`
    );
  },
  get: (pifId: string) =>
    request<PifInfoResponse>(`/api/v1/pif-info/${encodeURIComponent(pifId)}`),
  delete: (pifId: string) =>
    request<{ status: string; message: string }>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}`,
      { method: "DELETE" }
    ),
  processDay: (targetDate: string) =>
    request<ProcessDayResponse>("/api/v1/pif-info/process-day", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ target_date: targetDate }),
    }),
  extractConversation: (conversationId: string) =>
    request<ExtractConversationResponse>(
      `/api/v1/pif-info/extract-conversation/${encodeURIComponent(conversationId)}`,
      { method: "POST" }
    ),
  getConversationsForDate: (dateStr: string) =>
    request<string[]>(`/api/v1/pif-info/conversations/${encodeURIComponent(dateStr)}`),
  startResearch: (pifId: string) =>
    request<ResearchStartResponse>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/research`,
      { method: "POST" }
    ),
  getResearchStatus: (taskId: string) =>
    request<ResearchStatusResponse>(
      `/api/v1/pif-info/research-status/${encodeURIComponent(taskId)}`
    ),
  startStaffResearch: (pifId: string) =>
    request<ResearchStartResponse>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/research-staff`,
      { method: "POST" }
    ),
  detectVendors: (pifId: string) =>
    request<ResearchStartResponse>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/detect-vendors`,
      { method: "POST" }
    ),
  exportAll: (format: "json" | "csv", includeMerged = false) =>
    downloadFile(
      `/api/v1/pif-info/export?format=${format}&include_merged=${includeMerged}`,
      `firms-export.${format}`
    ),
  exportFirm: (pifId: string, format: "json" | "csv") =>
    downloadFile(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/export?format=${format}`,
      `firm.${format}`
    ),
  enrichAll: (pifId: string) =>
    request<ResearchStartResponse>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/enrich-all`,
      { method: "POST" }
    ),
  getEnrichmentStatus: (taskId: string) =>
    request<FullEnrichmentStatusResponse>(
      `/api/v1/pif-info/enrich-all/status/${encodeURIComponent(taskId)}`
    ),
  generateOutreach: (pifId: string, caseStudyUrl: string, clientDescription: string) =>
    request<OutreachResponse>(`/api/v1/pif-info/${encodeURIComponent(pifId)}/generate-outreach`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ case_study_url: caseStudyUrl, client_description: clientDescription }),
    }),
  firmLookup: (params: FirmLookupRequest) =>
    request<FirmLookupResponse>("/api/v1/pif-info/firm-lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),
  firmLookupCreate: (params: FirmLookupCreateRequest) =>
    request<FirmLookupCreateResponse>("/api/v1/pif-info/firm-lookup/create", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params),
    }),
  analyzeBehavior: (pifId: string) =>
    request<{ pif_id: string; firm_name: string; task_id: string; status: string; message: string }>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/analyze-behavior`,
      { method: "POST" }
    ),
  analyzeLeadershipEmails: (pifId: string) =>
    request<{ pif_id: string; firm_name: string; task_id: string; status: string; message: string }>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/analyze-leadership-emails`,
      { method: "POST" }
    ),
  analyzeBehaviorBatch: () =>
    request<{ task_id: string; message: string; total: number | null }>(
      "/api/v1/pif-info/analyze-behavior/batch",
      { method: "POST" }
    ),
  score: (pifId: string) =>
    request<{ pif_id: string; firm_name: string; icp_score: number; icp_tier: string; score_breakdown: Record<string, unknown> }>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/score`,
      { method: "POST" }
    ),
  scoreBatch: () =>
    request<{ task_id: string; message: string; total: number | null }>(
      "/api/v1/pif-info/score/batch",
      { method: "POST" }
    ),
  getAnalyticsSummary: () =>
    request<AnalyticsSummary>("/api/v1/pif-info/analytics/summary"),
  listAutorespondEvents: (params: {
    agentType?: string;
    search?: string;
    dateFrom?: string;
    dateTo?: string;
    testMode?: boolean;
    page?: number;
    pageSize?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.agentType) searchParams.set("agent_type", params.agentType);
    if (params.search) searchParams.set("search", params.search);
    if (params.dateFrom) searchParams.set("date_from", params.dateFrom);
    if (params.dateTo) searchParams.set("date_to", params.dateTo);
    if (params.testMode !== undefined) searchParams.set("test_mode", String(params.testMode));
    if (params.page) searchParams.set("page", String(params.page));
    if (params.pageSize) searchParams.set("page_size", String(params.pageSize));
    return request<AutorespondEventListResponse>(
      `/api/v1/pif-info/autorespond-events?${searchParams.toString()}`
    );
  },
  getAutorespondEventsSummary: () =>
    request<AutorespondEventSummary>("/api/v1/pif-info/autorespond-events/summary"),
  listFirmAutorespondEvents: (pifId: string, params?: { page?: number; pageSize?: number }) => {
    const searchParams = new URLSearchParams();
    if (params?.page) searchParams.set("page", String(params.page));
    if (params?.pageSize) searchParams.set("page_size", String(params.pageSize));
    return request<AutorespondEventListResponse>(
      `/api/v1/pif-info/${encodeURIComponent(pifId)}/autorespond-events?${searchParams.toString()}`
    );
  },
};

export const PifInboxApi = {
  listInboxes: () => request<FrontInboxListResponse>("/api/v1/pif-inbox/inboxes"),
  listConversations: (inboxId: string, params?: { limit?: number; cursor?: string | null }) => {
    const searchParams = new URLSearchParams();
    searchParams.set("limit", String(params?.limit ?? 15));
    if (params?.cursor) searchParams.set("cursor", params.cursor);
    return request<FrontConversationListResponse>(
      `/api/v1/pif-inbox/inboxes/${encodeURIComponent(inboxId)}/conversations?${searchParams.toString()}`
    );
  },
  getConversation: (conversationId: string) =>
    request<FrontConversationDetailResponse>(
      `/api/v1/pif-inbox/conversations/${encodeURIComponent(conversationId)}`
    ),
  getAttachmentDownloadUrl: (messageId: string, attachmentId: string) =>
    `${API_BASE_URL}/api/v1/pif-inbox/messages/${encodeURIComponent(messageId)}/attachments/${encodeURIComponent(attachmentId)}/download`,
  startExport: (params: { inboxId: string; inboxName?: string | null; dateFrom: string; dateTo: string }) =>
    request<FrontInboxExportStartResponse>("/api/v1/pif-inbox/exports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        inbox_id: params.inboxId,
        inbox_name: params.inboxName,
        date_from: params.dateFrom,
        date_to: params.dateTo,
      }),
    }),
  getExportStatus: (exportId: string) =>
    request<FrontInboxExportStatus>(`/api/v1/pif-inbox/exports/${encodeURIComponent(exportId)}`),
  getExportDownloadUrl: (exportId: string) =>
    `${API_BASE_URL}/api/v1/pif-inbox/exports/${encodeURIComponent(exportId)}/download`,
};

export const PifStatsAuthApi = {
  login: (username: string, password: string) =>
    request<{ authenticated: boolean; username?: string }>("/api/v1/pifstats-auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    }),
  logout: () =>
    request<{ authenticated: boolean }>("/api/v1/pifstats-auth/logout", {
      method: "POST",
    }),
  check: () => request<{ authenticated: boolean; username?: string }>("/api/v1/pifstats-auth/check"),
  getEnv: () => request<{ path: string; content: string }>("/api/v1/pifstats-auth/env"),
};

export const PipelineApi = {
  create: (data: {
    pif_id: string;
    contact_name?: string | null;
    contact_linkedin?: string | null;
    contact_email?: string | null;
    outreach_type: string;
    sender_persona?: string | null;
    status?: string;
    message_variant?: string | null;
    notes?: string | null;
  }) =>
    request<PipelineRecord>("/api/v1/pif-pipeline/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  listByFirm: (pifId: string) =>
    request<PipelineListResponse>(`/api/v1/pif-pipeline/by-firm/${encodeURIComponent(pifId)}`),
  get: (recordId: string) =>
    request<PipelineRecord>(`/api/v1/pif-pipeline/${encodeURIComponent(recordId)}`),
  update: (recordId: string, data: Partial<{
    contact_name: string | null;
    contact_linkedin: string | null;
    contact_email: string | null;
    outreach_type: string;
    sender_persona: string | null;
    status: string;
    message_variant: string | null;
    sent_at: string | null;
    replied_at: string | null;
    notes: string | null;
  }>) =>
    request<PipelineRecord>(`/api/v1/pif-pipeline/${encodeURIComponent(recordId)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  delete: (recordId: string) =>
    request<{ status: string; message: string }>(
      `/api/v1/pif-pipeline/${encodeURIComponent(recordId)}`,
      { method: "DELETE" }
    ),
};

// Usage tracking types
export type UsageEventCreate = {
  event_type: string;
  event_name: string;
  page_path?: string;
  component?: string;
  details?: Record<string, unknown>;
  session_id?: string;
  duration_ms?: number;
};

export type UsageEventResponse = {
  id: string;
  user_id: string;
  username: string;
  event_type: string;
  event_name: string;
  page_path?: string;
  component?: string;
  details?: Record<string, unknown>;
  ip_address?: string;
  user_agent?: string;
  session_id?: string;
  duration_ms?: number;
  created_at: string;
};

export type UsageStatsResponse = {
  total_events: number;
  total_page_views: number;
  total_actions: number;
  total_sessions: number;
  unique_pages_visited: number;
  events_today: number;
  events_this_week: number;
  events_this_month: number;
  page_view_counts: Record<string, number>;
  most_visited_pages: Array<{ page: string; count: number; last_visit: string | null }>;
  action_counts: Record<string, number>;
  most_common_actions: Array<{ action: string; count: number; last_performed: string | null }>;
  total_time_spent_ms: number;
  average_session_duration_ms: number;
  time_spent_per_page: Record<string, number>;
  hourly_activity: Record<string, number>;
  daily_activity: Record<string, number>;
  sessions: Array<{
    session_id: string;
    start: string | null;
    end: string | null;
    events_count: number;
    pages_visited: number;
  }>;
  recent_events: UsageEventResponse[];
};

// Inbox audit types
export type InboxAuditRunResponse = {
  id: string;
  inbox_id: string;
  inbox_name: string | null;
  inbox_address: string | null;
  run_at: string;
  lookback_start: string;
  lookback_end: string;
  total_received: number;
  total_processed: number;
  total_missed: number;
  status: string;
  error_message: string | null;
};

export type InboxAuditMissResponse = {
  id: string;
  audit_run_id: string;
  conversation_id: string;
  front_url: string | null;
  inbox_id: string;
  inbox_name: string | null;
  state: string;
  reason: string | null;
  subject: string | null;
  detected_at: string;
  reviewed: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  notes: string | null;
};

export type InboxAuditSummary = {
  last_run_at: string | null;
  last_run_status: string | null;
  open_misses: number;
  misses_by_day: Array<{ date: string; count: number }>;
  misses_by_inbox: Array<{ inbox_id: string; inbox_name: string | null; count: number }>;
  misses_by_state: Array<{ state: string; count: number }>;
};

export type InboxAuditQueueResponse = {
  status: string;
  queued_count: number;
  task_ids: string[];
  conversation_ids: string[];
  message: string;
};

export type InboxAuditQueueStatusTask = {
  task_id: string;
  conversation_id: string;
};

export type InboxAuditQueueStatusItem = InboxAuditQueueStatusTask & {
  state: string;
  status: "pending" | "processed" | "failed" | string;
  error_message?: string | null;
};

export type InboxAuditQueueStatusResponse = {
  total_queued: number;
  processed: number;
  failed: number;
  pending: number;
  failed_conversation_ids: string[];
  items: InboxAuditQueueStatusItem[];
};

export const InboxAuditApi = {
  getSummary: (days = 7) =>
    request<InboxAuditSummary>(`/api/v1/inbox-audit/summary?days=${days}`),
  listRuns: (params?: { days?: number; inboxId?: string }) => {
    const sp = new URLSearchParams();
    if (params?.days) sp.set("days", String(params.days));
    if (params?.inboxId) sp.set("inbox_id", params.inboxId);
    const qs = sp.toString();
    return request<{ items: InboxAuditRunResponse[]; total: number }>(
      `/api/v1/inbox-audit/runs${qs ? `?${qs}` : ""}`
    );
  },
  listMisses: (params?: {
    reviewed?: boolean;
    state?: string;
    inboxId?: string;
    days?: number;
  }) => {
    const sp = new URLSearchParams();
    if (params?.reviewed !== undefined) sp.set("reviewed", String(params.reviewed));
    if (params?.state) sp.set("state", params.state);
    if (params?.inboxId) sp.set("inbox_id", params.inboxId);
    if (params?.days) sp.set("days", String(params.days));
    const qs = sp.toString();
    return request<{ items: InboxAuditMissResponse[]; total: number }>(
      `/api/v1/inbox-audit/misses${qs ? `?${qs}` : ""}`
    );
  },
  reviewMiss: (missId: string, payload: { reviewed_by?: string; notes?: string }) =>
    request<InboxAuditMissResponse>(
      `/api/v1/inbox-audit/misses/${encodeURIComponent(missId)}/review`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      }
    ),
  triggerRun: (lookbackHours?: number) =>
    request<{ status: string; task_id: string | null; message: string }>(
      `/api/v1/inbox-audit/run${lookbackHours ? `?lookback_hours=${lookbackHours}` : ""}`,
      { method: "POST" }
    ),
  queueMissProcessing: (missId: string) =>
    request<InboxAuditQueueResponse>(
      `/api/v1/inbox-audit/misses/${encodeURIComponent(missId)}/queue-processing`,
      { method: "POST" }
    ),
  queueOpenMissesProcessing: (limit = 5000, dispatchIntervalSeconds = 5) =>
    request<InboxAuditQueueResponse>(
      `/api/v1/inbox-audit/misses/queue-processing?limit=${limit}&dispatch_interval_seconds=${dispatchIntervalSeconds}`,
      { method: "POST" }
    ),
  getQueueProcessingStatus: (tasks: InboxAuditQueueStatusTask[]) =>
    request<InboxAuditQueueStatusResponse>(
      "/api/v1/inbox-audit/misses/queue-processing/status",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tasks }),
      }
    ),
};

export const UsageApi = {
  track: (event: UsageEventCreate) =>
    request<UsageEventResponse>("/api/v1/usage/track", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(event),
    }),
  getStats: (username: string = "admin", days: number = 30) =>
    request<UsageStatsResponse>(
      `/api/v1/usage/stats?username=${encodeURIComponent(username)}&days=${days}`
    ),
  getEvents: (params: {
    username?: string;
    event_type?: string;
    page_path?: string;
    days?: number;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params.username) searchParams.set("username", params.username);
    if (params.event_type) searchParams.set("event_type", params.event_type);
    if (params.page_path) searchParams.set("page_path", params.page_path);
    if (params.days) searchParams.set("days", String(params.days));
    if (params.limit) searchParams.set("limit", String(params.limit));
    if (params.offset) searchParams.set("offset", String(params.offset));
    return request<UsageEventResponse[]>(
      `/api/v1/usage/events?${searchParams.toString()}`
    );
  },
};
