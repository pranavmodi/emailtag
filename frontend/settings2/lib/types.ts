export type Maybe<T> = T | null;

export interface AuthCheckResponse {
  authenticated: boolean;
  username?: string;
}

export interface EmailProcessingStatus {
  processing_enabled: boolean;
  description: string;
  last_updated: string | null;
  updated_by: string | null;
}

export interface AutorespondSettingDetail {
  enabled: boolean;
  label: string;
  description: string;
}

export interface AutorespondSettingsResponse {
  global_autorespond_enabled: boolean;
  appointment_inquiry: AutorespondSettingDetail;
  apt_status_req: AutorespondSettingDetail;
  medical_records: AutorespondSettingDetail;
  bill_balance_request: AutorespondSettingDetail;
  bill_offer: AutorespondSettingDetail;
  case_updates: AutorespondSettingDetail;
  missing_lien_request: AutorespondSettingDetail;
  liens: AutorespondSettingDetail;
}

export interface ToggleAutorespondResponse {
  status: string;
  autorespond_type: string;
  enabled: boolean;
  updated_by?: string;
  updated_at?: string;
}

export interface GlobalAutorespondToggleResponse {
  status: string;
  global_autorespond_enabled: boolean;
  updated_by?: string;
  updated_at?: string;
}

export interface ConversationTagStatus {
  conversation_id: string;
  still_has_tag: boolean;
  current_tags: string[];
}

export interface TagStatisticsResponse {
  tag_name: string;
  date: string;
  total_conversations: number;
  still_tagged: number;
  re_tagged: number;
  fetch_failed: number;
  still_tagged_percentage: number;
  re_tagged_percentage: number;
  conversations: ConversationTagStatus[];
}

export interface TagStatisticsSummary {
  tag_name: string;
  total_conversations: number;
  still_tagged: number;
  re_tagged: number;
  fetch_failed: number;
  still_tagged_percentage: number;
  re_tagged_percentage: number;
}

export interface AllTagsStatisticsResponse {
  date: string;
  total_conversations: number;
  total_tags: number;
  tag_statistics: TagStatisticsSummary[];
}

export interface ArchivedConversation {
  conversation_id: string;
  subject: string | null;
  sender: string;
  created_at: string;
  archived_at: string;
  tags_applied: string[];
}

export interface ArchivedConversationsResponse {
  date: string;
  hour: number | null;
  total_archived: number;
  conversations: ArchivedConversation[];
}

export interface ConversationReplayAttachment {
  id?: string;
  filename?: string;
  content_type?: string;
  size?: number;
  download_url?: string;
}

export interface ConversationReplayMessage {
  id: string;
  author_name?: string;
  author_email?: string;
  author_handle?: string;
  direction?: string;
  is_inbound?: boolean;
  created_at?: string;
  body?: string;
  text_body?: string;
  subject?: string;
  attachments: ConversationReplayAttachment[];
}

export interface ConversationReplayResponse {
  conversation_id: string;
  subject?: string;
  message_count: number;
  messages: ConversationReplayMessage[];
}

export interface ConversationReplaySendResponse {
  status: string;
  message_id: string;
  subject: string;
  sent_to: string;
  sender: string;
}

export interface EvalClassificationEntry {
  conversation_id: string;
  predicted_tags: string[];
  actual_tags: string[];
  exact_match: boolean;
  partial_match: boolean;
  accuracy: number;
  matching_tags?: string[];
  missing_tags?: string[];
  extra_tags?: string[];
  error?: string;
}

export interface EvalClassificationResponse {
  conversation_id?: string | null;
  date?: string | null;
  task_id?: string;
  mode?: string;
  message?: string;
  results: EvalClassificationEntry[];
  summary: {
    total: number;
    exact_matches: number;
    partial_matches: number;
    no_matches: number;
    accuracy: number;
  };
}

export interface MessageTemplateResponse {
  id: string;
  template_key: string;
  template_name: string;
  template_body: string;
  description?: string;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
}

export interface TagSettingsResponse {
  id: string;
  tag_name: string;
  settings: Record<string, string>;
  created_at: string;
  updated_at: string;
  updated_by?: string | null;
}

export interface TagSettingsListResponse {
  items: TagSettingsResponse[];
  total: number;
}

export interface TemplateAttachmentResponse {
  id: string;
  tag_name: string;
  template_key?: string | null;
  filename: string;
  file_path: string;
  mime_type: string;
  file_size: number;
  description?: string | null;
  created_at: string;
  uploaded_by?: string | null;
}

export interface TemplateAttachmentListResponse {
  items: TemplateAttachmentResponse[];
  total: number;
}

export interface TemplateAttachmentUploadResponse {
  attachment: TemplateAttachmentResponse;
  message: string;
}

export interface BillOfferIntake {
  id: string;
  front_conversation_id: string;
  email_id?: string | null;
  status: string;
  patient_id?: string | null;
  patient_match?: Record<string, any> | null;
  patient_data?: Record<string, any> | null;
  extracted_facts?: Record<string, any> | null;
  corrected_facts?: Record<string, any> | null;
  missing_fields?: string[] | null;
  confidence?: Record<string, any> | null;
  original_sender_email?: string | null;
  last_agent_action?: string | null;
  last_run_id?: string | null;
  last_agent_run_status?: string | null;
  reply_draft?: string | null;
  reply_sent_at?: string | null;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BillOfferTaggedEmail {
  front_conversation_id: string;
  email_id: string;
  subject?: string | null;
  sender: string;
  received_at: string;
  search_text?: string | null;
  tags: string[];
  has_intake: boolean;
  intake?: BillOfferIntake | null;
}

export interface BillOfferTaggedEmailListResponse {
  items: BillOfferTaggedEmail[];
  total: number;
}

export interface BillOfferIntakeListResponse {
  items: BillOfferIntake[];
  total: number;
}

export interface BillOfferAgentLog {
  id: string;
  front_conversation_id: string;
  email_id?: string | null;
  intake_id?: string | null;
  run_id: string;
  step_name: string;
  step_status: string;
  input_snapshot?: Record<string, any> | null;
  output_snapshot?: Record<string, any> | null;
  message?: string | null;
  error?: string | null;
  created_at: string;
}

export interface BillOfferAgentLogListResponse {
  items: BillOfferAgentLog[];
  total: number;
}

export interface BillOfferCorrectionAudit {
  id: string;
  front_conversation_id: string;
  intake_id: string;
  field_name: string;
  previous_value?: Record<string, any> | null;
  new_value?: Record<string, any> | null;
  changed_by?: string | null;
  created_at: string;
}

export interface BillOfferCorrectionAuditListResponse {
  items: BillOfferCorrectionAudit[];
  total: number;
}

export interface BillOfferSettingsResponse {
  review_required: boolean;
}

export interface BillOfferRunAgentResponse {
  status: string;
  run_id: string;
  intake: BillOfferIntake;
  details: Record<string, any>;
}

// Classification Traces Types
export interface RecentConversation {
  conversation_id: string;
  last_trace_at: string | null;
  classification_traces: number;
  archival_traces: number;
  total_tokens: number;
}

export interface RecentConversationsResponse {
  conversations: RecentConversation[];
  total_count: number;
}

export interface DocumentAnalysis {
  filename?: string;
  file_size?: number | string;
  document_type?: string;
  description?: string;
  patient_id?: string;
  confidence?: string | number;
  detected_type?: string;
  processing_status?: string;
  enhanced_lien_analysis?: Record<string, unknown>;
  enhanced_lien_processing?: Record<string, unknown>;
}

export interface LienValidation {
  check_type: string;
  filename?: string;
  // Signature fields
  patient_signature_present?: boolean;
  attorney_signature_present?: boolean;
  patient_signature_inside_box?: boolean;
  attorney_signature_inside_box?: boolean;
  lien_signature_type?: string;
  placement_valid?: boolean;
  placement_issues?: string[];
  signature_analysis?: string;
  // Barcode fields
  barcode_found?: boolean;
  patient_ids?: string[];
  lien_types?: string[];
  referrer_id?: string;
  raw_barcode_value?: string;
  all_barcodes?: unknown[];
  // Cover letter fields
  is_cover_letter?: boolean;
  cover_letter_confidence?: string | number;
  has_conditional_language?: boolean;
  conditional_language_confidence?: string | number;
  conditional_phrases_found?: string[];
  page_classification?: string;
  explanation?: string;
  // Image quality fields
  document_quality?: string;
  quality_explanation?: string;
  quality_by_page?: Array<{ page: number; quality: string }>;
  overall_quality?: string;
  // Strikethrough fields
  strikethrough_detected?: boolean;
  strikethrough_instances?: Array<{
    page_number?: number;
    struck_through_text: string;
    visual_description?: string;
    confidence?: string;
  }>;
  total_instances?: number;
  pages_with_strikethrough?: number;
  total_pages?: number;
  summary?: Record<string, unknown>;
  raw_data?: Record<string, unknown>;
}

// No Action List Types
export interface NoActionListResponse {
  no_action_list: string[];
  count: number;
  description: string;
}

export interface NoActionListUpdateResponse {
  success: boolean;
  message: string;
  no_action_list: string[];
  count: number;
  updated_by: string;
}

// AI Training Conversations Types
export interface AITrainingConversation {
  conversation_id: string;
  subject: string | null;
  recipient: string | null;
  status: string;
  created_at: string | null;
  tags: string[];
  front_url: string;
}

export interface AITrainingConversationsResponse {
  conversations: AITrainingConversation[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  available_tags: string[];
  filter_tags: string[];
  days: number;
  error?: string;
}

export interface ClassificationTrace {
  id: string;
  trace_type: string;
  step_name: string;
  step_order: number;
  classification_path: string | null;
  llm_model: string | null;
  prompt_template: string | null;
  full_prompt: string | null;
  llm_response: string | null;
  chosen_option: string | null;
  conversation_summary: string | null;
  classification_reason: string | null;
  email_format: string | null;
  message_count: number | null;
  started_at: string | null;
  completed_at: string | null;
  duration_ms: number | null;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  total_tokens: number | null;
  document_analysis: DocumentAnalysis | null;
  lien_validation: LienValidation | null;
  input_data: Record<string, unknown> | null;
  output_data: Record<string, unknown> | null;
  error_data: Record<string, unknown> | null;
}

// PIF (Personal Injury Firm) Types
export interface PifContact {
  name: string;
  title: string;
  email: string;
  phone: string;
  extension: string;
}

export interface LeadershipMember {
  name: string;
  title: string;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  bio: string | null;
  image_url: string | null;
  // Enriched fields from LinkedIn research
  education?: string[];
  experience?: string[];
  skills?: string[];
  certifications?: string[];
  publications?: string[];
  cases_handled?: string[];
  bar_admissions?: string[];
}

export interface StaffMember {
  name: string;
  title: string;
  role_category: string; // intake_specialist, case_manager, paralegal, office_manager, billing_coordinator, medical_records, other
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  bio: string | null;
}

export interface LeadershipEmailEntry {
  name: string;
  title: string;
  email: string;
  total_emails: number;
  first_contact: string | null;
  last_contact: string | null;
  tag_distribution: Record<string, number>;
  recent_subjects: string[];
  matched_by: string;
}

export interface ResearchData {
  practice_areas: string[];
  founded_year: string | null;
  firm_size: string | null;
  office_locations: string[];
  notable_cases: string[];
  awards_recognition: string[];
  bar_associations: string[];
  social_media: Record<string, string>;
  additional_info: string | null;
  sources: string[];
  leadership_email_history?: LeadershipEmailEntry[];
}

export interface BehavioralData {
  total_email_count: number;
  monthly_email_volume: number[]; // [3 months oldest first]
  last_contact_date: string | null;
  days_since_last_contact: number | null;
  topic_distribution: Record<string, number>;
  primary_pain_point: string | null;
  sender_roles: Record<string, number>;
  contact_profiles?: Record<string, Record<string, unknown>>;
  peak_contact_days: string[];
  after_hours_ratio: number;
  analyzed_at: string;
}

export interface ScoreBreakdown {
  email_volume_score: number;
  email_volume_reason: string;
  recency_score: number;
  recency_reason: string;
  pain_signals_score: number;
  pain_signals_reason: string;
  firm_size_score: number;
  firm_size_reason: string;
  completeness_score: number;
  completeness_reason: string;
  total: number;
  scored_at: string | null;
}

export interface MonthlyEmailVolumePoint {
  month: string;
  count: number;
}

export interface PipelineRecord {
  id: string;
  pif_id: string;
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
  created_at: string;
  updated_at: string;
}

export interface PipelineListResponse {
  items: PipelineRecord[];
  total: number;
}

export interface AnalyticsSummary {
  total_firms_tracked: number;
  firms_by_tier: Record<string, number>;
  firms_by_entity_type: Record<string, number>;
  top_pain_points: Array<{ pain_point: string; count: number }>;
  avg_monthly_volume_by_tier: Record<string, number>;
  pipeline_funnel: Record<string, number>;
  firms_contacted_last_30_days: number;
  firms_needing_recontact: number;
}

export interface AutorespondEvent {
  id: string;
  pif_id: string | null;
  firm_name: string | null;
  agent_type: string;
  contact_email: string;
  contact_name: string | null;
  conversation_id: string;
  email_subject: string | null;
  tags: string[];
  response_sent: boolean;
  test_mode: boolean;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface AutorespondEventListResponse {
  items: AutorespondEvent[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AutorespondEventSummary {
  total_events: number;
  events_today: number;
  events_this_week: number;
  by_agent_type: Record<string, number>;
  by_day: Array<{ date: string; count: number }>;
  top_firms: Array<{ firm_name: string; pif_id: string | null; count: number }>;
}

export const AGENT_TYPE_LABELS: Record<string, string> = {
  apt_status_req: "Apt Status",
  bill_balance_request: "Bill/Balance",
  medical_records: "Medical Records",
  psl_lien: "PSL Lien",
  asl_lien: "ASL Lien",
  missing_lien_request: "Missing Lien",
  case_updates: "Case Updates",
  unknown_sig_lien: "Unknown Sig Lien",
};

export const ENTITY_TYPE_LABELS: Record<string, string> = {
  pi_law_firm: "PI Law Firm",
  medical_referring: "Medical Referring",
  medical_facility: "Medical Facility",
  insurance: "Insurance",
  funding: "Funding",
  collections: "Collections",
  legal_other: "Legal (Other)",
  administrative: "Administrative",
  patient_adjacent: "Patient Adjacent",
};

export interface PifInfoResponse {
  id: string;
  firm_name: string;
  entity_type: string;
  website: string | null;
  canonical_website: string | null;
  website_status: string | null;
  website_source: string | null;
  website_confidence: number | null;
  emails: string[];
  phones: string[];
  fax: string | null;
  addresses: string[];
  contacts: PifContact[];
  first_contacted_precise_at: string | null;
  conversation_ids: string[];
  extraction_notes: string | null;
  leadership: LeadershipMember[] | null;
  research_data: ResearchData | null;
  research_status: string | null;
  last_researched_at: string | null;
  staff: StaffMember[] | null;
  staff_research_status: string | null;
  // Behavioral intelligence
  behavioral_data: BehavioralData | null;
  icp_score: number | null;
  icp_tier: string | null;
  score_breakdown: ScoreBreakdown | null;
  icp_scored_at: string | null;
  vendor_stack: VendorStackEntry[] | null;
  monthly_email_volume: MonthlyEmailVolumePoint[];
  created_at: string;
  updated_at: string;
}

export interface VendorStackEntry {
  vendor: string;
  source: string;
  confidence?: string;
  known?: boolean;
  evidence?: string;
}

export interface ResearchResponse {
  pif_id: string;
  firm_name: string;
  status: string;
  leadership: LeadershipMember[];
  research_data: ResearchData | null;
  message: string;
}

export interface ResearchStartResponse {
  pif_id: string;
  firm_name: string;
  task_id: string;
  status: string;
  message: string;
}

export interface ResearchStatusResponse {
  pif_id: string;
  firm_name: string;
  task_id: string;
  status: string;
  leadership?: LeadershipMember[] | null;
  research_data?: ResearchData | null;
  message: string;
}

export interface FullEnrichmentStatusResponse {
  task_id: string;
  status: string;
  message: string;
  pif_id?: string | null;
  firm_name?: string | null;
  result?: Record<string, unknown> | null;
}

export interface PifInfoListResponse {
  items: PifInfoResponse[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface PersonSearchResult {
  name: string;
  title: string;
  email: string | null;
  phone: string | null;
  linkedin: string | null;
  bio: string | null;
  role_category: string | null;
  source: string; // 'leadership' or 'staff'
  firm_id: string;
  firm_name: string;
  firm_website: string | null;
}

export interface PeopleSearchResponse {
  results: PersonSearchResult[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface OutreachMessageResult {
  name: string;
  title: string;
  subjectShortPranav: string;
  subjectShortNeha: string;
  subjectLongPranav: string;
  subjectLongNeha: string;
  shortPranav: string;
  shortNeha: string;
  longPranav: string;
  longNeha: string;
}

export interface OutreachResponse {
  pif_id: string;
  firm_name: string;
  messages: OutreachMessageResult[];
  errors: string[];
}

export interface ProcessDayResponse {
  date: string;
  total_conversations: number;
  processed: number;
  firms_found: number;
  firms_created: number;
  firms_updated: number;
  errors: string[];
}

// Firm Lookup Types
export interface FirmLookupRequest {
  firm_name: string;
  website?: string;
  email?: string;
  phone?: string;
  contact_name?: string;
}

export interface FirmLookupConversation {
  conversation_id: string;
  subject: string | null;
  sender: string | null;
  created_at: string | null;
  snippet: string | null;
  source: "local" | "front";
}

export interface FirmLookupResponse {
  matching_firms: PifInfoResponse[];
  conversations: FirmLookupConversation[];
  total_conversations: number;
}

export interface FirmLookupCreateRequest {
  firm_name: string;
  website?: string;
  email?: string;
  phone?: string;
  contact_name?: string;
  selected_conversation_ids: string[];
  start_research: boolean;
}

export interface FirmLookupCreateResponse {
  pif: PifInfoResponse;
  is_new: boolean;
  task_id: string | null;
  message: string;
}

export interface ExtractConversationResponse {
  conversation_id: string;
  extracted: boolean;
  is_new_firm?: boolean;
  pif_id?: string;
  firm_name?: string;
  firm_info?: {
    website: string | null;
    emails: string[];
    phones: string[];
    fax: string | null;
    addresses: string[];
    contacts: PifContact[];
    conversation_count: number;
  };
  message?: string;
}

export interface FrontInbox {
  id: string;
  name: string;
  type: string;
  address: string;
  is_private: boolean;
}

export interface FrontInboxListResponse {
  items: FrontInbox[];
  total: number;
}

export interface FrontTag {
  id: string;
  name: string;
  highlight: string;
}

export interface FrontConversationSummary {
  id: string;
  subject: string;
  status: string;
  status_category: string;
  assignee_name: string;
  recipient_name: string;
  recipient_handle: string;
  tags: FrontTag[];
  created_at: string | null;
  updated_at: string | null;
  waiting_since: string | null;
  front_url: string;
}

export interface FrontConversationListResponse {
  items: FrontConversationSummary[];
  next_cursor: string | null;
}

export interface FrontMessageRecipient {
  name: string;
  handle: string;
  role: string;
}

export interface FrontMessageAttachment {
  id: string;
  filename: string;
  content_type: string;
  size?: number | null;
}

export interface FrontConversationMessage {
  id: string;
  type: string;
  is_inbound: boolean;
  created_at: string | null;
  subject: string;
  author_name: string;
  author_handle: string;
  recipients: FrontMessageRecipient[];
  text: string;
  body: string;
  blurb: string;
  attachments: FrontMessageAttachment[];
}

export interface FrontConversationDetailResponse {
  conversation: FrontConversationSummary;
  messages: FrontConversationMessage[];
  message_count: number;
}

export interface FrontInboxExportStartResponse {
  export_id: string;
  status: string;
  message: string;
}

export interface FrontInboxExportStatus {
  export_id?: string;
  status: string;
  message: string;
  inbox_id: string;
  inbox_name?: string | null;
  date_from: string;
  date_to: string;
  total_conversations: number;
  processed_conversations: number;
  download_url?: string | null;
  file_size?: number | null;
  created_at?: string;
  updated_at?: string;
}

// Test Email Types
export interface TestEmailScenario {
  key: string;
  description: string;
  subject: string;
  expected_tags: string[];
  has_attachments: boolean;
  type: string;
}

export interface TestEmailScenariosResponse {
  scenarios: Record<string, Record<string, TestEmailScenario>>;
  types: Record<string, string>;
  smtp_configured: boolean;
  recipient_email: string | null;
}

export interface SendTestEmailRequest {
  scenario_keys: string[];
  recipient_email?: string;
}

export interface SendTestEmailResult {
  scenario_key: string;
  status: "success" | "failed";
  message: string;
  test_id?: string;
}

export interface SendTestEmailResponse {
  results: SendTestEmailResult[];
}

export interface TestEmailConfigResponse {
  smtp_configured: boolean;
  recipient_email: string | null;
  smtp_host: string | null;
}
