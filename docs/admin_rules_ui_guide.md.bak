# Admin Rules UI Guide

## 1. Introduction

This guide explains how to use the Admin Rules UI to manage the classification rules for the email tagging system. These "rules" are actually **LLM (Large Language Model) prompt templates** that instruct an AI (like GPT-4o) on how to categorize emails.

The UI interacts with the `hierarchical_classification_rules` table in the database. Each entry in this table represents a specific set of instructions (a prompt) used at a particular step in the email classification process.

## 2. Accessing the UI

The Admin Rules UI is accessible at the following URL:

*   **`/admin/rules`**

## 3. Understanding the Rules Table Display

When you navigate to the `/rules` page, you will see a table listing all the currently defined hierarchical classification rules. The table has the following columns:

*   **Name:** A human-readable name assigned to the rule set. This helps in identifying the purpose of the rule, e.g., "ROOT_SCHEDULING_RULES" or "Primary Top-Level Classification".
*   **Category:** This is a **critical, unique hierarchical key** for the rule set.
    *   Examples: `ROOT`, `ROOT_SCHEDULING`, `ROOT_ACCOUNTS_RECEIVABLE_BILLING_INQUIRIES`.
    *   The system uses this key to fetch the correct prompt template at each stage of the classification.
    *   It is **read-only** in the edit form because it's derived from the system's `EMAIL_CATEGORIES` structure.
*   **Rule Content:** This is the actual LLM prompt template.
    *   It contains detailed instructions for the AI.
    *   Crucially, it includes the placeholder `{{EMAIL_CONTENT_PLACEHOLDER}}`, which the system replaces with the actual email text before sending it to the AI.
    *   The content is displayed in a scrollable, pre-formatted box for readability.
*   **Created At:** The date and time when the rule was initially created.
*   **Updated At:** The date and time when the rule was last modified.
*   **Actions:**
    *   **Edit:** Allows you to modify the `Name` and `Rule Content` of the selected rule.

## 4. How Hierarchical Classification Works (A Brief Overview)

The email classification system uses a hierarchical approach, guided by a structure defined in `settings.EMAIL_CATEGORIES`. Think of this as a decision tree.

1.  **Starting Point:** Classification always begins with the `ROOT` category. The system fetches the rule from `hierarchical_classification_rules` where `category = "ROOT"`.
2.  **LLM Makes a Choice:** The `Rule Content` (prompt) for `ROOT` typically asks the LLM to choose from the main top-level email categories (e.g., "Scheduling", "Medical Records & Images", "Accounts Receivable").
3.  **Building the Path:** If the LLM chooses, for example, "Scheduling":
    *   The system sanitizes this choice (uppercases, replaces spaces with underscores, etc.) to form a path segment, e.g., `SCHEDULING`.
    *   It then constructs a new hierarchical category key: `ROOT_SCHEDULING`.
4.  **Next Level:** The system fetches the rule from `hierarchical_classification_rules` where `category = "ROOT_SCHEDULING"`.
5.  **Recursive Process:** The prompt for `ROOT_SCHEDULING` will list the sub-options available under "Scheduling" (as defined in `settings.EMAIL_CATEGORIES`). The LLM makes another choice, the path extends (e.g., to `ROOT_SCHEDULING_NEW_APPOINTMENT`), and the process repeats.
6.  **Reaching a Leaf:** This continues until the `settings.EMAIL_CATEGORIES` structure indicates a final tag (a string) or a list of final tags to choose from. The prompt associated with the path leading to this leaf node will guide the LLM's final decision.

The `Category` key in the UI table directly corresponds to these system-generated keys.

## 5. Editing a Rule (LLM Prompt Template)

Clicking the "Edit" button next to a rule will take you to the edit form for that specific rule.

*   **Category (Read-only):**
    *   This field is displayed but cannot be changed.
    *   It is the unique identifier used by the system and is automatically generated based on the `EMAIL_CATEGORIES` structure. Changing it would break the classification logic for that path.
*   **Rule Set Name (Editable):**
    *   You can update this name to be more descriptive or to better reflect the rule's purpose.
*   **Rule Content (Editable - This is the LLM Prompt):**
    *   This is the most important field. It contains the instructions that will be sent to the AI.
    *   **CRITICAL:** The placeholder `{{EMAIL_CONTENT_PLACEHOLDER}}` **MUST** be present in the prompt. The system will replace this exact string with the content of the email being classified.
    *   **Tips for Writing Effective Prompts:**
        *   **Be Clear and Explicit:** Tell the AI exactly what you want it to do.
        *   **List Options Clearly:** The prompt must clearly list the exact options the LLM should choose from. These options **must** correspond to:
            *   The keys in the `settings.EMAIL_CATEGORIES` dictionary for the current path (if the next level is a dictionary of more sub-categories).
            *   The string items in the `settings.EMAIL_CATEGORIES` list for the current path (if the next level is a list of final tags).
        *   **Instruct on Response Format:** Clearly tell the LLM to respond with *ONLY* the chosen option name, without any extra explanation or pleasantries. E.g., "Respond with ONLY the chosen category name from the list above."
        *   **Context is Key:** The prompt should provide enough context for the LLM to make an informed decision based on the `{{EMAIL_CONTENT_PLACEHOLDER}}`.
        *   **Review Existing Prompts:** The prompts generated by `scripts/generate_hierarchical_rules_table.py` provide a good baseline. Use them as a reference.
        *   **Example Structure for a Choice:**
            ```
            You are an expert email classifier. The email content is provided below.
            {{EMAIL_CONTENT_PLACEHOLDER}}

            Based on the email content, choose EXACTLY ONE of the following options for 'XYZ Category':
            - OptionAlpha
            - OptionBeta
            - OptionGamma

            Respond with ONLY the chosen option name.
            Chosen Option:
            ```
    *   **Saving Changes:** When you save, the updated prompt is stored in the database and will be used by the classification system immediately for new emails processed down that specific path.

## 6. Example Scenario: How a Rule is Used

Let's trace a hypothetical email classification:

1.  **Email:** An email asking to book a new patient appointment.
2.  **Step 1: ROOT Classification**
    *   System Path: `[]` (empty)
    *   Category Key: `ROOT`
    *   The `Rule Content` for `ROOT` might be:
        ```
        You are an expert email classifier for a medical imaging company.
        Classify the following email content into ONE of the primary categories.
        {{EMAIL_CONTENT_PLACEHOLDER}}

        Choose from:
        - Scheduling
        - Medical Records & Images
        - Accounts Receivable

        Respond with ONLY the chosen category name.
        Selected Category:
        ```
    *   LLM analyzes the email and (hopefully) responds: `Scheduling`

3.  **Step 2: Scheduling Sub-Classification**
    *   System Path: `["Scheduling"]`
    *   Category Key: `ROOT_SCHEDULING` (generated from `ROOT` + `Scheduling`)
    *   The `Rule Content` for `ROOT_SCHEDULING` might be (assuming `settings.EMAIL_CATEGORIES["Scheduling"]` has keys like "New Appointment", "Reschedule Request"):
        ```
        The email is related to Scheduling.
        {{EMAIL_CONTENT_PLACEHOLDER}}

        Further classify this scheduling request by choosing ONE of the following:
        - New Appointment
        - Reschedule Request
        - Cancellation
        - General Scheduling Inquiry

        Respond with ONLY the chosen option name.
        Selected Scheduling Type:
        ```
    *   LLM analyzes again and responds: `New Appointment`

4.  **Step 3 (if applicable): Final Tag Selection**
    *   System Path: `["Scheduling", "New Appointment"]`
    *   Category Key: `ROOT_SCHEDULING_NEW_APPOINTMENT`
    *   If `settings.EMAIL_CATEGORIES["Scheduling"]["New Appointment"]` is a list like `["New Patient Appointment Tag", "Existing Patient Follow-up Tag"]`, the `Rule Content` for `ROOT_SCHEDULING_NEW_APPOINTMENT` would instruct the LLM to pick one from this list.
    *   LLM responds: `New Patient Appointment Tag`
    *   **Final Tag Applied:** `New Patient Appointment Tag`

## 7. Important Considerations

*   **Live Changes:** Once you save an edited rule, it's live in the system. Subsequent classifications that use that specific rule path will use the updated prompt.
*   **Consistency is KEY:**
    *   The options listed in your prompt **must exactly match** the keys (for dictionary/object next levels) or string values (for list next levels) in your `settings.EMAIL_CATEGORIES` structure for that specific classification path.
    *   If a prompt for `ROOT_SCHEDULING` lists "New Appt" as an option, but `settings.EMAIL_CATEGORIES["Scheduling"]` has a key "New Appointment", the system won't be able to proceed correctly if the LLM returns "New Appt". The LLM's output must be one of the exact keys/strings from `EMAIL_CATEGORIES`.
*   **Initial Population:** The `scripts/generate_hierarchical_rules_table.py` script is responsible for initially creating these rule entries and their basic prompt templates based on `EMAIL_CATEGORIES`. The UI is primarily for fine-tuning, updating, and correcting these prompts.
*   **`{{EMAIL_CONTENT_PLACEHOLDER}}`:** Cannot be stressed enough - this exact placeholder must exist in your prompt for the email content to be injected.

## 8. Troubleshooting & Verification

*   **Check Logs:** If classifications are not behaving as expected after a prompt update:
    *   The application logs (especially from `app/services/classification_service.py`) will show the path taken, the rule source used, and the LLM's prediction at each step. This can help identify if an LLM is not returning an expected option or if a prompt is missing.
*   **Test with Specific Emails:** After editing a prompt, it's good practice to test the classification with a few relevant email examples to ensure it's working as intended.
*   **Verify `EMAIL_CATEGORIES` Structure:** Ensure your prompts align with the structure defined in your `settings.EMAIL_CATEGORIES` environment variable (or its Python dictionary representation in `app.core.config`).

By carefully managing these LLM prompt templates, you can guide the AI to accurately classify emails according to your defined hierarchical structure. 