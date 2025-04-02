# Training Data Collection

This directory contains scripts for collecting and preparing training data from FrontApp conversations, and using that data to classify new conversations.

## Pipeline Overview

The complete pipeline consists of the following steps:

1. Fetch training emails from FrontApp
2. Create a structured training set
3. Clean and process conversations
4. Create a balanced category dataset
5. Analyze conversations and tag usage
6. Classify new conversations using few-shot learning

## Pipeline Steps

### 1. Fetch Training Emails
First, fetch emails tagged with specific tags from FrontApp:
```bash
# List all available tags
python3 fetch_ai_training_emails.py --list-tags

# Fetch conversations with a specific tag
python3 fetch_ai_training_emails.py --tag "AI:Training"
```

### 2. Create Training Set
Create a structured training set from the fetched conversations:
```bash
python3 create_training_set.py
```

### 3. Clean Conversations
Clean and process the raw conversation data:
```bash
# Process all conversations
python3 clean_conversations.py

# Debug mode - process only one conversation
python3 clean_conversations.py --debug

# Process a specific conversation
python3 clean_conversations.py --debug --conv-id "conv_123"
```

### 4. Create Category Dataset
The `create_category_dataset.py` script creates a balanced dataset for top-level category classification. Here's how it works:

1. **Input**: 
   - Uses cleaned conversations from `cleaned_data/cleaned_conversations.jsonl`
   - Uses category hierarchy from `EMAIL_CATEGORIES` environment variable

2. **Process**:
   - Maps each tag to its top-level category based on the hierarchy
   - For each conversation, determines its top-level category based on its tags
   - Creates a balanced dataset by sampling an equal number of conversations from each category
   - Default minimum samples per category is 100 (configurable)

3. **Output**:
   - Saves balanced dataset to `category_dataset/category_dataset.jsonl`
   - Each conversation includes its top-level category
   - Prints distribution statistics of categories in both full and balanced datasets

Example output:
```
Loading categories and conversations...
Loaded 1000 conversations

Category distribution in full dataset:
- Scheduling: 400 conversations
- Medical Records & Images: 300 conversations
- Accounts Receivable: 300 conversations

Creating balanced dataset with minimum 100 samples per category...
Sampling 100 conversations from each category

Final balanced dataset distribution:
- Scheduling: 100 conversations
- Medical Records & Images: 100 conversations
- Accounts Receivable: 100 conversations

Dataset saved to: /home/fret/data/emailtag/category_dataset/category_dataset.jsonl
```

Run the script:
```bash
# Use default minimum samples (100)
python3 create_category_dataset.py

# Specify custom minimum samples
python3 create_category_dataset.py --min-samples 200

# Or set via environment variable
MIN_SAMPLES=200 python3 create_category_dataset.py
```

You can also configure the minimum samples in your code:
```python
from training.create_category_dataset import create_balanced_dataset

# Create dataset with custom minimum samples
create_balanced_dataset(min_samples=200)
```

### 5. Analyze Conversations
The analysis script (`analyze_conversations.py`) uses the cleaned conversations from `cleaned_data/cleaned_conversations.jsonl` and the category hierarchy from the `EMAIL_CATEGORIES` environment variable to provide insights about the conversations.

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

Example output:
```
Loading categories and conversations...
Loaded 1000 conversations

Analyzing tag frequencies by category:
Scheduling:
  Appointment Request: 150
  Schedule Change: 75
  Cancellation: 50
Medical Records & Images:
  Image Request: 200
  Record Request: 100
Accounts Receivable:
  Payment:
    Payment Received: 80
    Payment Failed: 40
  Liens:
    ASL:
      Rad Lien: 60
      Tech Lien: 45
    PSL:
      Lien Modified: 30

Top 5 conversations with the most tags:
------------------------------------------------------------
Conversation ID: conv_123
Subject: Re: MRI Appointment and Payment
Number of tags: 4
Tags:
  - Appointment Request (Scheduling)
  - Payment Received (Accounts Receivable > Payment)
  - Image Request (Medical Records & Images)
  - Rad Lien (Accounts Receivable > Liens > ASL)
------------------------------------------------------------

Analysis of Untagged Conversations:
------------------------------------------------------------
Total conversations: 1000
Conversations with no valid tags: 50
Percentage untagged: 5.00%

Invalid tags found (not in hierarchy):
  - Old Tag: 25 occurrences
  - Deprecated Tag: 15 occurrences
------------------------------------------------------------
```

### 6. Classify Conversations
Classify new conversations using few-shot learning:
```bash
# Run classification on a random test conversation
python3 classify_conversation.py
```

The classification system uses few-shot learning with OpenAI's GPT-4 model to categorize emails into three main categories:
- Scheduling
- Medical Records & Images
- Accounts Receivable

The process works by:
1. Loading a balanced dataset of pre-categorized conversations
2. Selecting example conversations for each category
3. Creating a prompt with these examples and the new conversation
4. Using GPT-4 to classify the conversation based on its subject, content, and tags

You can also use the classification function in your code:
```python
from training.classify_conversation import classify_conversation
from openai import OpenAI

client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
conversation = {
    'subject': 'New Appointment Request',
    'content': '...',
    'tags': ['Appointment Request']
}

# Classify with default 2 examples per category
category, confidence = classify_conversation(client, conversation)

# Or specify number of examples per category
category, confidence = classify_conversation(client, conversation, examples_per_category=3)
```

## Data Formats

### Training Set Format
The training set is saved in JSONL format with the following structure:
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

### Category Dataset Format
The category dataset includes the top-level category for each conversation:
```json
{
    "id": "conversation_id",
    "subject": "email_subject",
    "content": "cleaned_email_content",
    "tags": [{"name": "tag1"}, {"name": "tag2"}],
    "top_level_category": "Scheduling"
}
```

## Requirements

- python-dotenv
- beautifulsoup4
- requests
- openai