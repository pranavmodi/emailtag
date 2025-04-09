"""
OpenAI-based analysis for classification errors.
"""

import os
from typing import Dict, Any
from openai import OpenAI
import httpx
import urllib3
import csv
from .data_loader import load_conversation, format_conversation_for_analysis

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class OpenAIAnalyzer:
    """Class for analyzing classification errors using OpenAI."""
    
    def __init__(self):
        """Initialize the OpenAI client."""
        self.client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            http_client=httpx.Client(verify=False)  # Disable SSL verification
        )
        self.model = os.getenv('REASONING_MODEL', 'o3-mini')
    
    def analyze_error(self, conv: Dict[str, Any], rules: Dict[str, str], 
                     predicted_category: str, true_category: str) -> Dict[str, str]:
        """
        Analyze a classification error using OpenAI.
        
        Args:
            conv (Dict[str, Any]): Conversation data
            rules (Dict[str, str]): Current classification rules
            predicted_category (str): Category predicted by the model
            true_category (str): True category
            
        Returns:
            Dict[str, str]: Analysis results containing rationale and proposed improvements
        """
        from .data_loader import format_conversation_for_analysis
        
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
        response = self.client.chat.completions.create(
            model=self.model,
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
    
    def analyze_category_error_pattern(self, error_file: str, rules: Dict[str, str], 
                                       predicted_category: str, actual_category: str, 
                                       max_examples: int = 5) -> Dict[str, str]:
        """Analyze a pattern of errors between two categories.
        
        Args:
            error_file: Path to the errors CSV file
            rules: Dictionary of current rules
            predicted_category: Category that emails were incorrectly classified as
            actual_category: True category that emails should have been classified as
            max_examples: Maximum number of examples to analyze
            
        Returns:
            Dictionary containing analysis and suggested improvements
        """
        try:
            # Load errors from CSV
            errors = []
            with open(error_file, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row['Predicted Category'] == predicted_category and 
                        row['True Category'] == actual_category):
                        errors.append(row)
                        if len(errors) >= max_examples:
                            break
            
            if not errors:
                print(f"No errors found where emails were incorrectly classified as '{predicted_category}' when they should have been '{actual_category}'")
                return {
                    'analysis': "No errors found for this category pair.",
                    'improvements': "No improvements needed."
                }
            
            # Format examples for analysis
            examples = []
            for error in errors:
                conv = load_conversation(error['Conversation ID'])
                conv_text = format_conversation_for_analysis(conv)
                examples.append(conv_text)
            
            # Create analysis prompt
            prompt = f"""Analyze these examples of emails that were incorrectly classified as '{predicted_category}' when they should have been '{actual_category}'.
            
Current rules for {predicted_category}:
{rules.get(predicted_category, 'No rules defined')}

Current rules for {actual_category}:
{rules.get(actual_category, 'No rules defined')}

Example conversations:
{chr(10).join(examples)}

Please analyze:
1. Common patterns in these misclassifications
2. Why the current rules failed
3. How to improve the rules to prevent these errors

IMPORTANT: You MUST provide COMPLETE UPDATED CLASSIFIERS for BOTH categories. Do not just suggest improvements to the existing rules.

Format your response as:
ANALYSIS:
[Your detailed analysis here]

UPDATED CLASSIFIERS:
[Complete updated classifier for {predicted_category}]

[Complete updated classifier for {actual_category}]"""

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
                print("Skipping OpenAI analysis for these errors.")
                return {
                    'analysis': "Analysis skipped by user.",
                    'improvements': "No improvements generated."
                }

            # Get analysis from OpenAI
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing email classification errors and improving classification rules."},
                    {"role": "user", "content": prompt}
                ]
            )
            
            analysis = response.choices[0].message.content
            
            # Print the raw response to console
            print("\n" + "="*80)
            print("RAW RESPONSE FROM OPENAI:")
            print("="*80)
            print(analysis)
            print("="*80)
            
            # Split analysis into analysis and improvements sections
            parts = analysis.split('\n\n')
            analysis_text = ""
            improvements = ""
            
            for part in parts:
                if part.startswith('ANALYSIS:'):
                    analysis_text = part.replace('ANALYSIS:', '').strip()
                elif part.startswith('UPDATED CLASSIFIERS:'):
                    improvements = part.replace('UPDATED CLASSIFIERS:', '').strip()
            
            # If we couldn't find the sections, use the whole response
            if not analysis_text and not improvements:
                analysis_text = analysis
                improvements = "No specific improvements section found in the response."
            
            return {
                'analysis': analysis_text,
                'improvements': improvements
            }
            
        except Exception as e:
            print(f"Error analyzing category error pattern: {str(e)}")
            return {
                'analysis': f"Error during analysis: {str(e)}",
                'improvements': "No improvements could be generated due to error."
            } 