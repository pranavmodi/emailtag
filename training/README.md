# Training Data Collection

This directory contains scripts for collecting and preparing training data from FrontApp conversations.

## Files

- `fetch_ai_training_emails.py`: Script to fetch emails tagged with specific tags from FrontApp
- `create_training_set.py`: Script to create a structured training set from FrontApp conversations
- `analyze_conversations.py`: Script to analyze conversation data and tag usage

## Usage

1. List all available tags:
```bash
python3 fetch_ai_training_emails.py --list-tags
```

2. Fetch conversations with a specific tag:
```bash
python3 fetch_ai_training_emails.py --tag "AI:Training"
```

3. Create a training set from tagged conversations:
```bash
python3 create_training_set.py
```

4. Analyze conversations and tag usage:
```bash
# Run all analyses
python3 analyze_conversations.py

# Analyze only tag frequencies
python3 analyze_conversations.py --mode tag_counts

# Show top conversations with most tags
python3 analyze_conversations.py --mode top_tagged

# Show top 10 conversations with most tags
python3 analyze_conversations.py --mode top_tagged --top-n 10

# Analyze untagged conversations
python3 analyze_conversations.py --mode untagged
```

The analysis script provides several insights:
- Tag frequency analysis by category
- Top conversations with the most tags
- Conversations with no valid tags from the hierarchy
- Statistics about invalid or deprecated tags

## Output

The training set will be saved in JSONL format with the following structure:
```json
{
    "id": "conversation_id",
    "subject": "email_subject",
    "content": "cleaned_email_content",
    "created_at": "timestamp",
    "status": "conversation_status",
    "metadata": {
        "sender": "sender_name",
        "recipients": ["recipient1", "recipient2"],
        "tags": ["tag1", "tag2"]
    }
}
```

## Requirements

- python-dotenv
- beautifulsoup4
- requests 