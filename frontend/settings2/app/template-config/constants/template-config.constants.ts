/**
 * Constants and default values for template configuration
 */

export const MENU_ITEMS = [
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
] as const;

export const SHOW_TEMPLATE_EDITOR = false;

export const TEMPLATE_DEFINITIONS = {
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

export type TemplateKey = keyof typeof TEMPLATE_DEFINITIONS;

export const TAG_OPTIONS = [
  { value: "Apt status req", label: "Apt Status Req" },
  { value: "Lien Templates", label: "Lien Templates" },
  { value: "Bill or Balance Request", label: "Bill or Balance Request" }
];

// Dummy data for preview - Appointment table
export const DUMMY_TABLE_DATA = `<tr>
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

// Dummy data for lien status table preview
export const DUMMY_LIEN_STATUS_TABLE = `<table border="1" style="border-collapse: collapse; width: 100%; margin-top: 10px;">
<thead>
<tr>
<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f0f0f0;">Lien Type</th>
<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f0f0f0;">Patient Signature</th>
<th style="border: 1px solid black; padding: 8px; text-align: left; background-color: #f0f0f0;">Attorney Signature</th>
</tr>
</thead>
<tbody>
<tr>
<td style="border: 1px solid black; padding: 8px;">Technical Lien (Imaging)</td>
<td style="border: 1px solid black; padding: 8px;">Signed 11/19/2025</td>
<td style="border: 1px solid black; padding: 8px;">Not Signed.<br/><a href="https://example.com/esign-attorney-tech" target="_blank" style="color: #2563eb; text-decoration: underline;">Please eSign here</a></td>
</tr>
<tr>
<td style="border: 1px solid black; padding: 8px;">Professional Lien (Report)</td>
<td style="border: 1px solid black; padding: 8px;">Not Signed.<br/><a href="https://example.com/esign-patient-rad" target="_blank" style="color: #2563eb; text-decoration: underline;">Please eSign here</a></td>
<td style="border: 1px solid black; padding: 8px;">Not Signed.<br/><a href="https://example.com/esign-attorney-rad" target="_blank" style="color: #2563eb; text-decoration: underline;">Please eSign here</a></td>
</tr>
</tbody>
</table>`;

// Dummy data for call log table preview
export const DUMMY_CALL_LOG_TABLE = `<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; font-family: Arial, sans-serif; font-size: 14px; margin-top: 10px;">
<thead>
<tr style="background-color: #f2f2f2;">
<th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Date/Time</th>
<th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Phone #</th>
<th style="text-align: center; padding: 10px; border: 1px solid #ddd;">Direction</th>
<th style="text-align: left; padding: 10px; border: 1px solid #ddd;">Disposition</th>
</tr>
</thead>
<tbody>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;">12/22/2025 02:30 PM</td>
<td style="padding: 8px; border: 1px solid #ddd;">(555) 123-4567</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center; color: #4CAF50; font-weight: bold;">⬅️ Inbound</td>
<td style="padding: 8px; border: 1px solid #ddd;">Appointment Confirmed</td>
</tr>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;">12/20/2025 10:15 AM</td>
<td style="padding: 8px; border: 1px solid #ddd;">(555) 123-4567</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center; color: #2196F3; font-weight: bold;">➡️ Outbound</td>
<td style="padding: 8px; border: 1px solid #ddd;">Left Voicemail</td>
</tr>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;">12/18/2025 03:45 PM</td>
<td style="padding: 8px; border: 1px solid #ddd;">(555) 987-6543</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: center; color: #4CAF50; font-weight: bold;">⬅️ Inbound</td>
<td style="padding: 8px; border: 1px solid #ddd;">Scheduling Question</td>
</tr>
</tbody>
</table>`;

export const DEFAULT_UNIFIED_TEMPLATE = `Dear {first_name} {last_name},<br/>
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
export const DEFAULT_CUSTOM_PLACEHOLDERS: Record<string, string> = {
  scheduling_phone: "800-558-2223",
  no_show_policy: "**If the patient cannot make the appointment please contact us within 48 hours of the appointment to reschedule or cancel to avoid any no-show fees. Two no-shows will require a $50 no-show payment before being scheduled for a 3rd time.**",
  bills_link: "https://app.radflow360.com/patient-portal",
  reports_link: "https://app.radflow360.com/patient-portal",
};

// Default lien templates (for ASL and PSL lien agents)
export const DEFAULT_LIEN_TEMPLATES = {
  lien_success_template: `Thank you for submitting the {lien_type}.

Patient ID: {patient_id}
Patient: {patient_name}
DOB: {dob}
DOI: {doi}

Your lien has been successfully uploaded to the patient file and is now on record.

{lien_status_table}

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  lien_patient_not_found_template: `Thank you for submitting the {lien_type}.

We're having trouble locating the patient record for this lien. A member of our billing team will personally review your submission and get back to you shortly.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  lien_reject_no_changes_template: `Thank you for submitting the {lien_type}.

We've received your lien document, however it appears to contain modifications or alterations (such as cross-outs, black-outs, or added text).

Please resubmit a clean, unmodified lien document so we can properly process it.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  lien_reject_not_readable_template: `Thank you for submitting the {lien_type}.

We received your lien document, however the document appears to be unreadable due to poor image quality, blurriness, or scanning issues.

Please resend a clearer version of the lien document so we can properly process it.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  lien_reject_sig_not_valid_template: `Thank you for submitting the {lien_type}.

We've received your lien document, however the signature appears to be completely outside the designated signature area.

Signatures must be placed inside or at least partially overlapping the signature box. Please resubmit the lien with the signature properly placed in the correct box.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  lien_reject_cover_letter_conditional_template: `Thank you for submitting the {lien_type}.

We've received your lien submission, however the cover letter contains conditional language or requests modifications to our standard lien terms.

We can only accept liens using our standard, unmodified agreement forms. Please resubmit the lien without the conditional language or contact our billing department to discuss your specific needs.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  lien_reject_email_conditional_template: `Thank you for submitting the {lien_type}.

We've received your lien submission, however the email message contains conditional language or requests modifications to our standard lien terms.

We can only accept liens using our standard, unmodified agreement forms. Please resubmit the lien without the conditional language or contact our billing department to discuss your specific needs.

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com`,

  // Bill Balance templates
  bill_balance_found_template: `Dear {patient_name},

Thank you for your inquiry regarding your account balance.

Patient ID: {patient_id}
Account Number: {account_number}
Current Balance: {current_balance}
Invoice Number: {invoice_number}

You can view detailed billing information and make payments through our patient portal:
<a href="{portal_link}">Access Patient Portal</a>

Available Payment Methods:
{payment_methods}

For billing questions, please contact our billing department at {billing_phone}.

Thank you,
Precise Imaging Billing Department
www.PreciseMRI.com`,

  bill_balance_not_found_template: `Thank you for your billing inquiry.

We're unable to locate a unique patient record. This could be because:
- The patient ID was not found in our system
- Multiple patient records were found matching the provided information

A member of our billing team will personally review your request and respond to you shortly. If you have any additional information such as:
- Full patient name and date of birth
- Invoice numbers or account numbers
- Service dates

Please reply with those details to help us locate the correct account.

For immediate assistance, please contact our billing department at {billing_phone}.

Thank you,
Precise Imaging Billing Department
www.PreciseMRI.com`
};

/**
 * Standard Tag Settings Structure
 *
 * Individual tags store ONLY templates (unified or scenario-specific)
 * Custom placeholders are stored separately in WORKSPACE tag
 *
 * NO LEGACY FIELDS - All settings use this standardized approach
 */
export const DEFAULT_TAG_SETTINGS = {
  // Unified template (for single-template tags like Apt status req)
  unified_template: DEFAULT_UNIFIED_TEMPLATE,

  // Lien templates (multi-scenario tag)
  lien_success_template: DEFAULT_LIEN_TEMPLATES.lien_success_template,
  lien_patient_not_found_template: DEFAULT_LIEN_TEMPLATES.lien_patient_not_found_template,
  lien_reject_no_changes_template: DEFAULT_LIEN_TEMPLATES.lien_reject_no_changes_template,
  lien_reject_not_readable_template: DEFAULT_LIEN_TEMPLATES.lien_reject_not_readable_template,
  lien_reject_sig_not_valid_template: DEFAULT_LIEN_TEMPLATES.lien_reject_sig_not_valid_template,
  lien_reject_cover_letter_conditional_template: DEFAULT_LIEN_TEMPLATES.lien_reject_cover_letter_conditional_template,
  lien_reject_email_conditional_template: DEFAULT_LIEN_TEMPLATES.lien_reject_email_conditional_template,

  // Bill Balance templates (multi-scenario tag)
  bill_balance_found_template: "",
  bill_balance_not_found_template: "",
  bill_balance_lien_reminder_template: "",
  bill_balance_no_data_template: "",
  bill_balance_request_patient_id_template: "",
  bill_balance_escalation_template: "",

  // Note: custom_placeholders are now stored in WORKSPACE tag, not per-tag
  // This field is added dynamically in the UI for PlaceholderManager
  custom_placeholders: DEFAULT_CUSTOM_PLACEHOLDERS,
};
