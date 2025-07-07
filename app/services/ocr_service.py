"""Service function for performing OCR on documents."""

import logging
import httpx
from typing import List, Dict, Any, Optional
import base64
import io # Potentially needed if we were handling streams, but bytes are fine directly

from app.core.config import settings # Assuming OCR API URL might be added here

logger = logging.getLogger(__name__)

# OCR API URL from settings
OCR_API_URL = str(settings.OCR_API_URL) 

def file_to_base64(file_path: str) -> Optional[str]:
    """Reads any file and encodes its content to a base64 string.

    Args:
        file_path: The path to the file.

    Returns:
        A base64 encoded string representing the file content, 
        or None if the file cannot be read.
    """
    try:
        with open(file_path, "rb") as file_content:
            binary_data = file_content.read()
            base64_encoded_data = base64.b64encode(binary_data)
            base64_string = base64_encoded_data.decode('utf-8')
            logger.info(f"Successfully encoded file: {file_path}")
            return base64_string
    except FileNotFoundError:
        logger.error(f"Error encoding file: File not found at {file_path}")
        return None
    except Exception as e:
        logger.error(f"Error reading or encoding file {file_path}: {e}")
        return None

def perform_ocr(file_paths: List[str]) -> Optional[Dict[str, Any]]:
    """
    Encodes files from given paths to base64 and sends them to the OCR API 
    for text extraction and information retrieval.

    Args:
        file_paths: A list of file paths for the documents to be processed.

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the OCR API containing 
                                   the extracted information for successfully processed files, 
                                   or None if no files could be encoded or an API error occurs.
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
                                           # ... potentially fewer items than input paths if encoding failed
                                       ],
                                       "message": "Success" 
                                   }
    Raises:
        httpx.HTTPStatusError: If the API returns an error status code (4xx or 5xx).
        Exception: For other potential issues like network errors or JSON decoding problems.
    """
    if not file_paths:
        logger.warning("No file paths provided for OCR. Skipping.")
        return None

    encoded_strings = []
    for file_path in file_paths:
        encoded_string = file_to_base64(file_path)
        if encoded_string:
            encoded_strings.append(encoded_string)
        else:
            logger.warning(f"Skipping file {file_path} due to encoding error.")

    if not encoded_strings:
        logger.error("No files could be successfully encoded for OCR.")
        return None

    # Construct the payload using successfully encoded strings
    payload_data = [{"encoded_string": s} for s in encoded_strings]
    payload = {"data": payload_data}

    # TODO: Configure SSL verification properly if needed for the OCR endpoint
    # Consider using a persistent client session if making many calls
    with httpx.Client(verify=False, timeout=60.0) as client: # Added timeout
        try:
            logger.info(f"Sending {len(encoded_strings)} successfully encoded document(s) to OCR API: {OCR_API_URL}")
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

def process_ocr_content(content: bytes) -> Optional[Dict[str, Any]]:
    """
    Encodes raw byte content to base64 and sends it to the OCR API.

    Args:
        content: The raw byte content of the document (e.g., PDF, image).

    Returns:
        Optional[Dict[str, Any]]: The JSON response from the OCR API, 
                                   or None if encoding or API call fails in a way 
                                   not raising an exception upstream.

    Raises:
        TypeError: If the input content is not bytes.
        httpx.HTTPStatusError: If the API returns an error status code (4xx or 5xx).
        Exception: For other potential issues like network errors or JSON decoding problems.
    """
    if not isinstance(content, bytes):
        logger.error("Invalid input: 'content' must be bytes.")
        raise TypeError("'content' must be bytes.")
    
    if not content:
        logger.warning("No content provided for OCR. Skipping.")
        return None

    # --- Encode Content ---
    try:
        encoded_content = base64.b64encode(content).decode('utf-8')
        logger.debug(f"Base64 encoded content. Encoded size: {len(encoded_content)}")
    except Exception as exc:
        logger.exception(f"Error Base64 encoding content: {exc}")
        # Let the caller handle the exception, maybe log and return None?
        # For now, re-raise to make failures explicit upstream.
        raise Exception(f"Failed to encode content for OCR: {exc}") from exc

    # --- Call OCR Service ---
    payload = {
        "data": [
            {"encoded_string": encoded_content}
        ]
    }

    # Reuse client settings from perform_ocr with increased timeout for stability
    with httpx.Client(verify=False, timeout=600.0) as client: # Increased timeout to 10 minutes for large files
        try:
            logger.info(f"Sending encoded content to OCR API: {OCR_API_URL}")
            response = client.post(OCR_API_URL, json=payload) 
            
            logger.info(f"OCR API response status: {response.status_code}")

            # Raise exceptions for 4xx/5xx errors
            response.raise_for_status() 
            
            response_data = response.json()
            logger.info("Successfully received and parsed OCR response from content.")
            return response_data

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling OCR API with content: {e.response.status_code} - {e.response.text}")
            # Re-raise the specific HTTP error for handling upstream (e.g., in Celery task)
            raise 
        except httpx.RequestError as e:
            # Handles connection errors, timeouts, etc.
            logger.error(f"Request error calling OCR API with content: {str(e)}")
            raise Exception(f"Could not connect to OCR API: {str(e)}") from e
        except Exception as e:
            # Catch other potential errors (e.g., JSON decoding)
            logger.exception(f"Unexpected error during OCR processing of content: {str(e)}")
            # Re-raise unexpected errors
            raise

# Example Usage (Optional - for testing directly)
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # Replace with actual file paths for testing
    test_file_path_1 = "ocr_test_PRE100345.pdf" # Using the provided test file
    # test_file_path_2 = "/path/to/your/image.png" # Optional: add another file path

    # Create a list of file paths to test
    files_to_test = [test_file_path_1]
    # if test_file_path_2 != "/path/to/your/image.png": 
    #    files_to_test.append(test_file_path_2)

    if files_to_test:
        try:
            print("Testing OCR service with file paths...")
            # Pass the list of file paths
            ocr_result = perform_ocr(files_to_test)
            
            if ocr_result:
                print("\n--- OCR Result Received ---")
                import json
                print(json.dumps(ocr_result, indent=4))
                print("---------------------------")
                
                # Example: Accessing specific info
                if ocr_result.get("data"):
                    for i, item in enumerate(ocr_result["data"]):
                        print(f"\n  Document {i+1} Info:")
                        info = item.get('info', {})
                        print(f"    Accession Nums: {info.get('accession_nums')}")
                        print(f"    Patient ID:     {info.get('patient_id')}")
                        print(f"    Study Type:     {info.get('study_type')}")
            else:
                print("\nOCR call did not return data (likely skipped or failed).")
                
        except Exception as e:
            print(f"\nOCR test failed: {e}")
    else:
         print("\nNo valid file paths specified for the test.") 