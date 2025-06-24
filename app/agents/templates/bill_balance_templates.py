"""
Templates for Bill Balance Request responses.

This module contains templates used by the bill_balance_request_agent.py
to generate responses for "Bill or balance Request" emails.
"""

# Comprehensive Bill Balance Template with study details and pending studies
COMPREHENSIVE_BILL_BALANCE_TEMPLATE = """
{patient_header}
Thank you for your request and for using Precise Imaging for your patient's imaging needs.
{bill_attachment_line}

Billing Status:
{billing_status_section}

{completed_studies_section}

{pending_studies_section}

Lien Status:
{lien_status_table}

To save time, you can download the bills in our portal which also contains the bill balance at the bottom.
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)

Thank you,
Precise Imaging Billing Dept.
"""

# Template for completed studies table
COMPLETED_STUDIES_TABLE_HEADER = """STUDY DESCRIPTION\tSTUDY DATE\tEXAM STATUS\tBILLING STATUS"""

# Template for pending studies section
PENDING_STUDIES_SECTION_TEMPLATE = """
There are pending studies that might be completed shortly. ${pending_amount:.2f} will be added to the bill balance once the studies below are completed:

STUDY DESCRIPTION\tSTUDY DATE\tEXAM STATUS\tBILLING STATUS
{pending_studies_rows}
"""

# Template for when no pending studies
NO_PENDING_STUDIES = ""

# Template for individual study row (completed)
COMPLETED_STUDY_ROW_TEMPLATE = """{study_description}\t{study_date}\t{exam_status}\t${amount:.2f} - Billed on {billed_date}"""

# Template for individual study row (pending)
PENDING_STUDY_ROW_TEMPLATE = """{study_description}\t{study_date}\t{exam_status}\tPotential amount to be billed ${amount:.2f}"""

# Template for lien status table row
LIEN_STATUS_ROW_TEMPLATE = """{lien_type}\t{patient_signature}\t{attorney_signature}"""

# Template for patient header with full details
PATIENT_HEADER_TEMPLATE = """{patient_id} - {patient_name} - DOB: {dob} - DOI: {doi}"""

# Fallback simple patient header
SIMPLE_PATIENT_HEADER_TEMPLATE = """Patient ID: {patient_id}""" 