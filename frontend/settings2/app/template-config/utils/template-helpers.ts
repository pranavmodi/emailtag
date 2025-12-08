/**
 * Helper functions for template configuration
 */

import { TAG_OPTIONS, DEFAULT_TAG_SETTINGS, DUMMY_TABLE_DATA } from "../constants/template-config.constants";

export const getTagLabel = (value: string) =>
  TAG_OPTIONS.find((option) => option.value === value)?.label ?? value;

// Generate preview HTML
export const generatePreviewHtml = (
  settings: typeof DEFAULT_TAG_SETTINGS,
  showPersonalInjury: boolean = true
): string => {
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
