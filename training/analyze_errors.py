#!/usr/bin/env python3
"""
Script to analyze classification errors and suggest improvements to the rules.
Takes errors.csv as input and uses OpenAI to analyze each error and propose rule improvements.
"""

import json
import os
import csv
import argparse
from typing import Dict, List, Any
from dotenv import load_dotenv
import openai
from openai import OpenAI
import httpx
import urllib3
import random

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

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
            category_name = filename.replace('_rules.txt', '')
            
            # Convert safe filename back to original category name
            if 'and' in category_name:
                display_name = category_name.replace('and', '&')
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

def load_conversation(conv_id: str) -> Dict[str, Any]:
    """
    Load a conversation from the dataset.
    
    Args:
        conv_id (str): Conversation ID
        
    Returns:
        Dict[str, Any]: Conversation data
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
    
    # Load from the full dataset
    dataset_file = os.path.join(data_dir, 'category_dataset', 'all_categorized_conversations.jsonl')
    
    with open(dataset_file, 'r') as f:
        for line in f:
            conv = json.loads(line)
            if conv.get('id') == conv_id:
                return conv
    
    raise ValueError(f"Conversation {conv_id} not found in dataset")

def format_conversation_for_analysis(conv: Dict[str, Any]) -> str:
    """
    Format a conversation for analysis.
    
    Args:
        conv (Dict[str, Any]): Conversation data
        
    Returns:
        str: Formatted conversation text
    """
    subject = conv.get('subject', 'No Subject')
    messages = conv.get('messages', [])
    tags = [tag.get('name', '') for tag in conv.get('tags', [])]
    true_category = conv.get('top_level_category', 'Unknown')
    
    formatted = f"Conversation ID: {conv.get('id', 'Unknown')}\n"
    formatted += f"True Category: {true_category}\n"
    formatted += f"Subject: {subject}\n"
    formatted += f"Tags: {', '.join(tags)}\n\n"
    
    if messages:
        formatted += "Messages:\n"
        for msg in messages:
            content = msg.get('content', 'No Content')
            formatted += f"{content}\n"
            formatted += "-" * 80 + "\n"
    
    return formatted

def analyze_error(client: OpenAI, conv: Dict[str, Any], rules: Dict[str, str], 
                 predicted_category: str, true_category: str) -> Dict[str, str]:
    """
    Analyze a classification error using OpenAI.
    
    Args:
        client (OpenAI): OpenAI client
        conv (Dict[str, Any]): Conversation data
        rules (Dict[str, str]): Current classification rules
        predicted_category (str): Category predicted by the model
        true_category (str): True category
        
    Returns:
        Dict[str, str]: Analysis results containing rationale and proposed improvements
    """
    # Format the conversation
    conv_text = format_conversation_for_analysis(conv)
    
    # Create the analysis prompt
    prompt = f"""You are an expert at analyzing email classification errors. I will provide you with:
1. A conversation that was misclassified
2. The current classification rules for the two relevant categories
3. The predicted and true categories

Please analyze why the classification was incorrect and provide COMPLETE UPDATED CLASSIFIERS for BOTH categories.

CONVERSATION:
{conv_text}

CURRENT CLASSIFICATION RULES:
"""
    
    # Add only the rules for the two relevant categories
    relevant_categories = [predicted_category, true_category]
    for category in relevant_categories:
        if category in rules:
            prompt += f"\n=== {category} RULES ===\n{rules[category]}\n"
    
    prompt += f"""
PREDICTED CATEGORY: {predicted_category}
TRUE CATEGORY: {true_category}

Please provide:
1. A detailed analysis of why the classification was incorrect
2. COMPLETE UPDATED CLASSIFIERS for BOTH categories (not just improvements to existing rules)
3. Any patterns or keywords that were missed or misinterpreted

Format your response as:
ANALYSIS:
[Your analysis here]

UPDATED CLASSIFIERS:
[Complete updated classifier for {predicted_category}]

[Complete updated classifier for {true_category}]
"""
    
    # Print the prompt and wait for user input
    print("\n" + "="*80)
    print("PROMPT TO BE SENT TO OPENAI:")
    print("="*80)
    print(prompt)
    print("="*80)
    
    # Ask for y/n input
    while True:
        response = input("\nSend this prompt to OpenAI? (y/n): ").lower()
        if response in ['y', 'n']:
            break
        print("Please enter 'y' or 'n'")
    
    # If user chose not to send, return empty analysis
    if response == 'n':
        print("Skipping OpenAI analysis for this error.")
        return {
            'analysis': "Analysis skipped by user.",
            'improvements': "No improvements generated."
        }
    
    # Get analysis from OpenAI
    response = client.chat.completions.create(
        model=os.getenv('REASONING_MODEL', 'o3-mini'),
        messages=[
            {"role": "system", "content": "You are an expert at analyzing email classification errors and improving classification rules."},
            {"role": "user", "content": prompt}
        ]
    )
    
    # Parse the response
    analysis_text = response.choices[0].message.content
    
    # Split into analysis and improvements
    parts = analysis_text.split('\n\n')
    analysis = ""
    improvements = ""
    
    for part in parts:
        if part.startswith('ANALYSIS:'):
            analysis = part.replace('ANALYSIS:', '').strip()
        elif part.startswith('UPDATED CLASSIFIERS:'):
            improvements = part.replace('UPDATED CLASSIFIERS:', '').strip()
    
    return {
        'analysis': analysis,
        'improvements': improvements
    }

def count_done_tagged_errors(error_file: str) -> Dict[str, int]:
    """
    Count how many error emails have a "done" tag.
    
    Args:
        error_file (str): Path to the errors.csv file
        
    Returns:
        Dict[str, int]: Dictionary with counts of total errors and errors with "done" tag
    """
    if not os.path.exists(error_file):
        raise ValueError(f"Error file not found: {error_file}")
    
    # Initialize counters
    total_errors = 0
    done_tagged_errors = 0
    
    # Specific variations of "done" tag to look for
    done_tag_variations = ["done", "Done"]
    
    # Dictionary to track which variations were found
    tag_variation_counts = {tag: 0 for tag in done_tag_variations}
    
    # Open error file for reading
    with open(error_file, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            total_errors += 1
            conversation_id = row['Conversation ID']
            predicted_category = row['Predicted Category']
            true_category = row['True Category']
            
            try:
                # Load the conversation
                conv = load_conversation(conversation_id)
                
                # Get all tags
                tags = [tag.get('name', '') for tag in conv.get('tags', [])]
                
                # Check for each variation of "done" tag
                for done_tag in done_tag_variations:
                    if done_tag in tags:
                        tag_variation_counts[done_tag] += 1
                        done_tagged_errors += 1
                        print(f"Conversation {conversation_id} has '{done_tag}' tag")
                        print(f"  Predicted: {predicted_category}, True: {true_category}")
                        print(f"  All tags: {tags}")
                        break  # Only count once per conversation
            except Exception as e:
                print(f"Error loading conversation {conversation_id}: {str(e)}")
    
    # Print summary
    print("\nSummary:")
    print(f"Total errors: {total_errors}")
    print(f"Errors with 'done' tag: {done_tagged_errors}")
    print(f"Percentage: {done_tagged_errors / total_errors * 100:.2f}%")
    print("\nBreakdown by tag variation:")
    for tag, count in tag_variation_counts.items():
        print(f"  '{tag}': {count} conversations")
    
    return {
        'total_errors': total_errors,
        'done_tagged_errors': done_tagged_errors,
        'percentage': (done_tagged_errors / total_errors * 100) if total_errors > 0 else 0,
        'tag_variation_counts': tag_variation_counts
    }

def main():
    """Main function to analyze classification errors."""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Analyze classification errors and suggest improvements.')
        parser.add_argument('--conversation-id', '-c', type=str, help='Specific conversation ID to analyze')
        parser.add_argument('--count-done-tags', action='store_true', help='Count how many error emails have a "done" tag')
        args = parser.parse_args()
        
        # Get the OpenAI model version
        model_version = os.getenv('REASONING_MODEL', 'o3-mini')
        print(f"Using OpenAI model: {model_version}")
        
        # Initialize OpenAI client
        client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            http_client=httpx.Client(verify=False)  # Disable SSL verification
        )
        
        # Load rules
        rules_dir = os.path.join('training', 'training_rules')
        print(f"Loading rules from {rules_dir}...")
        rules = load_rules(rules_dir)
        
        # Load errors from CSV
        script_dir = os.path.dirname(os.path.abspath(__file__))
        error_file = os.path.join(script_dir, 'errors.csv')
        
        if not os.path.exists(error_file):
            raise ValueError(f"Error file not found: {error_file}")
        
        # If count-done-tags flag is set, just count and exit
        if args.count_done_tags:
            print("Counting error emails with 'done' tag...")
            counts = count_done_tagged_errors(error_file)
            print(f"Total errors: {counts['total_errors']}")
            print(f"Errors with 'done' tag: {counts['done_tagged_errors']}")
            print(f"Percentage: {counts['percentage']:.2f}%")
            return
        
        # Create output file for analysis (in append mode)
        analysis_file = os.path.join(script_dir, 'error_analysis.txt')
        
        # Open error file for reading
        with open(error_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            
            # If a specific conversation ID is provided, find and analyze only that error
            if args.conversation_id:
                conversation_id = args.conversation_id
                found = False
                
                for row in reader:
                    if row['Conversation ID'] == conversation_id:
                        found = True
                        print(f"\nAnalyzing error for conversation ID: {conversation_id}...")
                        
                        # Load the conversation
                        conv = load_conversation(row['Conversation ID'])
                        
                        # Analyze the error
                        analysis = analyze_error(
                            client, 
                            conv, 
                            rules,
                            row['Predicted Category'],
                            row['True Category']
                        )
                        
                        # Append analysis to file immediately
                        with open(analysis_file, 'a') as outfile:
                            outfile.write(f"\n{'='*80}\n")
                            outfile.write(f"ERROR FOR CONVERSATION ID: {conversation_id}\n")
                            outfile.write(f"True Category: {row['True Category']}\n")
                            outfile.write(f"Predicted Category: {row['Predicted Category']}\n\n")
                            outfile.write("ANALYSIS:\n")
                            outfile.write(analysis['analysis'])
                            outfile.write("\n\nUPDATED CLASSIFIERS:\n")
                            outfile.write(analysis['improvements'])
                            outfile.write("\n")
                        
                        print(f"Analysis saved to {analysis_file}")
                        break
                
                if not found:
                    print(f"Error: Conversation ID '{conversation_id}' not found in errors.csv")
                    return
            
            # If no specific conversation ID, analyze all errors
            else:
                total_errors = sum(1 for _ in reader)
                csvfile.seek(0)  # Reset file pointer
                next(reader)  # Skip header row
                
                for i, row in enumerate(reader, 1):
                    print(f"\nAnalyzing error {i} of {total_errors}...")
                    
                    # Load the conversation
                    conv = load_conversation(row['Conversation ID'])
                    
                    # Analyze the error
                    analysis = analyze_error(
                        client, 
                        conv, 
                        rules,
                        row['Predicted Category'],
                        row['True Category']
                    )
                    
                    # Append analysis to file immediately
                    with open(analysis_file, 'a') as outfile:
                        outfile.write(f"\n{'='*80}\n")
                        outfile.write(f"ERROR #{i}\n")
                        outfile.write(f"Conversation ID: {row['Conversation ID']}\n")
                        outfile.write(f"True Category: {row['True Category']}\n")
                        outfile.write(f"Predicted Category: {row['Predicted Category']}\n\n")
                        outfile.write("ANALYSIS:\n")
                        outfile.write(analysis['analysis'])
                        outfile.write("\n\nUPDATED CLASSIFIERS:\n")
                        outfile.write(analysis['improvements'])
                        outfile.write("\n")
                    
                    print(f"Analysis saved to {analysis_file}")
                    
                    # Ask user if they want to continue
                    if i < total_errors:  # If not the last error
                        while True:
                            response = input("\nContinue analysis? (y/n): ").lower()
                            if response in ['y', 'n']:
                                break
                            print("Please enter 'y' or 'n'")
                        if response == 'n':
                            print("\nAnalysis stopped by user")
                            break
                    else:
                        print("\nAll errors have been analyzed")
        
        print(f"\nAnalysis complete! Results saved to {analysis_file}")
        
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 