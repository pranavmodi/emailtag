#!/bin/bash

# EmailTag test data generator script
# This script sends multiple test emails to simulate a batch of incoming emails

# Check if virtual environment is activated
if [[ "$VIRTUAL_ENV" == "" ]]; then
    echo "Virtual environment not activated. Activating now..."
    source venv/bin/activate || { echo "Failed to activate virtual environment. Please run 'source venv/bin/activate' first."; exit 1; }
fi

# Default values
WEBHOOK_URL="http://localhost:8000/api/v1/webhooks/frontapp"
COUNT=10
SIGN=true
USE_RAW=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            WEBHOOK_URL="$2"
            shift 2
            ;;
        --count)
            COUNT="$2"
            shift 2
            ;;
        --no-sign)
            SIGN=false
            shift
            ;;
        --raw)
            USE_RAW=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--url URL] [--count N] [--no-sign] [--raw]"
            exit 1
            ;;
    esac
done

echo "=== EmailTag Test Data Generator ==="
echo "Webhook URL: $WEBHOOK_URL"
echo "Number of emails: $COUNT"
echo "Signing payloads: $SIGN"
echo "Using raw email data: $USE_RAW"
echo "=================================="

# Create a mixture of templates for realistic testing
if $USE_RAW; then
    # If raw mode, use template 6 for all emails
    python test_webhook.py --url "$WEBHOOK_URL" --count "$COUNT" --raw $(if ! $SIGN; then echo "--no-sign"; fi)
else
    # Send a varied mix of emails
    for template in {0..6}; do
        # Calculate how many of each template to send
        template_count=$((COUNT / 7))
        if [ $template -eq 0 ]; then
            # Add remainder to first template
            template_count=$((template_count + COUNT % 7))
        fi
        
        if [ $template_count -gt 0 ]; then
            echo "Sending $template_count emails with template $template..."
            python test_webhook.py --url "$WEBHOOK_URL" --template "$template" --count "$template_count" $(if ! $SIGN; then echo "--no-sign"; fi)
        fi
    done
fi

echo "All test emails sent successfully!" 