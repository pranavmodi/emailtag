#!/usr/bin/env python3
"""
Script to analyze all patterns of classification errors between categories.
This script identifies all unique error patterns in the errors.csv file and analyzes each one.
"""

import os
import sys
import csv
import argparse
from collections import defaultdict
from dotenv import load_dotenv
from openai import OpenAI
import httpx
import urllib3

# Import from the same directory
from analyze_errors import load_rules, analyze_category_error_pattern

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

def find_error_patterns(error_file: str) -> dict:
    """
    Find all unique error patterns in the errors.csv file.
    
    Args:
        error_file (str): Path to the errors.csv file
        
    Returns:
        dict: Dictionary mapping error patterns to lists of conversation IDs
    """
    if not os.path.exists(error_file):
        raise ValueError(f"Error file not found: {error_file}")
    
    # Dictionary to store error patterns
    error_patterns = defaultdict(list)
    
    # Open error file for reading
    with open(error_file, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        
        for row in reader:
            from_category = row['Predicted Category']
            to_category = row['True Category']
            conversation_id = row['Conversation ID']
            
            # Create a key for the error pattern
            pattern_key = f"{from_category} → {to_category}"
            
            # Add the conversation ID to the list for this pattern
            error_patterns[pattern_key].append(conversation_id)
    
    return error_patterns

def main():
    """Main function to analyze all error patterns."""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Analyze all patterns of classification errors between categories.')
        parser.add_argument('--max-examples', type=int, default=3, 
                           help='Maximum number of examples to analyze per pattern (default: 3)')
        parser.add_argument('--rules-dir', type=str, default='../training_rules',
                           help='Directory containing rule files (default: ../training_rules)')
        parser.add_argument('--min-errors', type=int, default=2,
                           help='Minimum number of errors required to analyze a pattern (default: 2)')
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
        print(f"Loading rules from {args.rules_dir}...")
        rules = load_rules(args.rules_dir)
        
        # Load errors from CSV
        script_dir = os.path.dirname(os.path.abspath(__file__))
        error_file = os.path.join(script_dir, '..', 'errors.csv')
        
        if not os.path.exists(error_file):
            raise ValueError(f"Error file not found: {error_file}")
        
        # Find all error patterns
        print("Finding all error patterns...")
        error_patterns = find_error_patterns(error_file)
        
        # Sort patterns by number of errors (descending)
        sorted_patterns = sorted(
            error_patterns.items(), 
            key=lambda x: len(x[1]), 
            reverse=True
        )
        
        # Print summary of error patterns
        print("\nError patterns found:")
        for pattern, conversation_ids in sorted_patterns:
            print(f"  {pattern}: {len(conversation_ids)} errors")
        
        # Create output directory for analyses
        output_dir = os.path.join(script_dir, 'error_pattern_analyses')
        os.makedirs(output_dir, exist_ok=True)
        
        # Analyze each error pattern
        for pattern, conversation_ids in sorted_patterns:
            # Skip patterns with too few errors
            if len(conversation_ids) < args.min_errors:
                print(f"\nSkipping pattern '{pattern}' (only {len(conversation_ids)} errors)")
                continue
            
            # Extract categories from pattern
            from_category, to_category = pattern.split(' → ')
            
            print(f"\nAnalyzing pattern: {pattern} ({len(conversation_ids)} errors)")
            
            # Create output file for analysis
            safe_pattern = pattern.replace(' ', '_').replace('→', 'to')
            analysis_file = os.path.join(output_dir, f'error_analysis_{safe_pattern}.txt')
            
            # Analyze the error pattern
            analysis = analyze_category_error_pattern(
                client,
                error_file,
                rules,
                from_category,
                to_category,
                args.max_examples
            )
            
            # Write analysis to file
            with open(analysis_file, 'w') as outfile:
                outfile.write(f"\n{'='*80}\n")
                outfile.write(f"ERROR PATTERN ANALYSIS: {pattern}\n")
                outfile.write(f"Total errors: {len(conversation_ids)}\n")
                outfile.write(f"Analyzed up to {args.max_examples} examples\n\n")
                outfile.write("ANALYSIS:\n")
                outfile.write(analysis['analysis'])
                outfile.write("\n\nUPDATED CLASSIFIERS:\n")
                outfile.write(analysis['improvements'])
                outfile.write("\n")
            
            print(f"Analysis saved to {analysis_file}")
            
            # Ask user if they want to continue
            if pattern != sorted_patterns[-1][0]:  # If not the last pattern
                while True:
                    response = input("\nContinue analyzing patterns? (y/n): ").lower()
                    if response in ['y', 'n']:
                        break
                    print("Please enter 'y' or 'n'")
                if response == 'n':
                    print("\nAnalysis stopped by user")
                    break
        
        print(f"\nAnalysis complete! Results saved to {output_dir}")
        
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 