"""AI service for email analysis."""

import logging
from typing import List

import openai
from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)


def analyze_email_content(content: str) -> List[str]:
    """
    Analyze email content using OpenAI to suggest appropriate tags.
    
    Args:
        content: The email content to analyze
        
    Returns:
        List[str]: A list of suggested tags
    """
    if not content:
        logger.warning("Empty content provided for analysis")
        return []
    
    try:
        # Prepare the prompt for OpenAI
        prompt = f"""
        You are an AI assistant for Precise Imaging, a medical imaging company. 
        Your task is to analyze the following email and suggest appropriate tags.
        
        The tags should categorize the email for different departments:
        - billing: For billing-related inquiries
        - scheduling: For appointment scheduling
        - results: For questions about imaging results
        - insurance: For insurance-related questions
        - technical: For technical issues
        - urgent: For time-sensitive matters
        - general: For general inquiries
        
        Email content:
        {content}
        
        Provide up to 3 most relevant tags from the list above, separated by commas.
        """
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that analyzes emails and suggests tags."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=50,
            temperature=0.3,
        )
        
        # Extract tags from response
        tags_text = response.choices[0].message.content.strip()
        tags = [tag.strip().lower() for tag in tags_text.split(',')]
        
        # Filter out any tags not in our predefined list
        valid_tags = ["billing", "scheduling", "results", "insurance", "technical", "urgent", "general"]
        filtered_tags = [tag for tag in tags if tag in valid_tags]
        
        logger.info(f"AI suggested tags: {filtered_tags}")
        return filtered_tags
        
    except Exception as e:
        logger.exception(f"Error analyzing email content: {str(e)}")
        return ["general"]  # Default tag in case of error 