#!/usr/bin/env python3
"""
Script to analyze specific patterns of classification errors between categories.
This script focuses on analyzing errors where emails were misclassified from one category to another.
"""

import os
import sys
import argparse
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

def main():
    """Main function to analyze category error patterns."""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Analyze specific patterns of classification errors between categories.')
        parser.add_argument('--from-category', type=str, required=True, 
                           help='Category that emails were incorrectly classified as')
        parser.add_argument('--to-category', type=str, required=True, 
                           help='True category that emails should have been classified as')
        parser.add_argument('--max-examples', type=int, default=5, 
                           help='Maximum number of examples to analyze (default: 5)')
        parser.add_argument('--rules-dir', type=str, default='../training_rules',
                           help='Directory containing rule files (default: ../training_rules)')
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
        
        # Analyze the error pattern
        print(f"Analyzing errors from '{args.from_category}' to '{args.to_category}'...")
        
        # Create output file for analysis
        analysis_file = os.path.join(script_dir, f'error_analysis_{args.from_category.replace(" ", "_")}_to_{args.to_category.replace(" ", "_")}.txt')
        
        # Analyze the error pattern
        analysis = analyze_category_error_pattern(
            client,
            error_file,
            rules,
            args.from_category,
            args.to_category,
            args.max_examples
        )
        
        # Write analysis to file
        with open(analysis_file, 'w') as outfile:
            outfile.write(f"\n{'='*80}\n")
            outfile.write(f"ERROR PATTERN ANALYSIS: {args.from_category} → {args.to_category}\n")
            outfile.write(f"Analyzed up to {args.max_examples} examples\n\n")
            outfile.write("ANALYSIS:\n")
            outfile.write(analysis['analysis'])
            outfile.write("\n\nUPDATED CLASSIFIERS:\n")
            outfile.write(analysis['improvements'])
            outfile.write("\n")
        
        print(f"Analysis saved to {analysis_file}")
        
    except Exception as e:
        print(f"\nError during analysis: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 