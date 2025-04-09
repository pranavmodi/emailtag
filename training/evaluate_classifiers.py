#!/usr/bin/env python3
"""
Script to evaluate category classifiers using previously generated rules.
Loads rules from files and evaluates them on the test set.
"""

import json
import os
import argparse
from typing import Dict, List, Any, Tuple
from dotenv import load_dotenv
import openai
from openai import OpenAI
import httpx
import urllib3
from collections import Counter, defaultdict
import csv
from datetime import datetime
import random

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

def load_test_dataset() -> List[Dict[str, Any]]:
    """
    Load the test dataset.
    
    Returns:
        List[Dict[str, Any]]: Test dataset
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
    
    # Use the full categorized dataset instead of just the test split
    test_file = os.path.join(data_dir, 'category_dataset', 'all_categorized_conversations.jsonl')
    test_data = load_dataset(test_file)
    
    # Randomize the dataset
    random.shuffle(test_data)
    
    print(f"Loaded and randomized {len(test_data)} conversations for evaluation")
    return test_data

def find_conversation_by_id(conversation_id: str) -> Dict[str, Any]:
    """
    Find a conversation by its ID in the dataset.
    
    Args:
        conversation_id (str): The ID of the conversation to find
        
    Returns:
        Dict[str, Any]: The conversation data or None if not found
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
    
    # Use the full categorized dataset
    dataset_file = os.path.join(data_dir, 'category_dataset', 'all_categorized_conversations.jsonl')
    
    with open(dataset_file, 'r') as f:
        for line in f:
            conversation = json.loads(line)
            if conversation.get('id') == conversation_id:
                return conversation
    
    return None

def load_rules(rules_dir: str) -> Dict[str, str]:
    """
    Load classification rules from files.
    
    Args:
        rules_dir (str): Directory containing rule files
        
    Returns:
        Dict[str, str]: Dictionary mapping categories to rules
    """
    rules = {}
    
    # Check if the directory exists
    if not os.path.exists(rules_dir):
        raise ValueError(f"Rules directory not found: {rules_dir}")
    
    # Load individual rule files
    for filename in os.listdir(rules_dir):
        if filename.endswith('_rules.txt') and not filename.startswith('all_'):
            # Extract category from filename
            # Handle safe filenames (with 'and' instead of '&')
            category_name = filename.replace('_rules.txt', '')
            
            # Convert safe filename back to original category name
            if 'and' in category_name:
                # Replace 'and' with '&' for display purposes
                display_name = category_name.replace('and', '&')
                # Also handle other replacements if needed
                display_name = display_name.replace('_', ' ').title()
            else:
                display_name = category_name.replace('_', ' ').title()
            
            # Load rule file
            file_path = os.path.join(rules_dir, filename)
            with open(file_path, 'r') as f:
                rules[display_name] = f.read()
            
            print(f"Loaded rules for {display_name} from {file_path}")
    
    if not rules:
        raise ValueError(f"No rule files found in {rules_dir}")
    
    return rules

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

def create_classification_prompt(rules: Dict[str, str], conversation: Dict[str, Any]) -> str:
    """
    Create a prompt for classifying a conversation using the rules.
    
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
    Classify a conversation using the rules.
    
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
        ]
    )
    
    # Extract prediction
    prediction = response.choices[0].message.content.strip()
    
    # Get confidence score (using logprobs if available)
    confidence = 1.0  # Default confidence
    if hasattr(response.choices[0], 'logprobs'):
        confidence = response.choices[0].logprobs
    
    return prediction, confidence

def format_conversation_for_display(conv: Dict[str, Any]) -> str:
    """
    Format a conversation for human-readable display.
    
    Args:
        conv (Dict[str, Any]): Conversation data
        
    Returns:
        str: Formatted conversation text
    """
    subject = conv.get('subject', 'No Subject')
    messages = conv.get('messages', [])
    tags = [tag.get('name', '') for tag in conv.get('tags', [])]
    
    formatted = f"\nSubject: {subject}\n"
    formatted += f"Tags: {', '.join(tags)}\n"
    
    if messages:
        formatted += "\nMessages:\n"
        for msg in messages:
            content = msg.get('content', 'No Content')
            formatted += f"{content}\n"
            formatted += "-" * 80 + "\n"
    
    return formatted

def evaluate_rules(client: OpenAI, rules: Dict[str, str], test_data: List[Dict[str, Any]], debug: bool = False, batch_size: int = 500) -> Dict[str, Any]:
    """
    Evaluate the rules on the test set.
    
    Args:
        client (OpenAI): OpenAI client
        rules (Dict[str, str]): Dictionary mapping categories to rules
        test_data (List[Dict[str, Any]]): Test dataset
        debug (bool): Whether to show detailed error information
        batch_size (int): Number of emails to process before pausing for user input
        
    Returns:
        Dict[str, Any]: Evaluation results
    """
    results = {
        'total': len(test_data),
        'correct': 0,
        'incorrect': 0,
        'accuracy': 0.0,
        'by_category': defaultdict(lambda: {'correct': 0, 'total': 0, 'accuracy': 0.0, 'incorrect_predictions': defaultdict(int)}),
        'confusion_matrix': defaultdict(lambda: defaultdict(int)),
        'errors': []  # Store error details
    }
    
    print("\nEvaluating rules on test set...")
    
    # Use fixed error file in the same directory as the script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    error_file = os.path.join(script_dir, 'errors.csv')
    
    # Initialize error file with headers
    with open(error_file, 'w', newline='') as csvfile:
        error_writer = csv.writer(csvfile)
        error_writer.writerow(['Conversation ID', 'Predicted Category', 'True Category'])
    
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
            # Update incorrect predictions for this category
            results['by_category'][true_category]['incorrect_predictions'][predicted_category] += 1
            
            # Store error details
            results['errors'].append({
                'id': conv.get('id', 'Unknown'),
                'true_category': true_category,
                'predicted_category': predicted_category
            })
            
            # Display error details and wait for user input only in debug mode
            if debug:
                print("\n" + "="*80)
                print(f"ERROR #{results['incorrect']}")
                print(f"Conversation ID: {conv.get('id', 'Unknown')}")
                print(f"True Category: {true_category}")
                print(f"Predicted Category: {predicted_category}")
                print("\nConversation Details:")
                print(format_conversation_for_display(conv))
                input("\nPress Enter to continue to next error...")
        
        # Print progress every batch_size conversations
        if i % batch_size == 0 or i == len(test_data):
            current_accuracy = results['correct'] / i
            print(f"\nProgress: {i}/{len(test_data)} conversations processed")
            print(f"Current accuracy: {current_accuracy:.2%}")
            print("Current category distribution:")
            for category, stats in results['by_category'].items():
                if stats['total'] > 0:
                    cat_accuracy = stats['correct'] / stats['total']
                    print(f"{category}: {stats['correct']}/{stats['total']} ({cat_accuracy:.2%})")
                    if stats['incorrect_predictions']:
                        print("  Incorrectly predicted as:")
                        for pred_cat, count in stats['incorrect_predictions'].items():
                            print(f"    {pred_cat}: {count}")
            
            # Write current errors to file
            with open(error_file, 'w', newline='') as csvfile:
                error_writer = csv.writer(csvfile)
                error_writer.writerow(['Conversation ID', 'Predicted Category', 'True Category'])
                for error in results['errors']:
                    error_writer.writerow([
                        error['id'],
                        error['predicted_category'],
                        error['true_category']
                    ])
            
            # Pause for user input after every batch_size conversations
            if i < len(test_data):  # Don't pause at the end
                while True:
                    response = input("\nContinue evaluation? (y/n): ").lower()
                    if response in ['y', 'n']:
                        break
                    print("Please enter 'y' or 'n'")
                if response == 'n':
                    print("\nEvaluation stopped by user")
                    return results
    
    # Calculate overall accuracy
    if results['total'] > 0:
        results['accuracy'] = results['correct'] / results['total']
    
    # Calculate per-category accuracy
    for category, stats in results['by_category'].items():
        if stats['total'] > 0:
            stats['accuracy'] = stats['correct'] / stats['total']
    
    print(f"\nError details saved to {error_file}")
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
    
    # Calculate column widths for better formatting
    category_width = max(len(category) for category in categories)
    category_width = max(category_width, len("True Category"))
    
    # Print header
    print(f"{'True Category':<{category_width}}", end="  ")
    for category in categories:
        print(f"{category:<{len(category)}}", end="  ")
    print("Total")
    
    # Print separator line
    print("-" * (category_width + sum(len(cat) + 2 for cat in categories) + 8))
    
    # Print matrix rows
    for true_category in categories:
        print(f"{true_category:<{category_width}}", end="  ")
        row_total = 0
        for predicted_category in categories:
            count = results['confusion_matrix'][true_category][predicted_category]
            print(f"{count:<{len(predicted_category)}}", end="  ")
            row_total += count
        print(row_total)
    
    # Print separator line
    print("-" * (category_width + sum(len(cat) + 2 for cat in categories) + 8))
    
    # Print column totals
    print(f"{'Total':<{category_width}}", end="  ")
    for predicted_category in categories:
        col_total = sum(results['confusion_matrix'][true_category][predicted_category] 
                        for true_category in categories)
        print(f"{col_total:<{len(predicted_category)}}", end="  ")
    print(results['total'])

def save_evaluation_results(results: Dict[str, Any], output_file: str) -> None:
    """
    Save the evaluation results to a file.
    
    Args:
        results (Dict[str, Any]): Evaluation results
        output_file (str): Path to save the results
    """
    # Convert defaultdict to regular dict for JSON serialization
    serializable_results = {
        'total': results['total'],
        'correct': results['correct'],
        'incorrect': results['incorrect'],
        'accuracy': results['accuracy'],
        'by_category': {k: dict(v) for k, v in results['by_category'].items()},
        'confusion_matrix': {k: dict(v) for k, v in results['confusion_matrix'].items()}
    }
    
    with open(output_file, 'w') as f:
        json.dump(serializable_results, f, indent=2)
    
    print(f"\nEvaluation results saved to {output_file}")

def evaluate_single_conversation(client: OpenAI, rules: Dict[str, str], conversation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluate a single conversation using the rules.
    
    Args:
        client (OpenAI): OpenAI client
        rules (Dict[str, str]): Dictionary mapping categories to rules
        conversation (Dict[str, Any]): Conversation to evaluate
        
    Returns:
        Dict[str, Any]: Evaluation results for the single conversation
    """
    true_category = conversation.get('top_level_category', 'Unknown')
    
    # Skip conversations with unknown category
    if true_category == 'Unknown':
        print(f"Warning: Conversation {conversation.get('id', 'Unknown')} has unknown category")
        return None
    
    # Classify the conversation
    predicted_category, confidence = classify_with_rules(client, rules, conversation)
    
    # Check if prediction is correct
    is_correct = predicted_category == true_category
    
    # Create results for this single conversation
    results = {
        'id': conversation.get('id', 'Unknown'),
        'true_category': true_category,
        'predicted_category': predicted_category,
        'is_correct': is_correct,
        'confidence': confidence
    }
    
    # Print results
    print("\nEvaluation Results for Conversation:")
    print("-" * 60)
    print(f"Conversation ID: {results['id']}")
    print(f"True Category: {results['true_category']}")
    print(f"Predicted Category: {results['predicted_category']}")
    print(f"Correct: {'Yes' if results['is_correct'] else 'No'}")
    
    # Handle None confidence value
    if results['confidence'] is not None:
        print(f"Confidence: {results['confidence']:.2f}")
    else:
        print("Confidence: N/A")
    
    # Print conversation details
    print("\nConversation Details:")
    print(format_conversation_for_display(conversation))
    
    return results

def main():
    """Main function to evaluate category classifiers."""
    parser = argparse.ArgumentParser(description='Evaluate category classifiers using existing rules')
    parser.add_argument('--rules-dir', type=str, 
                        help='Directory containing rule files (default: training/training_rules)')
    parser.add_argument('--debug', action='store_true', 
                        help='Print prompts without making API calls and show detailed error information')
    parser.add_argument('--output', type=str, 
                        help='Path to save evaluation results (default: DATA_DIR/evaluation_results.json)')
    parser.add_argument('--batch-size', type=int, default=500,
                        help='Number of emails to process before pausing for user input (default: 500)')
    parser.add_argument('--conversation-id', type=str,
                        help='Evaluate a specific conversation by ID')
    args = parser.parse_args()
    
    try:
        # Initialize OpenAI client
        client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            http_client=httpx.Client(verify=False)  # Disable SSL verification
        )
        
        # Print batch size
        print(f"Using batch size: {args.batch_size}")
        
        # Print OpenAI model
        model = os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o')
        print(f"Using OpenAI model: {model}")
        
        # Get data directory
        data_dir = os.getenv('DATA_DIR')
        if not data_dir:
            raise ValueError("DATA_DIR environment variable not set")
        
        # Set default rules directory to training/training_rules
        rules_dir = args.rules_dir or os.path.join('training', 'training_rules')
        
        # Load rules
        print(f"Loading rules from {rules_dir}...")
        rules = load_rules(rules_dir)
        
        # Check if we're evaluating a specific conversation
        if args.conversation_id:
            print(f"Looking for conversation with ID: {args.conversation_id}")
            conversation = find_conversation_by_id(args.conversation_id)
            
            if conversation is None:
                print(f"Error: Conversation with ID {args.conversation_id} not found")
                return
            
            # Evaluate the single conversation
            if args.debug:
                # Just print a sample prompt without making API call
                print("\nSample classification prompt:")
                print("-" * 60)
                prompt = create_classification_prompt(rules, conversation)
                print(prompt)
                print("-" * 60)
                print("Debug mode: Skipping evaluation")
            else:
                results = evaluate_single_conversation(client, rules, conversation)
                
                # Save results if output path is provided
                if args.output and results:
                    with open(args.output, 'w') as f:
                        json.dump(results, f, indent=2)
                    print(f"\nEvaluation results saved to {args.output}")
        else:
            # Load test dataset
            test_data = load_test_dataset()
            
            # Evaluate the rules on the test set
            if args.debug:
                # Just print a sample prompt without making API call
                print("\nSample classification prompt:")
                print("-" * 60)
                sample_conv = test_data[0]
                prompt = create_classification_prompt(rules, sample_conv)
                print(prompt)
                print("-" * 60)
                print("Debug mode: Skipping evaluation")
            else:
                results = evaluate_rules(client, rules, test_data, debug=args.debug, batch_size=args.batch_size)
                print_evaluation_results(results)
                
                # Save results if output path is provided
                if args.output:
                    save_evaluation_results(results, args.output)
                else:
                    output_file = os.path.join(data_dir, 'evaluation_results.json')
                    save_evaluation_results(results, output_file)
        
    except Exception as e:
        print(f"\nError during evaluation: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 