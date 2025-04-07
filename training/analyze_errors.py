#!/usr/bin/env python3
"""
Script to analyze classification errors and suggest improvements to the rules.
Takes errors.csv as input and uses OpenAI to analyze each error and propose rule improvements.
"""

import json
import os
import csv
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
2. The current classification rules
3. The predicted and true categories

Please analyze why the classification was incorrect and suggest improvements to the rules.

CONVERSATION:
{conv_text}

CURRENT CLASSIFICATION RULES:
"""
    
    # Add current rules
    for category, rule_text in rules.items():
        prompt += f"\n=== {category} RULES ===\n{rule_text}\n"
    
    prompt += f"""
PREDICTED CATEGORY: {predicted_category}
TRUE CATEGORY: {true_category}

Please provide:
1. A detailed analysis of why the classification was incorrect
2. Specific improvements to the rules that would prevent this type of error
3. Any patterns or keywords that were missed or misinterpreted

Format your response as:
ANALYSIS:
[Your analysis here]

IMPROVEMENTS:
[Your suggested improvements here]
"""
    
    # Print the prompt and wait for user input
    print("\n" + "="*80)
    print("PROMPT TO BE SENT TO OPENAI:")
    print("="*80)
    print(prompt)
    print("="*80)
    input("\nPress Enter to send this prompt to OpenAI (Ctrl+C to cancel)...")
    
    # Get analysis from OpenAI
    response = client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o'),
        messages=[
            {"role": "system", "content": "You are an expert at analyzing email classification errors and improving classification rules."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
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
        elif part.startswith('IMPROVEMENTS:'):
            improvements = part.replace('IMPROVEMENTS:', '').strip()
    
    return {
        'analysis': analysis,
        'improvements': improvements
    }

def main():
    """Main function to analyze classification errors."""
    try:
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
        
        # Create output file for analysis (in append mode)
        analysis_file = os.path.join(script_dir, 'error_analysis.txt')
        
        # Open error file for reading
        with open(error_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
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
                    outfile.write("\n\nIMPROVEMENTS:\n")
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
        
        print(f"\nAnalysis complete! Results saved to {analysis_file}")
        
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 