"""AI service for email analysis."""

import logging
from typing import List
import io

import openai
from openai import OpenAI
import html2text
import mailparser

from app.core.config import settings

logger = logging.getLogger(__name__)

# Initialize OpenAI client
client = OpenAI(api_key=settings.OPENAI_API_KEY)

# HTML to text converter (for fallback)
html_converter = html2text.HTML2Text()
html_converter.ignore_links = False
html_converter.ignore_images = True


def parse_email_content(content_text: str, content_html: str = None) -> str:
    """
    Parse email content using mail-parser.
    
    Args:
        content_text: Plain text content
        content_html: HTML content
        
    Returns:
        str: Parsed text content
    """
    # If we already have plain text, use it
    if content_text and len(content_text.strip()) > 0:
        return content_text
    
    # If we have HTML but no text, try to extract text
    if content_html and len(content_html.strip()) > 0:
        # Try mail-parser first
        try:
            # Create a simple email-like string with the HTML content
            email_string = f"Content-Type: text/html\n\n{content_html}"
            parsed_mail = mailparser.parse_from_string(email_string)
            extracted_text = parsed_mail.body
            
            if extracted_text:
                return extracted_text
        except Exception as e:
            logger.warning(f"Error parsing HTML with mail-parser: {str(e)}")
        
        # Fallback to html2text
        return html_converter.handle(content_html)
    
    # If we don't have either, return empty string
    return ""


def analyze_email_content(content_text: str, content_html: str = None) -> List[str]:
    """
    Analyze email content using OpenAI to suggest appropriate tags.
    
    Args:
        content_text: The plain text email content to analyze
        content_html: Optional HTML content if plain text is not available
        
    Returns:
        List[str]: A list of suggested tags
    """
    # Parse content
    content = parse_email_content(content_text, content_html)
    
    if not content:
        logger.warning("Empty content provided for analysis")
        return ["general"]  # Default tag for empty content
    
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
        
        # If no valid tags were found, return "general"
        if not filtered_tags:
            filtered_tags = ["general"]
        
        logger.info(f"AI suggested tags: {filtered_tags}")
        return filtered_tags
        
    except Exception as e:
        logger.exception(f"Error analyzing email content: {str(e)}")
        return ["general"]  # Default tag in case of error 