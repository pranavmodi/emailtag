# app/agents/templates/appointment_status_templates.py

TEMPLATE_APPOINTMENT_FOUND_DETAILED = """Patient ID: {patient_id_confirmed}

Study ID: {first_study_id} - {first_exam_description}
I have confirmed that this study has been scheduled.
Appointment Date/Time: {first_appointment_datetime_str}. Please arrive 15 minutes before the exam time at {first_arrival_time_str}
Appointment Location: {first_location_name}

Our direct scheduling phone # is {scheduling_phone} and we can assist with directions, rescheduling, canceling, or any other scheduling-related questions.
{no_show_policy}

Here is a summary of the patient's exams we currently have entered into our system:
Study ID | Exam Description | Status | Study Date | Location | Images Available | Report Available
---------|------------------|--------|------------|----------|------------------|-----------------
{studies_table_rows}

{personal_injury_info}
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account): {bills_link}
Access reports & images (Request login here for reports): {reports_link}
"""

TEMPLATE_REQUEST_PATIENT_ID = "To help me find your appointment status, could you please provide your Patient ID?"

TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE = "Thank you for the information. We're still having trouble locating your appointment details without a Patient ID. A member of our team will personally review your request and get back to you shortly."

TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID = "We found your Patient ID: {patient_id}, but could not find any upcoming appointments. If you believe this is an error, please provide the approximate date and type of your exam so our team can investigate further. A member of our team will also review this request."

TEMPLATE_DB_ERROR = "We encountered a technical difficulty while trying to fetch your appointment details for Patient ID: {patient_id}. Our team has been notified and will look into this." 