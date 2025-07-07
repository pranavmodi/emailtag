"""
Templates for Bill Balance Request responses.

This module contains templates used by the bill_balance_request_agent.py
to generate responses for "Bill or balance Request" emails.
"""

# Comprehensive Bill Balance Template with study details and pending studies
COMPREHENSIVE_BILL_BALANCE_TEMPLATE = """
{patient_header}
{bill_attachment_line}

{billing_status_table}

{lien_status_table}

To save time, you can access bills, reports, and e-sign liens in our portal:
<a href="http://precise.radflow360.com/">Precise Imaging Portal</a> (Click "Request Login" if you don't have an account)

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
"""

# Template for patient header with full details
PATIENT_HEADER_TEMPLATE = """
<b>Patient:</b> {patient_name}
<b>DOB:</b> {dob}
<b>DOI:</b> {doi}
<b>Patient ID:</b> {patient_id}
"""

# Fallback simple patient header
SIMPLE_PATIENT_HEADER_TEMPLATE = """Patient ID: {patient_id}"""

# Comprehensive Lien Reminder Template with patient header
COMPREHENSIVE_LIEN_REMINDER_TEMPLATE = """
{patient_header}

Thank you for your request. Please review the lien status below, as we are missing required signatures. A bill cannot be produced until all liens are signed.

{lien_status_table}

{billing_status_table}

To save time, you can e-sign liens in our portal:
<a href="http://precise.radflow360.com/">Precise Imaging Portal</a> (Click "Request Login" if you don't have an account)

Thank you,
Precise Imaging Billing Dept.
www.PreciseMRI.com
""" 