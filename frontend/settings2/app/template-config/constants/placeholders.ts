/**
 * Placeholder definitions for autorespond templates
 *
 * Structure:
 * - common: Placeholders available to ALL autorespond types
 * - specific: Placeholders specific to each autorespond type
 */

export interface Placeholder {
  key: string;
  description: string;
  example?: string;
}

/**
 * Map tag names (from UI dropdown) to autorespond types (internal keys)
 */
export const TAG_TO_AUTORESPOND_TYPE: Record<string, string> = {
  "Apt status req": "autorespond_apt_status_req",
  "Lien Templates": "autorespond_liens",
  "Medical Records": "autorespond_medical_records",
  "Bill or Balance Request": "autorespond_bill_balance_request",
  "Case Updates": "autorespond_case_updates",
  "Missing Lien Request": "autorespond_missing_lien_request",
  "Appointment Inquiry": "autorespond_appointment_inquiry"
};

export interface PlaceholderSet {
  common: Placeholder[];
  specific: Record<string, Placeholder[]>;
}

export const TEMPLATE_PLACEHOLDERS: PlaceholderSet = {
  // Common placeholders available to ALL autorespond types
  common: [
    {
      key: "{patient_id}",
      description: "Patient ID",
      example: "PRE100453"
    },
    {
      key: "{patient_name}",
      description: "Patient full name",
      example: "John Doe"
    },
    {
      key: "{dob}",
      description: "Date of birth (MM/DD/YYYY)",
      example: "01/15/1985"
    },
    {
      key: "{doi}",
      description: "Date of injury (MM/DD/YYYY)",
      example: "03/20/2024"
    }
  ],

  // Type-specific placeholders
  specific: {
    // Appointment Status Request
    autorespond_apt_status_req: [
      {
        key: "{appointment_date}",
        description: "Upcoming appointment date",
        example: "12/25/2024"
      },
      {
        key: "{appointment_time}",
        description: "Appointment time",
        example: "2:30 PM"
      },
      {
        key: "{modality}",
        description: "Imaging modality",
        example: "MRI, CT, X-Ray"
      },
      {
        key: "{location}",
        description: "Appointment location",
        example: "Main Office"
      },
      {
        key: "{appointment_status}",
        description: "Current appointment status",
        example: "Confirmed, Pending, Cancelled"
      }
    ],

    // Liens (ASL & PSL)
    autorespond_liens: [
      {
        key: "{lien_type}",
        description: "Type of lien",
        example: "Attorney Signed Radiology Lien"
      },
      {
        key: "{lien_status_table}",
        description: "HTML table showing lien upload statuses for all documents",
        example: "<table>...</table>"
      },
      {
        key: "{signature_type}",
        description: "Signature type (ASL or PSL)",
        example: "Attorney Signed"
      }
    ],

    // Medical Records
    autorespond_medical_records: [
      {
        key: "{request_type}",
        description: "Type of medical records requested",
        example: "Release of Records, Image Request, CD Request"
      },
      {
        key: "{processing_time}",
        description: "Estimated processing time",
        example: "3-5 business days"
      },
      {
        key: "{record_format}",
        description: "Format of records",
        example: "CD, Digital Download, Paper"
      }
    ],

    // Bill or Balance Request
    autorespond_bill_balance_request: [
      {
        key: "{current_balance}",
        description: "Current outstanding balance",
        example: "$1,250.00"
      },
      {
        key: "{invoice_number}",
        description: "Invoice/bill number",
        example: "INV-2024-001"
      },
      {
        key: "{payment_methods}",
        description: "Available payment methods",
        example: "Credit Card, Check, Online Portal"
      }
    ],

    // Case Updates
    autorespond_case_updates: [
      {
        key: "{case_update_type}",
        description: "Type of case update",
        example: "Drop Letter, New Attorney, Promise to Send Payment"
      },
      {
        key: "{balance}",
        description: "Current account balance",
        example: "$2,500.00"
      },
      {
        key: "{lien_status}",
        description: "Current lien status",
        example: "Active, Pending, Resolved"
      },
      {
        key: "{attorney_name}",
        description: "Attorney name (for New Attorney updates)",
        example: "Smith & Associates"
      }
    ],

    // Missing Lien Request
    autorespond_missing_lien_request: [
      {
        key: "{requested_lien_type}",
        description: "Type of lien being requested",
        example: "Radiology Lien, Technologist Lien"
      },
      {
        key: "{required_documents}",
        description: "List of required documents",
        example: "Signed lien form, Photo ID"
      }
    ],

    // Appointment Inquiry (if needed separately from apt_status_req)
    autorespond_appointment_inquiry: [
      {
        key: "{available_dates}",
        description: "Available appointment dates",
        example: "12/20, 12/21, 12/22"
      },
      {
        key: "{contact_phone}",
        description: "Scheduling phone number",
        example: "(555) 123-4567"
      },
      {
        key: "{scheduling_link}",
        description: "Online scheduling link",
        example: "https://schedule.preciseimaging.com"
      }
    ]
  }
};

/**
 * Get all available placeholders for a specific autorespond type
 * @param autorespondType - The autorespond type key
 * @returns Combined array of common and specific placeholders
 */
export function getPlaceholdersForType(autorespondType: string): {
  common: Placeholder[];
  specific: Placeholder[];
} {
  return {
    common: TEMPLATE_PLACEHOLDERS.common,
    specific: TEMPLATE_PLACEHOLDERS.specific[autorespondType] || []
  };
}

/**
 * Get all valid placeholder keys for a specific autorespond type
 * @param autorespondType - The autorespond type key
 * @returns Array of placeholder keys
 */
export function getValidPlaceholderKeys(autorespondType: string): string[] {
  const { common, specific } = getPlaceholdersForType(autorespondType);
  return [
    ...common.map(p => p.key),
    ...specific.map(p => p.key)
  ];
}

/**
 * Check if a placeholder is valid for a specific autorespond type
 * @param placeholder - The placeholder key to check (e.g., "{patient_id}")
 * @param autorespondType - The autorespond type key
 * @returns true if placeholder is valid
 */
export function isValidPlaceholder(placeholder: string, autorespondType: string): boolean {
  const validKeys = getValidPlaceholderKeys(autorespondType);
  return validKeys.includes(placeholder);
}

/**
 * Extract all placeholders from template text
 * @param templateText - The template text to search
 * @returns Array of placeholder keys found in the text
 */
export function extractPlaceholders(templateText: string): string[] {
  const placeholderRegex = /\{[^}]+\}/g;
  const matches = templateText.match(placeholderRegex);
  return matches ? Array.from(new Set(matches)) : [];
}

/**
 * Validate template placeholders
 * @param templateText - The template text to validate
 * @param autorespondType - The autorespond type key
 * @returns Object with validation result and any invalid placeholders
 */
export function validateTemplatePlaceholders(
  templateText: string,
  autorespondType: string
): { isValid: boolean; invalidPlaceholders: string[] } {
  const usedPlaceholders = extractPlaceholders(templateText);
  const validKeys = getValidPlaceholderKeys(autorespondType);

  const invalidPlaceholders = usedPlaceholders.filter(
    placeholder => !validKeys.includes(placeholder)
  );

  return {
    isValid: invalidPlaceholders.length === 0,
    invalidPlaceholders
  };
}
