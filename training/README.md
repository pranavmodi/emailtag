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

**Output File**: The script generates a cleaned version of the conversations in `cleaned_data/cleaned_conversations.jsonl`. This file:
- Uses JSONL format (one JSON object per line)
- Contains processed conversations with cleaned HTML content
- Includes normalized email addresses and structured sender/recipient information
- Preserves conversation metadata (tags, status, etc.)
- Is used as input for subsequent steps in the pipeline

### 4. Create Category Dataset
The `create_category_dataset.py` script creates a balanced dataset for top-level category classification. Here's how it works:

1. **Input**: 
   - Uses cleaned conversations from `cleaned_data/cleaned_conversations.jsonl`
   - Uses category hierarchy from `EMAIL_CATEGORIES` environment variable

2. **Process**:
   - Maps each tag to its top-level category based on the hierarchy
   - For each conversation, determines its top-level category based on its tags
   - Creates a balanced dataset by sampling an equal number of conversations from each category
   - Splits the data into training and test sets (80/20 split by default)

3. **Output**:
   - Saves training dataset to `category_dataset/train_dataset.jsonl`
   - Saves test dataset to `category_dataset/test_dataset.jsonl`
   - Prints distribution statistics of categories in both splits

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

Train/Test Split Statistics:
Train set distribution:
- Scheduling: 80 conversations
- Medical Records & Images: 80 conversations
- Accounts Receivable: 80 conversations

Test set distribution:
- Scheduling: 20 conversations
- Medical Records & Images: 20 conversations
- Accounts Receivable: 20 conversations

Train dataset saved to: /home/fret/data/emailtag/category_dataset/train_dataset.jsonl
Test dataset saved to: /home/fret/data/emailtag/category_dataset/test_dataset.jsonl
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

### 5. Train and Evaluate Classifiers
The training and evaluation process is split into two scripts:

#### Training (`train_classifiers.py`)
This script generates classification rules for each category using the training data:

1. **Process**:
   - Loads the training dataset
   - Groups conversations by category
   - For each category:
     - Samples example conversations
     - Uses OpenAI to analyze examples and generate specific rules
     - Saves rules to individual files and a combined file

2. **Features**:
   - Customizable number of examples per category
   - Debug mode to preview prompts without making API calls
   - Option to skip evaluation
   - Safe filename handling for special characters

Run the training script:
```bash
# Basic usage (uses 5 examples per category)
./training/train_classifiers.py

# Use more examples for rule generation
./training/train_classifiers.py --num-examples 10

# Debug mode (prints prompts without making API calls)
./training/train_classifiers.py --debug

# Skip evaluation on test set
./training/train_classifiers.py --skip-evaluation
```

Output files:
- Individual rule files: `category_rules/[category]_rules.txt`
- Combined rules: `category_rules/all_category_rules.txt`

#### Evaluation (`evaluate_classifiers.py`)
This script evaluates the generated rules on the test set:

1. **Process**:
   - Loads the generated rules and test dataset
   - For each test conversation:
     - Creates a prompt with all rules and the conversation
     - Uses OpenAI to classify based on the rules
     - Compares prediction with true category
   - Generates detailed evaluation metrics

2. **Features**:
   - Confusion matrix showing classification errors
   - Per-category accuracy metrics
   - Debug mode to preview prompts
   - Customizable output location for results

Run the evaluation script:
```bash
# Basic usage (uses default rules directory)
./training/evaluate_classifiers.py

# Specify custom rules directory
./training/evaluate_classifiers.py --rules-dir /path/to/rules

# Debug mode (prints sample prompt)
./training/evaluate_classifiers.py --debug

# Save results to specific file
./training/evaluate_classifiers.py --output /path/to/results.json
```

Example evaluation output:
```
Evaluation Results:
------------------------------------------------------------
Total test conversations: 60
Correct classifications: 54
Incorrect classifications: 6
Overall accuracy: 90.00%

Accuracy by category:
Scheduling: 18/20 (90.00%)
Medical Records & Images: 19/20 (95.00%)
Accounts Receivable: 17/20 (85.00%)

Confusion Matrix:
------------------------------------------------------------
True Category    Scheduling   Med Records   Accounts   Total
Scheduling      18           1             1          20
Med Records     1            19            0          20
Accounts        1            1             18         20
Total          20           21            19         60
```

The evaluation results are also saved to a JSON file for further analysis.

### 6. Classify New Conversations
Classify new conversations using few-shot learning:
```