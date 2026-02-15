/**
 * Helper functions for template configuration
 */

import { TAG_OPTIONS, DEFAULT_TAG_SETTINGS, DUMMY_TABLE_DATA, DUMMY_LIEN_STATUS_TABLE, DUMMY_CALL_LOG_TABLE, DUMMY_TEXT_LOG_TABLE, DUMMY_BILLING_STATUS_TABLE } from "../constants/template-config.constants";

export const getTagLabel = (value: string) =>
  TAG_OPTIONS.find((option) => option.value === value)?.label ?? value;

/**
 * Resolve nested placeholders by performing multiple passes.
 * Continues until no more replacements are made or max iterations reached.
 * This allows placeholders within placeholder values to be resolved.
 *
 * Example: If {greeting} = "Hello {patient_name}" and {patient_name} = "Jane Smith",
 * the result will be "Hello Jane Smith" after two passes.
 *
 * @param template - The template string with placeholders
 * @param placeholders - Record of placeholder keys (with braces) to values
 * @param maxIterations - Maximum number of passes to prevent infinite loops (default: 10)
 * @returns The template with all nested placeholders resolved
 */
export const resolveNestedPlaceholders = (
  template: string,
  placeholders: Record<string, string>,
  maxIterations: number = 10
): string => {
  let result = template;
  let iteration = 0;
  let previousResult = '';

  while (result !== previousResult && iteration < maxIterations) {
    previousResult = result;
    Object.entries(placeholders).forEach(([key, value]) => {
      // Escape special regex characters in the placeholder key
      const regex = new RegExp(key.replace(/[{}]/g, '\\$&'), 'g');
      result = result.replace(regex, value);
    });
    iteration++;
  }

  return result;
};

/**
 * Get all dummy placeholder values (shared across all preview functions)
 */
export const getDummyPlaceholders = (): Record<string, string> => {
  // Dummy patient data
  const dummyPatient = {
    firstName: "Jane",
    lastName: "Smith",
    dob: "05/12/1985",
    address: "456 Oak Avenue, Los Angeles, CA 90210",
    homePhone: "555-123-4567",
    cellPhone: "555-987-6543",
    patientId: "PRE1234567",
    doi: "03/22/2024"
  };

  // Build appointment table HTML
  const appointmentTableHtml = `<table border="1" style="border-collapse: collapse; width: 100%;">
<thead>
<tr>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Study ID</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Exam Description</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Status</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Exam Date/Time</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Location</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">MRI Type</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Images Available</th>
<th style="border: 1px solid black; padding: 8px; text-align: left;">Report Available</th>
</tr>
</thead>
<tbody>${DUMMY_TABLE_DATA}</tbody>
</table>`;

  return {
    // Patient info
    "{first_name}": dummyPatient.firstName,
    "{last_name}": dummyPatient.lastName,
    "{patient_name}": `${dummyPatient.firstName} ${dummyPatient.lastName}`,
    "{patient_id}": dummyPatient.patientId,
    "{patient_id_confirmed}": dummyPatient.patientId,
    "{dob}": dummyPatient.dob,
    "{doi}": dummyPatient.doi,
    "{address}": dummyPatient.address,
    "{home_phone}": dummyPatient.homePhone,
    "{cell_phone}": dummyPatient.cellPhone,

    // Tables
    "{appointment_table}": appointmentTableHtml,
    "{lien_status_table}": DUMMY_LIEN_STATUS_TABLE,
    "{call_log_table}": DUMMY_CALL_LOG_TABLE,
    "{text_log_table}": DUMMY_TEXT_LOG_TABLE,
    "{billing_status_table}": DUMMY_BILLING_STATUS_TABLE,

    // Lien-specific
    "{lien_type}": "Attorney Signed Lien (ASL)",
  };
};

/**
 * Generate preview HTML using unified template approach.
 * All templates now use unified_template with custom placeholders.
 */
export const generatePreviewHtml = (
  settings: typeof DEFAULT_TAG_SETTINGS,
  showPersonalInjury: boolean = true
): string => {
  // Get all dummy placeholders
  const dummyPlaceholders = getDummyPlaceholders();

  // Get personal injury info template from custom placeholders (matches backend behavior)
  const personalInjuryTemplate = settings.custom_placeholders?.personal_injury_info ||
    "Important Information regarding personal injury cases<br/>A report containing the findings of the exam will also be sent to the attorney.<br/>A bill will be sent to the attorney once both the patient and the attorney sign all pending liens.<br/>Please make sure to submit a negotiation offer before sending the payment.<br/><br/>";

  // Personal injury info (conditionally included based on checkbox)
  const personalInjuryInfo = showPersonalInjury ? personalInjuryTemplate : "";

  // Start with unified template
  let formattedTemplate = settings.unified_template || "";

  // Build a combined placeholders object for nested resolution
  // This includes dummy placeholders, personal injury info, and custom placeholders
  const allPlaceholders: Record<string, string> = { ...dummyPlaceholders };

  // Add personal injury info (special case - conditional based on showPersonalInjury)
  allPlaceholders["{personal_injury_info}"] = personalInjuryInfo;

  // Add all OTHER custom placeholders (workspace-wide), skipping personal_injury_info since it's handled above
  if (settings.custom_placeholders) {
    Object.entries(settings.custom_placeholders).forEach(([key, value]) => {
      // Skip personal_injury_info since it's handled above with conditional logic
      if (key === 'personal_injury_info') {
        return;
      }
      // Custom placeholders are stored without braces, so add them
      allPlaceholders[`{${key}}`] = value;
    });
  }

  // Use multi-pass nested placeholder resolution
  // This allows placeholders within placeholder values to be resolved
  formattedTemplate = resolveNestedPlaceholders(formattedTemplate, allPlaceholders);

  return formattedTemplate;
};
