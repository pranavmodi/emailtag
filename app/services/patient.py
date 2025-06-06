"""Patient information service."""

import json
import logging
import traceback
from typing import Dict, List, Optional, Any

import httpx
import requests
from dotenv import load_dotenv
import os

from app.core.config import settings

# Initialize logger
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Get RadFlow API URL from environment with a default value
RADFLOW_API_URL = os.getenv("RADFLOW_API_URL", "https://app.radflow360.com/chatbotapi/Patient/GetPatientStudyRelatedDetails")

def get_headers() -> Dict[str, str]:
    """
    Get headers for backend API requests.
    
    Returns:
        Dict[str, str]: Headers for API requests
    """
    return {
        "Authorization": f"Bearer {settings.BACKEND_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

def process_patient_data(data: Dict[str, Any], phone: str) -> Dict[str, Any]:
    """
    Process patient data from API response and store in unified store.
    
    Args:
        data (Dict[str, Any]): Raw API response data
        phone (str): Phone number for indexing
        
    Returns:
        Dict[str, Any]: Success status and message
    """
    try:
        # Check if the API response was successful
        if data.get("responseStatus") != "Success":
            logger.error("API response status indicates failure")
            return {
                "success": False,
                "error": data.get("exception") or "API response indicates failure"
            }

        result = data.get("result", {})
        patient_data_list = []
        
        # Handle the nested JSON string in result.result
        if isinstance(result.get("result"), str):
            try:
                patient_data_list = json.loads(result["result"])
            except json.JSONDecodeError:
                logger.error("Failed to parse nested JSON string in result.result")
                return {
                    "success": False,
                    "error": "Failed to parse patient data"
                }
        elif isinstance(result.get("result"), list):
            patient_data_list = result["result"]
            
        # Get total patients from response
        total_patients = result.get("totalPatients", len(patient_data_list))
            
        if not patient_data_list:
            return {
                "success": False,
                "error": "No patients found"
            }
            
        # Create numbered list of patients
        numbered_list = []
        transformed_patients = []
        
        for i, patient in enumerate(patient_data_list, 1):
            # Transform patient data to match our schema
            transformed_patient = {
                "patient_id": patient.get("PatientId", ""),
                "first_name": patient.get("FirstName", ""),
                "last_name": patient.get("LastName", ""),
                "phone": patient.get("Phone", phone),  # Use provided phone if not in data
                "sex": patient.get("Sex", "").strip(),  # Remove trailing spaces
                "financial_type": patient.get("FinancialTypeName", ""),
                "language": patient.get("LANGUAGE", ""),
                "birth_date": patient.get("BirthDate", ""),
                "address": patient.get("ADDRESS", ""),
                "doi": patient.get("Doi", ""),
                "dol": patient.get("DOL", ""),
                "radiologist_name": patient.get("RadiologistName", "")
            }
            transformed_patients.append(transformed_patient)
            
            # Create numbered list entry
            name = f"{transformed_patient['first_name']} {transformed_patient['last_name']}".strip()
            patient_id = transformed_patient["patient_id"]
            numbered_list.append(f"<button>{i}. {name} (ID: {patient_id})</button>")
        
        return {
            "success": True,
            "message": f"Successfully processed {total_patients} patients",
            "patients": transformed_patients,
            "numbered_list": "\n".join(numbered_list)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to process patient data: {str(e)}"
        }

async def fetch_patient_data(phone: str) -> Dict[str, Any]:
    """
    Fetch patient data from the API.
    
    Args:
        phone (str): Phone number to fetch data for
        
    Returns:
        Dict[str, Any]: API response with patient data
    """
    try:
        logger.info(f"Fetching patient data for phone: {phone}")
        
        # Remove +1 prefix if present for consistency
        storage_phone = phone.replace("+1", "")
        logger.debug(f"Standardized phone number to: {storage_phone}")
        
        payload = {
            "patientId": "",
            "phone": storage_phone,
            "firstName": "",
            "lastName": "",
            "birthDate": "",
            "doi": "",
            "accessionNumber": "",
            "requiredField": "Details"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making API request to {RADFLOW_API_URL} with payload: {json.dumps(payload)}")
        
        async with httpx.AsyncClient(verify=False) as client:
            logger.debug("Created httpx client")
            
            try:
                response = await client.post(
                    RADFLOW_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                logger.debug(f"Received API response with status code: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"API request failed with status {response.status_code}: {response.text}")
                    return {
                        "success": False,
                        "error": f"API request failed with status {response.status_code}"
                    }
                
                try:
                    data = response.json()
                    logger.debug("Successfully parsed JSON response")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}\nResponse text: {response.text[:500]}")
                    return {
                        "success": False,
                        "error": "Invalid JSON response from API"
                    }
                
                logger.info(f"Processing patient data response for phone: {storage_phone}")
                result = process_patient_data(data, storage_phone)
                
                if result["success"]:
                    logger.info(f"Successfully retrieved patient data: {result['message']}")
                else:
                    logger.error(f"Failed to process patient data: {result.get('error', 'Unknown error')}")
                
                return result
            except httpx.TimeoutException:
                logger.error(f"API request timed out after 30 seconds")
                return {
                    "success": False,
                    "error": "API request timed out after 30 seconds"
                }
            except httpx.ConnectError as e:
                logger.error(f"Connection error while fetching patient data: {str(e)}")
                return {
                    "success": False,
                    "error": f"Connection error: {str(e)}"
                }
                
    except Exception as e:
        logger.error(f"Unexpected error in fetch_patient_data: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Failed to fetch patient data: {str(e)}"
        }

async def fetch_study_details(patient_id: str) -> Dict[str, Any]:
    """
    Fetch study details for a patient and store them.
    
    Args:
        patient_id (str): Patient ID to fetch studies for
        
    Returns:
        Dict[str, Any]: Success status and message
    """
    try:
        payload = {
            "patientId": patient_id,
            "phone": "",
            "firstName": "",
            "lastName": "",
            "birthDate": "",
            "doi": "",
            "accessionNumber": "",
            "requiredField": "Study Details"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                RADFLOW_API_URL,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            
            response.raise_for_status()
            
            try:
                data = response.json()

                # Check response status
                if data.get("responseStatus") != "Success":
                    error_msg = data.get("exception") or "Failed to fetch study details"
                    return {
                        "success": False,
                        "error": error_msg
                    }

                # Extract studies from nested result
                result = data.get("result", {})
                
                raw_studies = []
                if isinstance(result.get("result"), str):
                    try:
                        raw_studies = json.loads(result["result"])
                    except json.JSONDecodeError:
                        return {
                            "success": False,
                            "error": "Failed to parse study data"
                        }
                elif isinstance(result.get("result"), list):
                    raw_studies = result["result"]
                
                if not raw_studies:
                    return {
                        "success": False,
                        "error": "No studies found"
                    }
                
                # Transform studies to match our schema
                transformed_studies = []
                for study in raw_studies:
                    # Get the latest status from AppointmentStatuses if available
                    latest_status = "Unknown"
                    scheduled_time = ""
                    if study.get("AppointmentStatuses"):
                        for status in study["AppointmentStatuses"]:
                            if status.get("Status"):
                                latest_status = status["Status"]
                            if status.get("ScheduledFor") and status["ScheduledFor"] != "Not Yet Scheduled":
                                scheduled_time = status["ScheduledFor"]
                    
                    # Get facility info from FacilityUsed if available
                    facility_name = ""
                    facility_address = ""
                    if study.get("FacilityUsed") and len(study["FacilityUsed"]) > 0:
                        facility = study["FacilityUsed"][0]  # Take first facility
                        facility_name = facility.get("FacilityName", "")
                        facility_address = facility.get("Address", "")

                    transformed_study = {
                        "appointment_time": scheduled_time,
                        "pre_arrival_minutes": 30,  # Default value
                        "facility": {
                            "facility_name": facility_name,
                            "address": facility_address
                        },
                        "study_description": study.get("StudyDescription", ""),
                        "status": latest_status,
                        "modality": study.get("Modality", ""),
                        "referring_physician": study.get("SchedulerName", "").strip(),
                        "insurance": "",  # Not provided in API
                        "authorization_number": study.get("AccessionNumber", "")
                    }
                    transformed_studies.append(transformed_study)
                
                return {
                    "success": True,
                    "message": f"Successfully retrieved {len(transformed_studies)} studies for patient {patient_id}",
                    "studies": transformed_studies
                }
            
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Failed to process study details: {str(e)}"
                }
            
    except httpx.HTTPStatusError as e:
        return {
            "success": False,
            "error": f"HTTP error {e.response.status_code}: {str(e)}"
        }
    except httpx.RequestError as e:
        return {
            "success": False,
            "error": f"Request failed: {str(e)}"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to fetch study details: {str(e)}"
        }

async def fetch_patient_by_id(patient_id: str) -> Dict[str, Any]:
    """
    Fetch patient information by ID from the RadFlow API.
    
    Args:
        patient_id: The patient's ID
        
    Returns:
        Dict[str, Any]: Patient information and status
    """
    try:
        logger.info(f"Fetching patient data for ID: {patient_id}")
        
        payload = {
            "patientId": patient_id,
            "phone": "",
            "firstName": "",
            "lastName": "",
            "birthDate": "",
            "doi": "",
            "accessionNumber": "",
            "requiredField": "Details"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                RADFLOW_API_URL,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return {
                    "success": False,
                    "error": f"API request failed with status {response.status_code}"
                }
            
            try:
                data = response.json()
                logger.debug("Successfully parsed JSON response")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}\nResponse text: {response.text[:500]}")
                return {
                    "success": False,
                    "error": "Invalid JSON response from API"
                }
            
            logger.info(f"Processing patient data response for ID: {patient_id}")
            result = process_patient_data(data, "")
            
            if result["success"]:
                logger.info(f"Successfully retrieved patient data: {result['message']}")
            else:
                logger.error(f"Failed to process patient data: {result.get('error', 'Unknown error')}")
            
            return result
            
    except Exception as e:
        logger.error(f"Unexpected error in fetch_patient_by_id: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Failed to fetch patient data: {str(e)}"
        }

async def fetch_patient_by_name_dob(first_name: str, last_name: str, birth_date: str) -> Dict[str, Any]:
    """
    Fetch patient information by name and date of birth from the RadFlow API.
    
    Args:
        first_name: Patient's first name
        last_name: Patient's last name
        birth_date: Patient's date of birth in YYYY-MM-DD format
        
    Returns:
        Dict[str, Any]: Patient information and status
    """
    try:
        logger.info(f"Fetching patient data for name: {first_name} {last_name}, DOB: {birth_date}")
        
        payload = {
            "patientId": "",
            "phone": "",
            "firstName": first_name,
            "lastName": last_name,
            "birthDate": birth_date,
            "doi": "",
            "accessionNumber": "",
            "requiredField": "Details"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient(verify=False) as client:
            response = await client.post(
                RADFLOW_API_URL,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            
            if response.status_code != 200:
                logger.error(f"API request failed with status {response.status_code}: {response.text}")
                return {
                    "success": False,
                    "error": f"API request failed with status {response.status_code}"
                }
            
            try:
                data = response.json()
                logger.debug("Successfully parsed JSON response")
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}\nResponse text: {response.text[:500]}")
                return {
                    "success": False,
                    "error": "Invalid JSON response from API"
                }
            
            logger.info(f"Processing patient data response for name: {first_name} {last_name}, DOB: {birth_date}")
            result = process_patient_data(data, "")
            
            if result["success"]:
                logger.info(f"Successfully retrieved patient data: {result['message']}")
            else:
                logger.error(f"Failed to process patient data: {result.get('error', 'Unknown error')}")
            
            return result
            
    except Exception as e:
        logger.error(f"Unexpected error in fetch_patient_by_name_dob: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Failed to fetch patient data: {str(e)}"
        }

async def get_patient_by_phone(phone: str) -> Dict[str, Any]:
    """
    Get patient information by phone number from the backend API.
    
    Args:
        phone: Patient's phone number
        
    Returns:
        Dict[str, Any]: Patient information and status
    """
    return await fetch_patient_data(phone)

async def get_patient_by_id(patient_id: str) -> Dict[str, Any]:
    """
    Get patient information by ID from the backend API.
    
    Args:
        patient_id: The patient's ID
        
    Returns:
        Dict[str, Any]: Patient information and status
    """
    return await fetch_patient_by_id(patient_id)

async def get_patient_by_name_dob(first_name: str, last_name: str, birth_date: str) -> Dict[str, Any]:
    """
    Get patient information by name and date of birth from the backend API.
    
    Args:
        first_name: Patient's first name
        last_name: Patient's last name
        birth_date: Patient's date of birth in YYYY-MM-DD format
        
    Returns:
        Dict[str, Any]: Patient information and status
    """
    return await fetch_patient_by_name_dob(first_name, last_name, birth_date)

async def get_patient_studies(patient_id: str) -> Dict[str, Any]:
    """
    Get patient's studies from the backend API.
    
    Args:
        patient_id: The patient's ID
        
    Returns:
        Dict[str, Any]: Study information and status
    """
    return await fetch_study_details(patient_id)

async def _fetch_patient_study_data(patient_id: str) -> Dict[str, Any]:
    """
    Fetch patient study data from the API.
    
    Args:
        patient_id (str): Patient ID to fetch studies for
        
    Returns:
        Dict[str, Any]: API response with patient study data
    """
    try:
        logger.info(f"Fetching patient study data for ID: {patient_id}")
        
        payload = {
            "patientId": patient_id,
            "phone": "",
            "firstName": "",
            "lastName": "",
            "birthDate": "",
            "doi": "",
            "accessionNumber": "",
            "requiredField": "Study Details"
        }
        
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Making API request to {RADFLOW_API_URL} with payload: {json.dumps(payload)}")
        
        async with httpx.AsyncClient(verify=False) as client:
            logger.debug("Created httpx client")
            
            try:
                response = await client.post(
                    RADFLOW_API_URL,
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )
                logger.debug(f"Received API response with status code: {response.status_code}")
                
                if response.status_code != 200:
                    logger.error(f"API request failed with status {response.status_code}: {response.text}")
                    return {
                        "success": False,
                        "error": f"API request failed with status {response.status_code}"
                    }
                
                try:
                    data = response.json()
                    logger.debug("Successfully parsed JSON response")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}\nResponse text: {response.text[:500]}")
                    return {
                        "success": False,
                        "error": "Invalid JSON response from API"
                    }
                
                # Check response status
                if data.get("responseStatus") != "Success":
                    error_msg = data.get("exception") or "Failed to fetch study details"
                    return {
                        "success": False,
                        "error": error_msg
                    }

                # Extract studies from nested result
                result = data.get("result", {})
                
                raw_studies = []
                if isinstance(result.get("result"), str):
                    try:
                        raw_studies = json.loads(result["result"])
                    except json.JSONDecodeError:
                        return {
                            "success": False,
                            "error": "Failed to parse study data"
                        }
                elif isinstance(result.get("result"), list):
                    raw_studies = result["result"]
                
                if not raw_studies:
                    return {
                        "success": False,
                        "error": "No studies found"
                    }
                
                # Transform studies to match our schema
                transformed_studies = []
                for study in raw_studies:
                    # Get the latest status from AppointmentStatuses if available
                    latest_status = "Unknown"
                    scheduled_time = ""
                    if study.get("AppointmentStatuses"):
                        for status in study["AppointmentStatuses"]:
                            if status.get("Status"):
                                latest_status = status["Status"]
                            if status.get("ScheduledFor") and status["ScheduledFor"] != "Not Yet Scheduled":
                                scheduled_time = status["ScheduledFor"]
                    
                    # Get facility info from FacilityUsed if available
                    facility_name = ""
                    facility_address = ""
                    if study.get("FacilityUsed") and len(study["FacilityUsed"]) > 0:
                        facility = study["FacilityUsed"][0]  # Take first facility
                        facility_name = facility.get("FacilityName", "")
                        facility_address = facility.get("Address", "")

                    transformed_study = {
                        "appointment_time": scheduled_time,
                        "pre_arrival_minutes": 30,  # Default value
                        "facility": {
                            "facility_name": facility_name,
                            "address": facility_address
                        },
                        "study_description": study.get("StudyDescription", ""),
                        "status": latest_status,
                        "modality": study.get("Modality", ""),
                        "referring_physician": study.get("SchedulerName", "").strip(),
                        "insurance": "",  # Not provided in API
                        "authorization_number": study.get("AccessionNumber", "")
                    }
                    transformed_studies.append(transformed_study)
                
                result = {
                    "success": True,
                    "message": f"Successfully retrieved {len(transformed_studies)} studies for patient {patient_id}",
                    "studies": transformed_studies
                }
                
                if result["success"]:
                    logger.info(f"Successfully retrieved patient study data: {result['message']}")
                else:
                    logger.error(f"Failed to process patient study data: {result.get('error', 'Unknown error')}")
                
                return result
                
            except httpx.TimeoutException:
                logger.error(f"API request timed out after 30 seconds")
                return {
                    "success": False,
                    "error": "API request timed out after 30 seconds"
                }
            except httpx.ConnectError as e:
                logger.error(f"Connection error while fetching patient study data: {str(e)}")
                return {
                    "success": False,
                    "error": f"Connection error: {str(e)}"
                }
                
    except Exception as e:
        logger.error(f"Unexpected error in _fetch_patient_study_data: {str(e)}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "error": f"Failed to fetch patient study data: {str(e)}"
        } 