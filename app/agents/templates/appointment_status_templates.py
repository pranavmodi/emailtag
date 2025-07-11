# app/agents/templates/appointment_status_templates.py

TEMPLATE_APPOINTMENT_FOUND_DETAILED = """Patient ID: {patient_id_confirmed}<br/><br/>

Study ID: {first_study_id} - {first_exam_description}<br/>
I have information about this study.<br/>
Study Date/Time: {first_appointment_datetime_str}<br/>
Study Location: {first_location_name}<br/><br/>

Our direct scheduling phone # is {scheduling_phone} and we can assist with directions, rescheduling, canceling, or any other scheduling-related questions.<br/>
{no_show_policy}<br/><br/>

Here is a summary of the patient's exams we currently have entered into our system:<br/><table border="1" style="border-collapse: collapse; width: 100%;">
    <thead>
        <tr>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Study ID</th>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Exam Description</th>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Status</th>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Study Date/Time</th>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Location</th>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Images Available</th>
            <th style="border: 1px solid black; padding: 8px; text-align: left;">Report Available</th>
        </tr>
    </thead>
    <tbody>{studies_table_rows}</tbody>
</table>
<br/>
{personal_injury_info}
Access bills, appointment times, and e-sign liens (Click request login if you don't have an account): <a href="{bills_link}">Click Here</a><br/>
Access reports & images (Request login here for reports): <a href="{reports_link}">Click Here</a><br/>
"""

# Note: TEMPLATE_REQUEST_PATIENT_ID and TEMPLATE_REQUEST_PATIENT_ID_AGAIN_ESCALATE 
# have been moved to shared_templates.py since they're used by multiple agents

TEMPLATE_APPOINTMENT_NOT_FOUND_FOR_ID = "We found your Patient ID: {patient_id}, but could not find any upcoming appointments. If you believe this is an error, please provide the approximate date and type of your exam so our team can investigate further. A member of our team will also review this request."

TEMPLATE_DB_ERROR = "We encountered a technical difficulty while trying to fetch your appointment details for Patient ID: {patient_id}. Our team has been notified and will look into this." 