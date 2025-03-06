# EmailTag Testing Guide

This document provides instructions for testing the EmailTag application, focusing on the FrontApp webhook integration and email tagging functionality.

## Prerequisites

Before running the tests, make sure you have:

1. Set up the application following the instructions in README.md
2. Activated your virtual environment (`source venv/bin/activate`)
3. Started the application either with Docker Compose or manually
4. Created the necessary database tables with Alembic migrations

## Testing Tools

The repository includes two testing scripts:

1. `test_webhook.py` - Sends individual test emails to the webhook endpoint
2. `generate_test_data.sh` - Sends multiple test emails with various templates

## Single Email Testing with `test_webhook.py`

This script allows you to send individual test emails to the FrontApp webhook endpoint with various configurations.

### Basic Usage

```bash
./test_webhook.py
```

This will send a single random email template to the default endpoint (http://localhost:8000/api/v1/webhooks/frontapp).

### Advanced Options

```bash
./test_webhook.py [OPTIONS]
```

Available options:

- `--url URL` - Specify a custom webhook URL
- `--template INDEX` - Use a specific email template (0-6)
- `--sender EMAIL` - Use a specific sender email address
- `--no-sign` - Don't sign the payload with HMAC
- `--no-html` - Don't include HTML content
- `--count N` - Send multiple emails
- `--raw` - Use the complex email template that includes raw email data

### Email Templates

The script includes the following email templates, each designed to test different tag categories:

0. Billing inquiry (expected tag: "billing")
1. Appointment rescheduling (expected tag: "scheduling")
2. Urgent results request (expected tags: "results", "urgent")
3. Insurance verification (expected tag: "insurance")
4. Technical issue report (expected tag: "technical")
5. General questions (expected tag: "general")
6. Complex email with raw email data (expected tags: "results", "insurance", "urgent")

### Examples

Send a specific template:
```bash
./test_webhook.py --template 2
```

Send 5 random emails:
```bash
./test_webhook.py --count 5
```

Send a complex email with raw email data for testing mail-parser:
```bash
./test_webhook.py --raw
```

## Batch Testing with `generate_test_data.sh`

This script generates multiple test emails with different templates to simulate a realistic batch of incoming emails.

### Basic Usage

```bash
./generate_test_data.sh
```

This will send 10 emails (a mix of all templates) to the default endpoint.

### Advanced Options

```bash
./generate_test_data.sh [OPTIONS]
```

Available options:

- `--url URL` - Specify a custom webhook URL
- `--count N` - Total number of emails to send (default: 10)
- `--no-sign` - Don't sign the payloads with HMAC
- `--raw` - Use only the complex email template with raw email data

### Examples

Send 20 varied emails:
```bash
./generate_test_data.sh --count 20
```

Send 5 complex emails with raw email data:
```bash
./generate_test_data.sh --count 5 --raw
```

## Verifying Results

After sending test emails, you can verify the results by:

1. Checking the application logs for successful processing
2. Querying the database to see if emails were stored and tagged correctly
3. Monitoring the Celery tasks via Flower (http://localhost:5555)

Example PostgreSQL query to check tagged emails:

```sql
SELECT e.id, e.subject, e.processed, string_agg(t.name, ', ') as tags
FROM email e
LEFT JOIN email_tag_association eta ON e.id = eta.email_id
LEFT JOIN tag t ON eta.tag_id = t.id
GROUP BY e.id, e.subject, e.processed
ORDER BY e.created_at DESC;
```

## Troubleshooting

If you encounter issues:

1. Make sure your application is running and accessible at the webhook URL
2. Check the DEBUG setting in your .env file (set to True for detailed logs)
3. Look for errors in the application logs
4. Verify the database connection is working properly
5. Ensure RabbitMQ and Celery workers are running 