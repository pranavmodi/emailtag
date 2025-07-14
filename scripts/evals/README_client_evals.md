# Client Evaluations Test Suite

This directory contains client-specific evaluation scenarios for testing the Front email tagging system's accuracy on real-world client emails.

## Files

- `scenarios_client_evals.py` - Contains client evaluation test scenarios
- `run_client_evals.py` - Dedicated test runner for client evaluations
- `README_client_evals.md` - This documentation file

## Usage

### Running Client Evaluations

You can run client evaluations in two ways:

#### 1. Using the dedicated client eval runner:
```bash
python run_client_evals.py
```

#### 2. Using the main test runner:
```bash
python run_tagging_tests.py
# Then select "client" or "client evaluations" when prompted
```

### Verbose Mode

For detailed output, use the verbose flag:
```bash
python run_client_evals.py --verbose
# or
python run_client_evals.py -v
```

## Current Scenarios

### Scenario 1: Apt Status Req - Client following up on imaging status
- **Subject**: "I am following up to see if our client got imaging's done."
- **Content**: Following up on client imaging status with patient information
- **Expected Tag**: `["Apt Status Req"]`
- **Category**: Scheduling > RX > Apt Status Req

## Adding New Client Scenarios

To add new client evaluation scenarios:

1. Edit `scenarios_client_evals.py`
2. Add a new entry to the `CLIENT_EVAL_SCENARIOS` dictionary
3. Follow the existing pattern:

```python
"2": {
    "description": "Brief description of the scenario",
    "subject": "Email subject line",
    "body_html": (
        "<p>HTML formatted email body content</p>"
        "<p>Test ID: {UNIQUE_TEST_ID}</p>"
    ),
    "expected_tags": ["Expected Tag Name"]
}
```

## Testing Process

1. **Email Sending**: The system sends a test email via SMTP to the configured Front webhook
2. **Processing Wait**: Waits 45 seconds for the email to be processed and tagged
3. **Validation**: Checks if the actual tags match the expected tags
4. **Reporting**: Provides detailed results including success/failure status and tag comparisons

## Configuration

The test requires the same configuration as the main test suite:
- SMTP credentials for sending test emails
- Front API credentials for tag validation (optional - will skip validation if not configured)

## Expected Output

The test runner will display:
- Available scenarios
- Test execution progress
- Tag validation results
- Summary statistics with success rate

## Integration

Client evaluations are also integrated into the main test runner (`run_tagging_tests.py`) and can be selected by choosing "client", "client evaluations", or "client_evals" when prompted for a category. 