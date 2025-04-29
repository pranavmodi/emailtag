"""Service function for performing OCR on documents."""

import logging
import httpx
from typing import List, Dict, Any, Optional

from app.core.config import settings # Assuming OCR API URL might be added here

logger = logging.getLogger(__name__)

# Consider adding the OCR API URL to your settings for flexibility
# OCR_API_URL = settings.OCR_API_URL 
OCR_API_URL = "https://docclassifier1-dev.radflow360.com:4000/all_doc_ocr_process" 

def perform_ocr(encoded_strings: List[str]) -> Optional[Dict[str, Any]]:
    """
    Sends base64 encoded document strings to the OCR API for text extraction 
    and information retrieval (accession numbers, patient ID, study type).

    Args:
        encoded_strings: A list of base64 encoded strings representing the documents.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the OCR API containing 
                                   the extracted information, or None if an error occurs.
                                   The structure is expected to be like:
                                   {
                                       "data": [
                                           {
                                               "encoded_string": "<original_encoded_string>", 
                                               "info": {
                                                   "accession_nums": [], 
                                                   "patient_id": "", 
                                                   "study_type": [] 
                                               }
                                           }
                                       ],
                                       "message": "Success" 
                                   }
    Raises:
        httpx.HTTPStatusError: If the API returns an error status code (4xx or 5xx).
        Exception: For other potential issues like network errors or JSON decoding problems.
    """
    if not encoded_strings:
        logger.warning("No encoded strings provided for OCR. Skipping API call.")
        return None

    # Construct the payload
    payload_data = [{"encoded_string": s} for s in encoded_strings]
    payload = {"data": payload_data}

    # TODO: Configure SSL verification properly if needed for the OCR endpoint
    # Consider using a persistent client session if making many calls
    with httpx.Client(verify=False, timeout=60.0) as client: # Added timeout
        try:
            logger.info(f"Sending {len(encoded_strings)} document(s) to OCR API: {OCR_API_URL}")
            response = client.post(OCR_API_URL, json=payload)
            
            logger.info(f"OCR API response status: {response.status_code}")

            # Raise exceptions for 4xx/5xx errors
            response.raise_for_status() 
            
            response_data = response.json()
            logger.info("Successfully received and parsed OCR response.")
            # You might want to add validation here to ensure the response structure matches expectations
            
            return response_data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling OCR API: {e.response.status_code} - {e.response.text}")
            # Re-raise the specific HTTP error for handling upstream
            raise 
        except httpx.RequestError as e:
            # Handles connection errors, timeouts, etc.
            logger.error(f"Request error calling OCR API: {str(e)}")
            raise Exception(f"Could not connect to OCR API: {str(e)}") from e
        except Exception as e:
            # Catch other potential errors (e.g., JSON decoding, unexpected issues)
            logger.exception(f"Unexpected error during OCR processing: {str(e)}")
            # Re-raise unexpected errors
            raise

# Example Usage (Optional - for testing directly)
# if __name__ == "__main__":
#     logging.basicConfig(level=logging.INFO)
#     
#     # Replace with actual base64 encoded strings for testing
#     test_encoded_string_1 = "..." # Example base64 string for a document
#     test_encoded_string_2 = "..." # Example base64 string for another document
# 
#     if test_encoded_string_1 != "...":
#         try:
#             print("Testing OCR service...")
#             ocr_result = perform_ocr([test_encoded_string_1, test_encoded_string_2])
#             
#             if ocr_result:
#                 print("OCR Result Received:")
#                 import json
#                 print(json.dumps(ocr_result, indent=4))
#                 
#                 # Example: Accessing specific info
#                 if ocr_result.get("data"):
#                     for item in ocr_result["data"]:
#                         print(f"  Document Info: {item.get('info')}")
#             else:
#                 print("OCR call did not return data (likely skipped or failed).")
#                 
#         except Exception as e:
#             print(f"OCR test failed: {e}")
#     else:
#          print("Please replace '...' with actual base64 encoded strings to run the OCR test.") 