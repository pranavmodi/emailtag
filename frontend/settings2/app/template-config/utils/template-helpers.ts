/**
 * Helper functions for template configuration
 */

import { TAG_OPTIONS, DEFAULT_TAG_SETTINGS, DUMMY_TABLE_DATA } from "../constants/template-config.constants";

export const getTagLabel = (value: string) =>
  TAG_OPTIONS.find((option) => option.value === value)?.label ?? value;

/**
 * Generate preview HTML using unified template approach.
 * All templates now use unified_template with custom placeholders.
 */
export const generatePreviewHtml = (
  settings: typeof DEFAULT_TAG_SETTINGS,
  showPersonalInjury: boolean = true
): string => {

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

  // Build table HTML
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

  // Personal injury info (conditionally included)
  const personalInjuryInfo = showPersonalInjury
    ? "Important Information regarding personal injury cases<br/>A report containing the findings of the exam will also be sent to the attorney.<br/>A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.<br/>Please make sure to submit a negotiation offer before sending the payment.<br/><br/>"
    : "";

  // Start with unified template
  let formattedTemplate = (settings.unified_template || "")
    .replace(/\{appointment_table\}/g, tableHtml)
    .replace(/\{personal_injury_info\}/g, personalInjuryInfo)
    .replace(/\{patient_id_confirmed\}/g, dummyPatient.patientId)
    .replace(/\{first_name\}/g, dummyPatient.firstName)
    .replace(/\{last_name\}/g, dummyPatient.lastName)
    .replace(/\{dob\}/g, dummyPatient.dob)
    .replace(/\{address\}/g, dummyPatient.address)
    .replace(/\{home_phone\}/g, dummyPatient.homePhone)
    .replace(/\{cell_phone\}/g, dummyPatient.cellPhone);

  // Replace all custom placeholders (workspace-wide)
  if (settings.custom_placeholders) {
    Object.entries(settings.custom_placeholders).forEach(([key, value]) => {
      const regex = new RegExp(`\\{${key}\\}`, 'g');
      formattedTemplate = formattedTemplate.replace(regex, value);
    });
  }

  return formattedTemplate;
};
