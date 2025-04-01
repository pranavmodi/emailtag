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
            prompt += f"Content: {conv.get('content', 'No Content')}\n"
            prompt += f"Tags: {[tag.get('name', '') for tag in conv.get('tags', [])]}\n"
            prompt += f"Category: {category}\n"
            prompt += "-" * 40 + "\n"
    
    # Add the test conversation
    prompt += "\nNow, classify this conversation into one of the categories:\n"
    prompt += f"Subject: {test_conversation.get('subject', 'No Subject')}\n"
    prompt += f"Content: {test_conversation.get('content', 'No Content')}\n"
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
    
    # Get classification from OpenAI
    response = client.chat.completions.create(
        model="gpt-4",
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

def main():
    """Main function to test conversation classification."""
    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        # Load a test conversation
        conversations = load_category_dataset()
        test_conversation = random.choice(conversations)
        
        print("Test conversation:")
        print("-" * 60)
        print(f"Subject: {test_conversation.get('subject', 'No Subject')}")
        print(f"Content: {test_conversation.get('content', 'No Content')}")
        print(f"Tags: {[tag.get('name', '') for tag in test_conversation.get('tags', [])]}")
        print(f"True Category: {test_conversation.get('top_level_category', 'Unknown')}")
        print("-" * 60)
        
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