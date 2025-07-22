"""Mock OCR responses for testing and client evaluation scenarios."""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# Mock OCR responses for different document types and scenarios
MOCK_OCR_RESPONSES = {
    "default": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE1234567",
                    "accession_nums": ["ACC123456"],
                    "study_type": ["MRI"],
                    "patient_name": "Test Patient",
                    "study_date": "2024-01-15",
                    "body_part": "Lumbar Spine",
                    "extracted_text": "Sample medical document text for testing purposes."
                }
            }
        ],
        "message": "Success"
    },
    
    "billing_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE2345678",
                    "accession_nums": ["ACC234567"],
                    "study_type": ["CT"],
                    "patient_name": "Billing Test Patient",
                    "study_date": "2024-02-01",
                    "body_part": "Chest",
                    "amount_due": "$450.00",
                    "insurance_info": "Blue Cross Blue Shield",
                    "extracted_text": "Invoice for CT scan services. Amount due: $450.00"
                }
            }
        ],
        "message": "Success"
    },
    
    "lien_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE6666666",
                    "accession_nums": ["ACC345678"],
                    "study_type": ["MRI"],
                    "patient_name": "Lien Test Patient",
                    "study_date": "2024-03-01",
                    "body_part": "Knee",
                    "lien_type": "Rad Lien",
                    "attorney_name": "Smith & Associates",
                    "case_number": "CV-2024-001",
                    "extracted_text": "Personal Services Lien documentation for MRI examination."
                }
            }
        ],
        "message": "Success"
    },

    "tech_lien_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE7777777",
                    "accession_nums": ["ACC789012"],
                    "study_type": ["CT"],
                    "patient_name": "Tech Lien Test Patient",
                    "study_date": "2024-07-01",
                    "body_part": "Abdomen",
                    "lien_type": "Tech Lien",
                    "attorney_name": "Johnson & Partners",
                    "case_number": "CV-2024-002",
                    "extracted_text": "Technologist Services Lien documentation for CT examination."
                }
            }
        ],
        "message": "Success"
    },
    
    "scheduling_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE4567890",
                    "accession_nums": ["ACC456789"],
                    "study_type": ["Ultrasound"],
                    "patient_name": "Schedule Test Patient",
                    "appointment_date": "2024-04-01",
                    "appointment_time": "10:00 AM",
                    "body_part": "Abdomen",
                    "referring_physician": "Dr. Johnson",
                    "extracted_text": "Ultrasound appointment scheduled for April 1st at 10:00 AM."
                }
            }
        ],
        "message": "Success"
    },
    
    "medical_records": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE5678901",
                    "accession_nums": ["ACC567890"],
                    "study_type": ["X-Ray"],
                    "patient_name": "Records Test Patient",
                    "study_date": "2024-05-01",
                    "body_part": "Shoulder",
                    "findings": "No acute fracture identified",
                    "radiologist": "Dr. Smith",
                    "extracted_text": "X-Ray report showing no acute fracture in shoulder region."
                }
            }
        ],
        "message": "Success"
    },
    
    "error_response": {
        "data": [],
        "message": "OCR processing failed",
        "error": "Unable to process document"
    },
    
    "multiple_attachments": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE6789012",
                    "accession_nums": ["ACC678901", "ACC678902"],
                    "study_type": ["MRI", "CT"],
                    "patient_name": "Multi Test Patient",
                    "study_date": "2024-06-01",
                    "body_part": "Brain",
                    "extracted_text": "Multiple imaging studies for brain examination."
                }
            },
            {
                "info": {
                    "patient_id": "PRE6789012",
                    "accession_nums": ["ACC678903"],
                    "study_type": ["PET"],
                    "patient_name": "Multi Test Patient",
                    "study_date": "2024-06-02",
                    "body_part": "Whole Body",
                    "extracted_text": "PET scan for oncology follow-up."
                }
            }
        ],
        "message": "Success"
    },

    "psl_rad_lien_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE6666666",
                    "accession_nums": ["ACC111111"],
                    "study_type": ["MRI"],
                    "patient_name": "John Smith",
                    "study_date": "2024-03-01",
                    "body_part": "Knee",
                    "lien_type": "Rad Lien",
                    "document_type": "PSL",
                    "extracted_text": "Patient Signed Lien for radiology services - MRI examination."
                }
            }
        ],
        "message": "Success"
    },

    "psl_tech_lien_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE7777777",
                    "accession_nums": ["ACC222222"],
                    "study_type": ["CT"],
                    "patient_name": "Maria Rodriguez",
                    "study_date": "2024-04-01",
                    "body_part": "Abdomen",
                    "lien_type": "Tech Lien",
                    "document_type": "PSL",
                    "extracted_text": "Patient Signed Lien for technologist services - CT examination."
                }
            }
        ],
        "message": "Success"
    },

    "asl_rad_lien_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE8888888",
                    "accession_nums": ["ACC333333"],
                    "study_type": ["MRI"],
                    "patient_name": "Client Patient",
                    "study_date": "2024-05-01",
                    "body_part": "Shoulder",
                    "lien_type": "Rad Lien",
                    "document_type": "ASL",
                    "attorney_name": "Johnson & Associates Law Firm",
                    "case_number": "CV-2024-003",
                    "extracted_text": "Attorney Signed Lien for radiology services - MRI examination."
                }
            }
        ],
        "message": "Success"
    },

    "asl_tech_lien_document": {
        "data": [
            {
                "info": {
                    "patient_id": "PRE9999999",
                    "accession_nums": ["ACC444444"],
                    "study_type": ["CT"],
                    "patient_name": "Client Patient 2",
                    "study_date": "2024-06-01",
                    "body_part": "Chest",
                    "lien_type": "Tech Lien",
                    "document_type": "ASL",
                    "attorney_name": "Davis & Partners Law Firm",
                    "case_number": "CV-2024-004",
                    "extracted_text": "Attorney Signed Lien for technologist services - CT examination."
                }
            }
        ],
        "message": "Success"
    }
}


def get_mock_ocr_response(document_type: str = "default") -> Dict[str, Any]:
    """
    Get a mock OCR response - currently returns a fixed hardcoded response.
    
    Args:
        document_type: Type of document to mock (ignored for now)
                      
    Returns:
        Fixed mock OCR response dictionary with patient ID and lien type
    """
    # Return fixed hardcoded response for now
    fixed_response = {
        "data": [
            {
                "info": {
                    "patient_id": "PRE6666666",
                    "accession_nums": ["ACC111111"],
                    "study_type": ["MRI"],
                    "patient_name": "Test Patient",
                    "study_date": "2024-03-01",
                    "body_part": "Knee",
                    "lien_type": "Rad Lien",
                    "document_type": "PSL",
                    "extracted_text": "Fixed mock OCR response for testing patient ID comments and lien classification."
                }
            }
        ],
        "message": "Success"
    }
    
    logger.info(f"Returning fixed mock OCR response with patient ID: PRE6666666 and lien_type: Rad Lien")
    return fixed_response


def get_mock_response_for_patient_id(patient_id: str) -> Dict[str, Any]:
    """
    Get a mock OCR response customized for a specific patient ID.
    
    Args:
        patient_id: Patient ID to include in the mock response
        
    Returns:
        Mock OCR response with the specified patient ID
    """
    response = MOCK_OCR_RESPONSES["default"].copy()
    if response.get("data") and len(response["data"]) > 0:
        response["data"][0]["info"]["patient_id"] = patient_id
    
    logger.info(f"Returning mock OCR response for patient ID: {patient_id}")
    return response


def determine_document_type_from_content(content_bytes: bytes, mock_ocr_type: str = None) -> str:
    """
    Attempt to determine document type from content for better mock responses.
    This is a simple heuristic-based approach for testing.
    
    Args:
        content_bytes: Document content as bytes
        mock_ocr_type: Optional override for mock OCR type in testing scenarios
        
    Returns:
        Estimated document type string
    """
    # If mock_ocr_type is provided (from test scenarios), use it directly
    if mock_ocr_type:
        logger.info(f"Using mock OCR type override: {mock_ocr_type}")
        return mock_ocr_type
    
    # Convert to string for parsing
    try:
        content_str = content_bytes.decode('utf-8', errors='ignore')
    except:
        return "default"
    
    # Check for embedded mock OCR type from test scenarios
    import re
    mock_type_match = re.search(r'%MOCK_OCR_TYPE:([^%]+)%', content_str)
    if mock_type_match:
        embedded_type = mock_type_match.group(1)
        logger.info(f"Found embedded mock OCR type: {embedded_type}")
        return embedded_type
    
    # Convert to lowercase for keyword matching
    content_str_lower = content_str.lower()
    
    # Simple keyword-based detection
    if any(word in content_str_lower for word in ['invoice', 'bill', 'payment', 'balance']):
        return "billing_document"
    elif any(word in content_str_lower for word in ['psl_radiology_lien', 'psl radiology', 'patient signed lien radiology']):
        return "psl_rad_lien_document"
    elif any(word in content_str_lower for word in ['psl_tech_lien', 'psl tech', 'patient signed lien tech']):
        return "psl_tech_lien_document"
    elif any(word in content_str_lower for word in ['asl_radiology_lien', 'asl radiology', 'attorney signed lien radiology']):
        return "asl_rad_lien_document"
    elif any(word in content_str_lower for word in ['asl_tech_lien', 'asl tech', 'attorney signed lien tech']):
        return "asl_tech_lien_document"
    elif any(word in content_str_lower for word in ['tech lien', 'technologist lien']):
        return "tech_lien_document"
    elif any(word in content_str_lower for word in ['rad lien', 'radiology lien', 'radiologist lien']):
        return "lien_document"  # This returns "Rad Lien"
    elif any(word in content_str_lower for word in ['lien', 'attorney', 'legal', 'case']):
        return "lien_document"  # Default lien type
    elif any(word in content_str_lower for word in ['appointment', 'schedule', 'time', 'date']):
        return "scheduling_document"
    elif any(word in content_str_lower for word in ['report', 'findings', 'radiology', 'diagnosis']):
        return "medical_records"
    else:
        return "default"