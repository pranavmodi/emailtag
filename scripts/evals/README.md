# Email Tagging Test Suite

This directory contains a refactored and modular test suite for the Front email tagging system. The test suite has been split into multiple manageable files organized by category.

## File Structure

```
scripts/evals/
├── README.md                      # This documentation
├── run_tagging_tests.py          # Main test runner
├── test_utils.py                 # SMTP and Front API utilities
├── scenarios_billing.py          # Billing-related test scenarios
├── scenarios_scheduling.py       # Scheduling-related test scenarios
├── scenarios_medical_records.py  # Medical records test scenarios
├── scenarios_case_updates.py     # Case update test scenarios
├── scenarios_collections.py      # Collections test scenarios
└── test_frontapp_tagging.py      # Original monolithic script (for reference)
```

## Quick Start

1. **Run the main test script:**
   ```bash
   cd scripts/evals
   python run_tagging_tests.py
   ```

2. **Enable verbose mode for detailed output:**
   ```bash
   python run_tagging_tests.py --verbose
   ```

## Test Categories

The test scenarios are organized into the following categories:

### Billing & Finance (5 scenarios)
- Billing inquiries and balance requests
- Lien documentation
- Settlement negotiations
- Refund requests

### Scheduling & Appointments (8 scenarios)
- Appointment requests and cancellations
- Status checks and confirmations
- RX order tracking
- Multi-step appointment workflows
- OCR testing with PDF attachments

### Medical Records (4 scenarios)
- Records release requests
- CD and image requests
- Patient information corrections
- Study information corrections

### Case Updates (9 scenarios)
- Attorney changes
- Drop letters and pending drops
- Payment promises and commitments
- Settlement status updates
- Liability clearance tracking

### Collections (2 scenarios)
- Collections warnings
- Payment tracking issues

## Running Tests

When you run the main script, you'll see a categorized list of available scenarios. You can then choose:

1. **Run all scenarios:** Enter `all`
2. **Run by category:** Enter category name (e.g., `billing`, `scheduling`, `medical`)
3. **Run specific scenarios:** Enter comma-separated scenario numbers (e.g., `1,7,15`)

Example:
```
Enter scenario number(s) to test (comma-separated), category name, or 'all': billing
```

## Configuration

The test suite requires the following environment variables in your `.env` file:

### SMTP Configuration (Required for sending emails)
```
SMTP_HOST=your.smtp.host
SMTP_PORT=587
SENDER_EMAIL=your.email@domain.com
SENDER_PASSWORD=your_password
```

### Front API Configuration (Required for tag validation)
```
FRONT_API_BASE_URL=https://api2.frontapp.com
FRONT_AUTH_TOKEN=your_front_api_token
```

**Note:** If Front API variables are not configured, the script will only send emails without validating tags.

## Scenario Format

Each scenario follows this structure:

```python
"scenario_id": {
    "description": "Human-readable description",
    "subject": "Email subject line",
    "body_html": "HTML email body with placeholders",
    "recipient_email": "target@example.com",
    "expected_tags": ["Expected", "Tags"],
    "attachments": ["optional/file/path.pdf"],  # Optional
    "patient_id": "PRE123456",                  # Optional
    "is_multi_step": True,                      # Optional
    "steps": [...]                              # For multi-step scenarios
}
```

### Placeholders
- `{UNIQUE_TEST_ID}` - Replaced with unique test ID for tracking
- `{SENDER_EMAIL_PLACEHOLDER}` - Replaced with actual sender email
- `{PATIENT_ID}` - Replaced with patient ID if specified

## Adding New Scenarios

To add new test scenarios:

1. Choose the appropriate category file (or create a new one)
2. Add your scenario to the category's dictionary
3. Update the main runner to import your new category if needed
4. Follow the existing scenario format

Example:
```python
"30": {
    "description": "New test scenario",
    "subject": "Test subject",
    "body_html": "<p>Test body with {UNIQUE_TEST_ID}</p>",
    "recipient_email": "ai.benchd@gmail.com",
    "expected_tags": ["Expected Tag"]
}
```

## Test Results

The test runner provides detailed results including:
- Number of scenarios tested
- Pass/fail counts
- Success rate percentage
- Detailed failure information (missing/extra tags)
- Unique test IDs for tracking

## Special Features

### Multi-Step Scenarios
Some scenarios support multi-step email workflows with user interaction prompts.

### Attachment Support
Scenarios can include PDF attachments for OCR testing (e.g., scenario 29).

### Dynamic Content
Invoice numbers and appointment subjects can be randomized for certain scenarios.

### Verbose Mode
Use `--verbose` flag for detailed logging and debugging information.

## Troubleshooting

1. **Email sending fails:** Check SMTP configuration and credentials
2. **Tag validation fails:** Verify Front API configuration and permissions
3. **Attachments not found:** Check file paths relative to script location
4. **Scenarios not found:** Verify scenario IDs exist in the category files

## Legacy Script

The original monolithic script `test_frontapp_tagging.py` is preserved for reference but should not be used for new development. 