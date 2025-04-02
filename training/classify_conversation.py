#!/usr/bin/env python3
"""
Script to classify conversations into top-level categories using few-shot learning with OpenAI.
Uses examples from the category dataset to create context for classification.
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
import requests
import urllib3

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load environment variables
load_dotenv()

def load_category_dataset() -> List[Dict[str, Any]]:
    """
    Load the category dataset from JSONL file.
    
    Returns:
        List[Dict[str, Any]]: List of conversations with their categories
    """
    data_dir = os.getenv('DATA_DIR')
    if not data_dir:
        raise ValueError("DATA_DIR environment variable not set")
        
    input_file = os.path.join(data_dir, 'category_dataset', 'category_dataset.jsonl')
    
    conversations = []
    with open(input_file, 'r') as f:
        for line in f:
            conversations.append(json.loads(line))
            
    return conversations

def get_examples_by_category(conversations: List[Dict[str, Any]], examples_per_category: int = 2) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get random examples from each category.
    
    Args:
        conversations (List[Dict[str, Any]]): List of all conversations
        examples_per_category (int): Number of examples to get per category
        
    Returns:
        Dict[str, List[Dict[str, Any]]]: Dictionary mapping categories to example conversations
    """
    # Group conversations by category
    category_examples = {}
    for conv in conversations:
        category = conv.get('top_level_category')
        if category not in category_examples:
            category_examples[category] = []
        category_examples[category].append(conv)
    
    # Sample random examples from each category
    sampled_examples = {}
    for category, convs in category_examples.items():
        sampled_examples[category] = random.sample(convs, min(examples_per_category, len(convs)))
    
    return sampled_examples

def create_few_shot_prompt(examples: Dict[str, List[Dict[str, Any]]], test_conversation: Dict[str, Any]) -> str:
    """
    Create a few-shot prompt with examples and the test conversation.
    
    Args:
        examples (Dict[str, List[Dict[str, Any]]]): Examples by category
        test_conversation (Dict[str, Any]): Conversation to classify
        
    Returns:
        str: Formatted prompt for the LLM
    """
    prompt = """You are a helpful assistant that classifies email conversations into top-level categories.
The categories are: Scheduling, Medical Records & Images, and Accounts Receivable.

Here are some examples of conversations and their categories:

"""
    
    # Add examples for each category
    for category, convs in examples.items():
        prompt += f"\nCategory: {category}\n"
        for conv in convs:
            prompt += f"Subject: {conv.get('subject', 'No Subject')}\n"
            # Extract content from messages
            messages = conv.get('messages', [])
            content = "No Content"
            if messages:
                # Use the content from the first message
                content = messages[0].get('content', 'No Content')
            prompt += f"Content: {content}\n"
            prompt += f"Tags: {[tag.get('name', '') for tag in conv.get('tags', [])]}\n"
            prompt += f"Category: {category}\n"
            prompt += "-" * 40 + "\n"
    
    # Add the test conversation
    prompt += "\nNow, classify this conversation into one of the categories:\n"
    prompt += f"Subject: {test_conversation.get('subject', 'No Subject')}\n"
    # Extract content from messages for test conversation
    messages = test_conversation.get('messages', [])
    content = "No Content"
    if messages:
        # Use the content from the first message
        content = messages[0].get('content', 'No Content')
    prompt += f"Content: {content}\n"
    prompt += f"Tags: {[tag.get('name', '') for tag in test_conversation.get('tags', [])]}\n"
    prompt += "Category:"
    
    return prompt

def classify_conversation(client: OpenAI, conversation: Dict[str, Any], examples_per_category: int = 2) -> Tuple[str, float]:
    """
    Classify a conversation using few-shot learning with OpenAI.
    
    Args:
        client (OpenAI): OpenAI client
        conversation (Dict[str, Any]): Conversation to classify
        examples_per_category (int): Number of examples to use per category
        
    Returns:
        Tuple[str, float]: Predicted category and confidence score
    """
    # Load examples from dataset
    conversations = load_category_dataset()
    examples = get_examples_by_category(conversations, examples_per_category)
    
    # Create prompt
    prompt = create_few_shot_prompt(examples, conversation)
    
    # Get model version from environment or use default
    model_version = os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o')
    
    # Get classification from OpenAI
    response = client.chat.completions.create(
        model=model_version,
        messages=[
            {"role": "system", "content": "You are a helpful assistant that classifies email conversations into top-level categories. Respond with just the category name."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,  # Use 0 temperature for more deterministic results
        max_tokens=10
    )
    
    # Extract prediction
    prediction = response.choices[0].message.content.strip()
    
    # Get confidence score (using logprobs if available)
    confidence = 1.0  # Default confidence
    if hasattr(response.choices[0], 'logprobs'):
        confidence = response.choices[0].logprobs
    
    return prediction, confidence

def condense_conversation(client: OpenAI, conversation: Dict[str, Any]) -> Dict[str, Any]:
    """
    Condense a conversation to its essential elements while preserving classification-relevant information.
    
    Args:
        client (OpenAI): OpenAI client
        conversation (Dict[str, Any]): Conversation to condense
        
    Returns:
        Dict[str, Any]: Condensed conversation
    """
    try:
        # Extract content from messages
        messages = conversation.get('messages', [])
        content = "No Content"
        if messages:
            content = messages[0].get('content', 'No Content')
        
        # Create prompt for condensation
        condensation_prompt = f"""Please condense this email conversation to its essential elements while preserving information relevant for classification into these categories: Scheduling, Medical Records & Images, and Accounts Receivable.

Original conversation:
Subject: {conversation.get('subject', 'No Subject')}
Content: {content}
Tags: {[tag.get('name', '') for tag in conversation.get('tags', [])]}

Please provide a concise summary that captures the key points needed for classification, including:
1. The main purpose/request
2. Any relevant dates, procedures, or medical information
3. Any billing or payment information
4. Any scheduling-related details

Condensed version:"""
        
        # Get condensed version from OpenAI with timeout
        response = client.chat.completions.create(
            model=os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o'),
            messages=[
                {"role": "system", "content": "You are a helpful assistant that condenses email conversations while preserving classification-relevant information."},
                {"role": "user", "content": condensation_prompt}
            ],
            temperature=0.0,
            max_tokens=200,
            timeout=30  # 30 second timeout
        )
        
        # Create condensed conversation
        condensed_conv = {
            'subject': conversation.get('subject', 'No Subject'),
            'content': response.choices[0].message.content.strip(),
            'tags': conversation.get('tags', []),
            'top_level_category': conversation.get('top_level_category', 'Unknown')
        }
        
        return condensed_conv
    except Exception as e:
        print(f"Error condensing conversation: {str(e)}")
        # Return original conversation if condensation fails
        return conversation

def generate_condensed_prompt(client: OpenAI, examples: Dict[str, List[Dict[str, Any]]], test_conversation: Dict[str, Any]) -> str:
    """
    Generate a condensed prompt by condensing multiple conversations in a single API call.
    
    Args:
        client (OpenAI): OpenAI client
        examples (Dict[str, List[Dict[str, Any]]]): Examples by category
        test_conversation (Dict[str, Any]): Conversation to classify
        
    Returns:
        str: Condensed prompt
    """
    # Create a single prompt to condense all conversations at once
    condensation_prompt = """Please condense these email conversations to their essential elements while preserving information relevant for classification into these categories: Scheduling, Medical Records & Images, and Accounts Receivable.

For each conversation, please provide a concise summary that captures:
1. The main purpose/request
2. Any relevant dates, procedures, or medical information
3. Any billing or payment information
4. Any scheduling-related details

Conversations to condense:

"""
    
    # Add all example conversations
    for category, convs in examples.items():
        for conv in convs:
            messages = conv.get('messages', [])
            content = "No Content"
            if messages:
                content = messages[0].get('content', 'No Content')
            
            condensation_prompt += f"\nCategory: {category}\n"
            condensation_prompt += f"Subject: {conv.get('subject', 'No Subject')}\n"
            condensation_prompt += f"Content: {content}\n"
            condensation_prompt += f"Tags: {[tag.get('name', '') for tag in conv.get('tags', [])]}\n"
            condensation_prompt += "-" * 40 + "\n"
    
    # Add test conversation
    messages = test_conversation.get('messages', [])
    content = "No Content"
    if messages:
        content = messages[0].get('content', 'No Content')
    
    condensation_prompt += "\nTest Conversation:\n"
    condensation_prompt += f"Subject: {test_conversation.get('subject', 'No Subject')}\n"
    condensation_prompt += f"Content: {content}\n"
    condensation_prompt += f"Tags: {[tag.get('name', '') for tag in test_conversation.get('tags', [])]}\n"
    condensation_prompt += "-" * 40 + "\n"
    
    condensation_prompt += "\nPlease provide condensed versions of all conversations above, maintaining their original categories and structure."
    
    # Get condensed versions in a single API call
    response = client.chat.completions.create(
        model=os.getenv('OPENAI_MODEL_VERSION', 'gpt-4o'),
        messages=[
            {"role": "system", "content": "You are a helpful assistant that condenses email conversations while preserving classification-relevant information."},
            {"role": "user", "content": condensation_prompt}
        ],
        temperature=0.0,
        max_tokens=1000,
        timeout=60
    )
    
    # Create the final classification prompt
    prompt = """You are a helpful assistant that classifies email conversations into top-level categories.
The categories are: Scheduling, Medical Records & Images, and Accounts Receivable.

Here are some condensed examples of conversations and their categories:

"""
    
    # Add the condensed conversations from the response
    prompt += response.choices[0].message.content.strip()
    
    # Add the classification instruction
    prompt += "\nNow, classify the test conversation into one of the categories:"
    
    return prompt

def condense_category_conversations(client: OpenAI, conversations: List[Dict[str, Any]], category: str, num_examples: int = 5) -> str:
    """
    Condense multiple conversations from a single category into a single prompt.
    
    Args:
        client (OpenAI): OpenAI client
        conversations (List[Dict[str, Any]]): List of conversations
        category (str): Category to condense
        num_examples (int): Number of examples to use
        
    Returns:
        str: Condensed version of the conversations
    """
    # Filter conversations for the category
    category_convs = [conv for conv in conversations if conv.get('top_level_category') == category]
    if len(category_convs) > num_examples:
        category_convs = random.sample(category_convs, num_examples)
    
    # Create prompt for condensing
    condensation_prompt = f"""Please analyze these {category} conversations and create a concise summary of their common patterns and key characteristics. Focus on what makes these conversations belong to the {category} category.

For each conversation, identify:
1. The main purpose/request
2. Key details and action items
3. Specific indicators or phrases
4. Any special considerations

Conversations to analyze:
"""
    
    # Add conversations to the prompt
    for conv in category_convs:
        messages = conv.get('messages', [])
        content = "No Content"
        if messages:
            content = messages[0].get('content', 'No Content')
        
        condensation_prompt += f"\nSubject: {conv.get('subject', 'No Subject')}\n"
        condensation_prompt += f"Content: {content}\n"
        condensation_prompt += f"Tags: {[tag.get('name', '') for tag in conv.get('tags', [])]}\n"
        condensation_prompt += "-"*40 + "\n"
    
    condensation_prompt += "\nPlease provide a summary of the common patterns and characteristics that define this category."
    
    # Get condensed version from OpenAI
    response = client.chat.completions.create(
        model="o3-mini",
        messages=[
            {"role": "system", "content": f"You are a helpful assistant that analyzes {category} conversations to identify their defining characteristics."},
            {"role": "user", "content": condensation_prompt}
        ],
        max_completion_tokens=500,
        timeout=30
    )
    
    return response.choices[0].message.content.strip()

def generate_optimized_prompt(client: OpenAI, num_iterations: int = 10) -> str:
    """
    Generate an optimized prompt by first condensing conversations by category,
    then creating a final optimized prompt from the condensed versions.
    
    Args:
        client (OpenAI): OpenAI client
        num_iterations (int): Number of iterations to run
        
    Returns:
        str: Optimized prompt
    """
    # Load all conversations
    conversations = load_category_dataset()
    print(f"\nLoaded {len(conversations)} total conversations")
    
    # Debug: Print conversation categories
    categories = {}
    for conv in conversations:
        category = conv.get('top_level_category', 'Unknown')
        categories[category] = categories.get(category, 0) + 1
    print("\nConversation categories:")
    for cat, count in categories.items():
        print(f"- {cat}: {count} conversations")
    
    # Create directory for prompts if it doesn't exist
    prompts_dir = os.path.join(os.getenv('DATA_DIR', ''), 'prompts')
    os.makedirs(prompts_dir, exist_ok=True)
    
    # Check for existing condensed summaries
    condensed_file = os.path.join(prompts_dir, 'condensed_category_summaries.txt')
    condensed_categories = {}
    
    if os.path.exists(condensed_file):
        print("\nFound existing condensed summaries file. Loading...")
        with open(condensed_file, 'r') as f:
            content = f.read()
            # Split by category headers
            sections = content.split("\n\n")
            for section in sections:
                if section.strip():
                    lines = section.split('\n')
                    category = lines[0].replace(':', '').strip()
                    summary = '\n'.join(lines[1:]).strip()
                    condensed_categories[category] = summary
        print(f"Loaded condensed summaries for: {', '.join(condensed_categories.keys())}")
    
    # Condense conversations for each category if not already done
    categories_to_process = ['Scheduling', 'Medical Records & Images', 'Accounts Receivable']
    categories_to_process = [cat for cat in categories_to_process if cat not in condensed_categories]
    
    if categories_to_process:
        print("\nCondensing conversations for remaining categories...")
        for category in categories_to_process:
            print(f"\nCondensing {category} conversations...")
            # Debug: Print available conversations for this category
            category_convs = [conv for conv in conversations if conv.get('top_level_category') == category]
            print(f"Found {len(category_convs)} conversations for {category}")
            
            if not category_convs:
                print(f"Warning: No conversations found for category {category}")
                continue
                
            condensed = condense_category_conversations(client, conversations, category)
            if not condensed.strip():
                print(f"Warning: Empty condensed summary for {category}")
                continue
                
            condensed_categories[category] = condensed
            print(f"Completed {category}")
            
            # Save after each category
            with open(condensed_file, 'w') as f:
                for cat, summary in condensed_categories.items():
                    f.write(f"{cat}:\n")
                    f.write(summary)
                    f.write("\n\n")
            print(f"Saved condensed summaries to {condensed_file}")
    
    # Create the final optimization prompt
    optimization_prompt = f"""Please analyze these condensed summaries of email conversations from three categories and create a set of clear, general classification rules that can be applied to any conversation.

For each category, I have provided a summary of its key characteristics and patterns. Please use these summaries to create specific rules for classification.

Category Summaries:

Scheduling:
{condensed_categories.get('Scheduling', 'No summary available')}

Medical Records & Images:
{condensed_categories.get('Medical Records & Images', 'No summary available')}

Accounts Receivable:
{condensed_categories.get('Accounts Receivable', 'No summary available')}

Please create a complete set of classification rules for ALL THREE categories. For each category, provide:
1. Main Purpose/Request rules
2. Key Details/Action Items to look for
3. Specific Indicators & Phrases
4. Edge Cases & Special Considerations

Example format for rules:
- If the conversation contains [specific indicators], classify as [category]
- If the primary purpose is [specific purpose], classify as [category]
- If the conversation involves [specific actions], classify as [category]

Classification Rules:"""
    
    # Print the prompt and wait for user input
    print("\nPreview of optimization prompt:")
    print("="*80)
    print(optimization_prompt)
    print("="*80)
    input("\nPress Enter to proceed with the OpenAI call, or Ctrl+C to cancel...")
    
    # Get optimized prompt from OpenAI with timeout
    response = client.chat.completions.create(
        model="o3-mini",  # Using o3-mini for reasoning
        messages=[
            {"role": "system", "content": "You are a helpful assistant that creates clear classification rules from category summaries. Ensure you provide rules for all three categories."},
            {"role": "user", "content": optimization_prompt}
        ],
        max_completion_tokens=1000,
        timeout=60  # 60 second timeout
    )
    
    optimized_prompt = response.choices[0].message.content.strip()
    
    # Save optimized prompt
    optimized_file = os.path.join(prompts_dir, 'optimized_prompt.txt')
    with open(optimized_file, 'w') as f:
        f.write(optimized_prompt)
    print(f"Saved optimized prompt to {optimized_file}")
    
    return optimized_prompt

def main():
    """Main function to test conversation classification."""
    parser = argparse.ArgumentParser(description='Classify conversations using few-shot learning')
    parser.add_argument('--debug', action='store_true', help='Print the generated prompt without making API call')
    parser.add_argument('--conv-id', type=str, help='Specific conversation ID to classify')
    parser.add_argument('--optimize', action='store_true', help='Generate and use optimized prompt')
    args = parser.parse_args()
    
    try:
        # Initialize OpenAI client with custom httpx client
        client = OpenAI(
            api_key=os.getenv('OPENAI_API_KEY'),
            http_client=httpx.Client(verify=False)  # Disable SSL verification
        )
        
        if args.optimize:
            # Generate optimized prompt
            optimized_prompt = generate_optimized_prompt(client)
            print("\nOptimized Prompt:")
            print("-" * 60)
            print(optimized_prompt)
            print("-" * 60)
            return
        
        # Load a test conversation
        conversations = load_category_dataset()
        if args.conv_id:
            # Find the specific conversation
            test_conversation = next((conv for conv in conversations if conv.get('id') == args.conv_id), None)
            if not test_conversation:
                print(f"Error: Could not find conversation with ID {args.conv_id}")
                return
        else:
            # Use a random conversation
            test_conversation = random.choice(conversations)
        
        print("Test conversation:")
        print("-" * 60)
        print(f"Subject: {test_conversation.get('subject', 'No Subject')}")
        messages = test_conversation.get('messages', [])
        content = "No Content"
        if messages:
            content = messages[0].get('content', 'No Content')
        print(f"Content: {content}")
        print(f"Tags: {[tag.get('name', '') for tag in test_conversation.get('tags', [])]}")
        print(f"True Category: {test_conversation.get('top_level_category', 'Unknown')}")
        print("-" * 60)
        
        if args.debug:
            # Just print the prompt
            conversations = load_category_dataset()
            examples = get_examples_by_category(conversations)
            prompt = create_few_shot_prompt(examples, test_conversation)
            print("\nGenerated Prompt:")
            print("-" * 60)
            print(prompt)
            print("-" * 60)
        else:
            # Get classification
            predicted_category, confidence = classify_conversation(client, test_conversation)
            
            print("\nClassification Results:")
            print("-" * 60)
            print(f"Predicted Category: {predicted_category}")
            print(f"Confidence: {confidence:.2f}")
            print(f"Correct: {predicted_category == test_conversation.get('top_level_category')}")
        
    except Exception as e:
        print(f"\nError during classification: {str(e)}")
        print(f"Full error details:", e.__class__.__name__)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main() 