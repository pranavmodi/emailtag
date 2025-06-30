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
{billing_status_table}

Lien Status:
{lien_status_table}

To save time, you can download the bills in our portal which also contains the bill balance at the bottom.
<a href="http://precise.radflow360.com/">Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)</a>

Thank you,
Precise Imaging Billing Dept.
http://www.PreciseMRI.com
"""



# Template for patient header with full details
PATIENT_HEADER_TEMPLATE = """{patient_id} - {patient_name} - DOB: {dob} - DOI: {doi}"""

# Fallback simple patient header
SIMPLE_PATIENT_HEADER_TEMPLATE = """Patient ID: {patient_id}"""

# Comprehensive Lien Reminder Template with patient header
COMPREHENSIVE_LIEN_REMINDER_TEMPLATE = """
{patient_header}
Thank you for your request and for using Precise Imaging for your patient's imaging needs.

Billing Status:
Please review the lien status as we are missing signed liens which must be signed before a bill is produced.

Lien Status:
{lien_status_table}


To save time, you can download the bills in our portal which also contains the bill balance at the bottom.
<a href="http://precise.radflow360.com/">Access bills, appointment times, and e-sign liens (Click request login if you don't have an account)</a>

Thank you,
Precise Imaging Billing Dept.
http://www.PreciseMRI.com
""" 