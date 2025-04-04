#!/usr/bin/env python3
"""
Script to train category-specific classifiers by generating rules from training data.
Uses OpenAI to analyze conversations in each category and generate classification rules.
Then evaluates these rules on the test set.
"""

import json
import os
import random
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv
import openai
from openai import OpenAI
import argparse
import httpx
import urllib3
from collections import Counter, defaultdict

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

def load_dataset(file_path: str) -> List[Dict[str, Any]]:
    """
    Load a dataset from a JSONL file.
    
    Args:
        file_path (str): Path to the JSONL file
        
    Returns:
        List[Dict[str, Any]]: List of conversations
    """
    conversations = []
    with open(file_path, 'r') as f:
        for line in f:
            conversations.append(json.loads(line))
    return conversations

def load_train_test_datasets() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Load both train and test datasets.
    
    Returns:
        Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]: Train and test datasets
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
    
    train_file = os.path.join(data_dir, 'category_dataset', 'train_dataset.jsonl')
    test_file = os.path.join(data_dir, 'category_dataset', 'test_dataset.jsonl')
    
    train_data = load_dataset(train_file)
    test_data = load_dataset(test_file)
    
    print(f"Loaded {len(train_data)} training conversations and {len(test_data)} test conversations")
    return train_data, test_data

def group_conversations_by_category(conversations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group conversations by their top-level category.
    
    Args:
        conversations (List[Dict[str, Any]]): List of conversations
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: Dictionary mapping categories to conversations
    """
    category_conversations = defaultdict(list)
    for conv in conversations:
        category = conv.get('top_level_category')
        if category and category != "Unknown":
            category_conversations[category].append(conv)
    return category_conversations

def extract_conversation_text(conversation: Dict[str, Any]) -> str:
    """
    Extract the text content from a conversation.
    
    Args:
        conversation (Dict[str, Any]): Conversation data
        
    Returns:
        str: Extracted text content
    """
    subject = conversation.get('subject', 'No Subject')
    
    # Extract content from messages
    messages = conversation.get('messages', [])
    content = "No Content"
    if messages:
        # Use the content from the first message
        content = messages[0].get('content', 'No Content')
    
    # Extract tags
    tags = [tag.get('name', '') for tag in conversation.get('tags', [])]
    
    return f"Subject: {subject}\nContent: {content}\nTags: {tags}"

def generate_category_rules(client: OpenAI, category: str, conversations: List[Dict[str, Any]], 
                          num_examples: int = 5) -> str:
    """
    Generate classification rules for a specific category using OpenAI.
    
    Args:
        client (OpenAI): OpenAI client
        category (str): Category to generate rules for
        conversations (List[Dict[str, Any]]): List of conversations in this category
        num_examples (int): Number of examples to use
        
    Returns:
        str: Generated classification rules
    """
    # Sample conversations if we have more than needed
    if len(conversations) > num_examples:
        sample_conversations = random.sample(conversations, num_examples)
    else:
        sample_conversations = conversations
    
    # Create prompt for rule generation
    prompt = f"""You are an expert at analyzing email conversations and creating classification rules.
I need you to analyze these {category} email conversations and create a set of clear, specific rules that can be used to identify if a new email belongs to the {category} category.

Here are {len(sample_conversations)} example conversations from the {category} category:

"""
    
    # Add example conversations
    for i, conv in enumerate(sample_conversations, 1):
        prompt += f"\nExample {i}:\n"
        prompt += extract_conversation_text(conv)
        prompt += "\n" + "-" * 40 + "\n"
    
    prompt += f"""
Based on these examples, please create a comprehensive set of rules for identifying {category} emails.
Your rules should be specific and actionable, focusing on:

1. Common subject lines and keywords
2. Typical content patterns and phrases
3. Specific tags that are often associated with this category
4. The main purpose or intent of these emails
5. Any unique characteristics that distinguish this category from others

Format your response as a numbered list of rules, with each rule being clear and specific.
For example:
1. If the subject contains [specific keywords], it's likely a {category} email
2. If the content mentions [specific topics], classify it as {category}
3. If the email is about [specific purpose], it belongs to the {category} category

Classification Rules for {category}:
"""
    
    # Get rules from OpenAI
    response = client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o'),
        messages=[
            {"role": "system", "content": f"You are an expert at analyzing {category} email conversations and creating classification rules."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=1000
    )
    
    return response.choices[0].message.content.strip()

def save_rules(rules: Dict[str, str], output_dir: str) -> None:
    """
    Save the generated rules to files.
    
    Args:
        rules (Dict[str, str]): Dictionary mapping categories to rules
        output_dir (str): Directory to save the rules
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # Save individual files for each category
    for category, rule_text in rules.items():
        # Replace special characters with underscores for safe filenames
        safe_category = category.lower().replace(' ', '_').replace('&', 'and').replace('/', '_')
        file_path = os.path.join(output_dir, f"{safe_category}_rules.txt")
        with open(file_path, 'w') as f:
            f.write(rule_text)
        print(f"Saved rules for {category} to {file_path}")
    
    # Save combined file
    combined_path = os.path.join(output_dir, "all_category_rules.txt")
    with open(combined_path, 'w') as f:
        for category, rule_text in rules.items():
            f.write(f"=== {category} RULES ===\n\n")
            f.write(rule_text)
            f.write("\n\n" + "=" * 50 + "\n\n")
    print(f"Saved all rules to {combined_path}")

def create_classification_prompt(rules: Dict[str, str], conversation: Dict[str, Any]) -> str:
    """
    Create a prompt for classifying a conversation using the generated rules.
    
    Args:
        rules (Dict[str, str]): Dictionary mapping categories to rules
        conversation (Dict[str, Any]): Conversation to classify
        
    Returns:
        str: Classification prompt
    """
    prompt = """You are an expert at classifying email conversations into categories.
I have provided you with a set of rules for each category and a conversation to classify.

Please analyze the conversation and determine which category it belongs to based on the rules.

"""
    
    # Add rules for each category
    for category, rule_text in rules.items():
        prompt += f"\n=== {category} RULES ===\n{rule_text}\n\n"
    
    # Add the conversation to classify
    prompt += "\nNow, classify this conversation into one of the categories based on the rules above:\n\n"
    prompt += extract_conversation_text(conversation)
    prompt += "\n\nCategory:"
    
    return prompt

def classify_with_rules(client: OpenAI, rules: Dict[str, str], conversation: Dict[str, Any]) -> Tuple[str, float]:
    """
    Classify a conversation using the generated rules.
    
    Args:
        client (OpenAI): OpenAI client
        rules (Dict[str, str]): Dictionary mapping categories to rules
        conversation (Dict[str, Any]): Conversation to classify
        
    Returns:
        Tuple[str, float]: Predicted category and confidence score
    """
    # Create prompt
    prompt = create_classification_prompt(rules, conversation)
    
    # Get classification from OpenAI
    response = client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o'),
        messages=[
            {"role": "system", "content": "You are an expert at classifying email conversations into categories. Respond with just the category name."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,
        max_tokens=10
    )
    
    # Extract prediction
    prediction = response.choices[0].message.content.strip()
    
    # Get confidence score (using logprobs if available)
    confidence = 1.0  # Default confidence
    if hasattr(response.choices[0], 'logprobs'):
        confidence = response.choices[0].logprobs
    
    return prediction, confidence

def evaluate_rules(client: OpenAI, rules: Dict[str, str], test_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluate the generated rules on the test set.
    
    Args:
        client (OpenAI): OpenAI client
        rules (Dict[str, str]): Dictionary mapping categories to rules
        test_data (List[Dict[str, Any]]): Test dataset
        
    Returns:
        Dict[str, Any]: Evaluation results
    """
    results = {
        'total': len(test_data),
        'correct': 0,
        'incorrect': 0,
        'accuracy': 0.0,
        'by_category': defaultdict(lambda: {'correct': 0, 'total': 0, 'accuracy': 0.0}),
        'confusion_matrix': defaultdict(lambda: defaultdict(int))
    }
    
    print("\nEvaluating rules on test set...")
    
    for i, conv in enumerate(test_data, 1):
        true_category = conv.get('top_level_category', 'Unknown')
        
        # Skip conversations with unknown category
        if true_category == 'Unknown':
            continue
        
        # Update category totals
        results['by_category'][true_category]['total'] += 1
        
        # Classify the conversation
        predicted_category, confidence = classify_with_rules(client, rules, conv)
        
        # Update confusion matrix
        results['confusion_matrix'][true_category][predicted_category] += 1
        
        # Check if prediction is correct
        is_correct = predicted_category == true_category
        if is_correct:
            results['correct'] += 1
            results['by_category'][true_category]['correct'] += 1
        else:
            results['incorrect'] += 1
        
        # Print progress
        if i % 5 == 0 or i == len(test_data):
            print(f"Processed {i}/{len(test_data)} test conversations...")
    
    # Calculate overall accuracy
    if results['total'] > 0:
        results['accuracy'] = results['correct'] / results['total']
    
    # Calculate per-category accuracy
    for category, stats in results['by_category'].items():
        if stats['total'] > 0:
            stats['accuracy'] = stats['correct'] / stats['total']
    
    return results

def print_evaluation_results(results: Dict[str, Any]) -> None:
    """
    Print the evaluation results.
    
    Args:
        results (Dict[str, Any]): Evaluation results
    """
    print("\nEvaluation Results:")
    print("-" * 60)
    print(f"Total test conversations: {results['total']}")
    print(f"Correct classifications: {results['correct']}")
    print(f"Incorrect classifications: {results['incorrect']}")
    print(f"Overall accuracy: {results['accuracy']:.2%}")
    
    print("\nAccuracy by category:")
    for category, stats in results['by_category'].items():
        print(f"{category}: {stats['correct']}/{stats['total']} ({stats['accuracy']:.2%})")
    
    print("\nConfusion Matrix:")
    print("-" * 60)
    
    # Get all categories
    categories = sorted(set(results['by_category'].keys()))
    
    # Print header
    print("True Category", end="\t")
    for category in categories:
        print(category, end="\t")
    print("Total")
    
    # Print matrix rows
    for true_category in categories:
        print(true_category, end="\t")
        row_total = 0
        for predicted_category in categories:
            count = results['confusion_matrix'][true_category][predicted_category]
            print(count, end="\t")
            row_total += count
        print(row_total)
    
    # Print column totals
    print("Total", end="\t")
    for predicted_category in categories:
        col_total = sum(results['confusion_matrix'][true_category][predicted_category] 
                        for true_category in categories)
        print(col_total, end="\t")
    print(results['total'])

def main():
    """Main function to train and evaluate category classifiers."""
    parser = argparse.ArgumentParser(description='Train and evaluate category classifiers')
    parser.add_argument('--num-examples', type=int, default=5, 
                        help='Number of examples to use for rule generation (default: 5)')
    parser.add_argument('--skip-evaluation', action='store_true', 
                        help='Skip evaluation on test set')
    parser.add_argument('--debug', action='store_true', 
                        help='Print prompts without making API calls')
    args = parser.parse_args()
    
    try:
        # Initialize OpenAI client
        client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            http_client=httpx.Client(verify=False)  # Disable SSL verification
        )
        
        # Load datasets
        train_data, test_data = load_train_test_datasets()
        
        # Group conversations by category
        train_by_category = group_conversations_by_category(train_data)
        
        # Print category distribution
        print("\nCategory distribution in training set:")
        print("-" * 60)
        for category, convs in train_by_category.items():
            print(f"{category}: {len(convs)} conversations")
        
        # Generate rules for each category
        print("\nGenerating classification rules for each category...")
        rules = {}
        
        for category, conversations in train_by_category.items():
            print(f"\nGenerating rules for {category}...")
            
            if args.debug:
                # Just print the prompt without making API call
                prompt = f"""You are an expert at analyzing email conversations and creating classification rules.
I need you to analyze these {category} email conversations and create a set of clear, specific rules that can be used to identify if a new email belongs to the {category} category.

Here are {min(args.num_examples, len(conversations))} example conversations from the {category} category:

"""
                
                # Add example conversations
                sample_conversations = random.sample(conversations, min(args.num_examples, len(conversations)))
                for i, conv in enumerate(sample_conversations, 1):
                    prompt += f"\nExample {i}:\n"
                    prompt += extract_conversation_text(conv)
                    prompt += "\n" + "-" * 40 + "\n"
                
                print("\nPrompt for rule generation:")
                print("-" * 60)
                print(prompt)
                print("-" * 60)
                
                # Use placeholder rules for debug mode
                rules[category] = f"Debug mode: Rules for {category} would be generated here."
            else:
                # Generate rules using OpenAI
                rules[category] = generate_category_rules(client, category, conversations, args.num_examples)
        
        # Save the rules
        data_dir = os.getenv('DATA_DIR')
        rules_dir = os.path.join(data_dir, 'category_rules')
        save_rules(rules, rules_dir)
        
        # Evaluate the rules on the test set
        if not args.skip_evaluation and not args.debug:
            results = evaluate_rules(client, rules, test_data)
            print_evaluation_results(results)
        
    except Exception as e:
        print(f"\nError during training and evaluation: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 