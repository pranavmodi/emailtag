#!/usr/bin/env python3
"""
Script to analyze classification errors and suggest improvements to the rules.
Takes errors.csv as input and uses OpenAI to analyze each error and propose rule improvements.
"""

import os
import csv
import argparse
from typing import Dict, Any

from .data_loader import load_rules, load_conversation, count_done_tagged_errors, format_conversation_for_analysis
from .openai_analyzer import OpenAIAnalyzer

def main():
    """Main function to analyze classification errors."""
    try:
        # Parse command line arguments
        parser = argparse.ArgumentParser(description='Analyze classification errors and suggest improvements.')
        parser.add_argument('--conversation-id', '-c', type=str, help='Specific conversation ID to analyze')
        parser.add_argument('--count-done-tags', action='store_true', help='Count how many error emails have a "done" tag')
        parser.add_argument('--predicted-category', type=str, help='Category that emails were incorrectly classified as')
        parser.add_argument('--actual-category', type=str, help='True category that emails should have been classified as')
        parser.add_argument('--max-examples', type=int, default=5, help='Maximum number of examples to analyze for category pattern')
        args = parser.parse_args()
        
        # Get the OpenAI model version
        model_version = os.getenv('REASONING_MODEL', 'o3-mini')
        print(f"Using OpenAI model: {model_version}")
        
        # Initialize OpenAI analyzer
        analyzer = OpenAIAnalyzer()
        
        # Load rules - Fix the path to training_rules
        script_dir = os.path.dirname(os.path.abspath(__file__))
        rules_dir = os.path.join(script_dir, '..', 'training_rules')
        print(f"Loading rules from {rules_dir}...")
        rules = load_rules(rules_dir)
        
        # Load errors from CSV
        error_file = os.path.join(script_dir, '..', 'errors.csv')
        
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
        
        # If predicted-category and actual-category are provided, analyze that pattern
        if args.predicted_category and args.actual_category:
            print(f"Analyzing errors where emails were incorrectly classified as '{args.predicted_category}' when they should have been '{args.actual_category}'...")
            
            # Create output file for analysis (in append mode)
            analysis_file = os.path.join(script_dir, f'error_analysis_{args.predicted_category.replace(" ", "_")}_to_{args.actual_category.replace(" ", "_")}.txt')
            
            # Analyze the error pattern
            analysis = analyzer.analyze_category_error_pattern(
                error_file,
                rules,
                args.predicted_category,
                args.actual_category,
                args.max_examples
            )
            
            # Write analysis to file
            with open(analysis_file, 'w') as outfile:
                outfile.write(f"\n{'='*80}\n")
                outfile.write(f"ERROR PATTERN ANALYSIS: {args.predicted_category} → {args.actual_category}\n")
                outfile.write(f"Analyzed up to {args.max_examples} examples\n\n")
                outfile.write("ANALYSIS:\n")
                outfile.write(analysis['analysis'])
                outfile.write("\n\nUPDATED CLASSIFIERS:\n")
                # Print the improvements to console for debugging
                print("\nIMPROVEMENTS TO BE WRITTEN TO FILE:")
                print(analysis['improvements'])
                outfile.write(analysis['improvements'])
                outfile.write("\n")
            
            print(f"Analysis saved to {analysis_file}")
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
                        analysis = analyzer.analyze_error(
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
                    analysis = analyzer.analyze_error(
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