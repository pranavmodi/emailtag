"""
Client evaluation email test scenarios for Front tagging system.
These scenarios are designed to test real-world client email patterns.
"""

CLIENT_EVAL_SCENARIOS = {
    "1": {
        "description": "Edy Posas-Valdes - Apt status req - Client following up on imaging status with DOL 04/07/2025",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Edy Posas- Valdes DOL: 04/07/2025</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt status req"]
    },
    "2": {
        "description": "Servando Zamora - Apt status req - Client following up on imaging status with DOL 07/27/2023, testing similar phrasing to scenario 1",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Servando Zamora - DOL 07/27/2023</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt status req"]
    },
    "3": {
        "description": "Servando Zamora - Sent payment but not received - Complex payment settlement with multiple check details and law firm correspondence",
        "subject": "RE: Servando Zamora, 07/27/2023",
        "body_html": (
            "<p>Good afternoon,</p>"
            "<p>Please find enclosed two checks from Reflow 360 representing an update regarding this case. We have already settled this matter with your office and issued payment. I believe your office is continuing to send redundant statements. Kindly update your records and block this client from the client list. If you can update your files, I'd be very appreciative before it reflects on our records.</p>"
            "<p>Check info:<br>"
            "Servando Zamora Date: 05/06/2024 - $1200.00 - Check #1344<br>"
            "Servando Zamora Date: 06/03/2024 - $1300.00 - Check #1348</p>"
            "<p>Sincerely yours,<br>"
            "Kayla Jacobs<br>"
            "Lien Negotiator<br>"
            "TRISH LAW FIRM<br>"
            "4 ATTORNEYS ADVOCATES<br>"
            "7357 Wilshire Blvd., Suite 600</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "4": {
        "description": "Servando Zamora - Sent payment but not received - Simple case with clear patient name (06/01/2024 DOI) for testing OpenAI patient extraction",
        "subject": "Payment Sent - Servando Zamora",
        "body_html": (
            "<p>Hello,</p>"
            "<p>This is regarding our client Servando Zamora who was injured on 06/01/2024.</p>"
            "<p>We sent payment via check #4567 on 12/01/2024 for $2500.00 but our records show you are still billing us.</p>"
            "<p>Please update your records as this matter has been settled.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "5": {
        "description": "Servando Zamora - Sent payment but not received - Patient details in subject line (06/01/2024 DOI) for testing subject line extraction capabilities",
        "subject": "RE: Servando Zamora, 06/01/2024 - Payment Already Sent",
        "body_html": (
            "<p>Good morning,</p>"
            "<p>We are writing to inform you that payment for this case was already processed.</p>"
            "<p>Check #7890 was sent on 11/15/2024 in the amount of $1800.00.</p>"
            "<p>Please stop sending statements and update your billing records.</p>"
            "<p>Thank you for your attention to this matter.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "6": {
        "description": "Edy Posas-Valdes - Apt status req - Forwarded email from Danny Rackow testing forwarded message parsing and patient extraction with DOL 04/07/2025",
        "subject": "I am following up to see if our client got imaging's done.",
        "body_html": (
            "<p>Danny Rackow<br>"
            "To: test123abc@mediflow360.com<br>"
            "Jul 17, 12:21 PM</p>"
            "<p>———— Forwarded message ————<br>"
            "From: drackow2008@gmail.com<br>"
            "Date: July 10, 2025 at 11:24 AM PDT<br>"
            "Subject: I am following up to see if our client got imaging's done.<br>"
            "To: test123abc@mediflow360.com</p>"
            "<p>I am following up to see if our client got imaging's done.</p>"
            "<p>Edy Posas-Valdes DOL: 04/07/2025</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt status req"]
    },
    "7": {
        "description": "Servando Zamora - Sent payment but not received - Nested forwarded messages with multiple DOL dates (07/27/2023 & 06/01/2024) testing complex email parsing and payment settlement claims",
        "subject": "EXTERNAL: RE: Servando Zamora, 07/27/2023",
        "body_html": (
            "<p>———— Forwarded message ————<br>"
            "From: billing@precisemri.com<br>"
            "Date: July 10, 2025 at 11:12 AM PDT<br>"
            "Subject: EXTERNAL: RE: Servando Zamora, 07/27/2023<br>"
            "To: test123abc@mediflow360.com</p>"
            "<p>- Danny Rackow</p>"
            "<p>How did I do? ⭐️⭐️⭐️⭐️⭐️</p>"
            "<p>———— Forwarded message ————<br>"
            "From: angela@tishbilaw.com<br>"
            "Date: July 1, 2025 at 11:51 AM PDT<br>"
            "Subject: EXTERNAL: RE: Servando Zamora, 07/27/2023<br>"
            "To: negotiation@precisemri.com</p>"
            "<p>⸻</p>"
            "<p>Good afternoon,</p>"
            "<p>We received an email from RadFlow 360 requesting for an update regarding this case. We already settled this matter with your office and issued payment. I believe your office is confusing both DOL cases. We settled both cases with your office and both checks have cleared in the bank. If you can update your files. If you have any questions please let us know.</p>"
            "<p>Servando Zamora – DOL 07/27/2023 – $1,150.00 Check # 12680<br>"
            "Servando Zamora – DOL 06/01/2024 – $1,150.00 Check # 12843</p>"
            "<p>Thank you,</p>"
            "<p>–</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Sent payment but not received"]
    },
    "8": {
        "description": "Ramon Cabrera - Lien Modified (Positive) - PSL lien document with crossed out sections, should trigger lien modification detection",
        "subject": "RE: Ramon Cabrera, PRE1049827 - PSL Lien Documents",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached the PSL lien documents for our client Ramon Cabrera (Patient ID: PRE1049827).</p>"
            "<p>Please review and process the attached lien documentation.</p>"
            "<p>Let us know if you need any additional information to complete the processing.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Best regards,<br>"
            "Attorney Services</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "PRE1049827 – Cabrera, Ramon crossed out liens.pdf",
                "filepath": "scripts/PRE1049827 – Cabrera, Ramon crossed out liens.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified"]
    },
    "9": {
        "description": "Maria Rodriguez - ASL Clean (Negative) - Clean document without modifications, should maintain original ASL tag and not trigger lien modification detection",
        "subject": "RE: Maria Rodriguez, 03/15/2024 - ASL Lien Submission",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>Attached please find the completed Attorney Service Lien (ASL) for our client Maria Rodriguez who was injured on 03/15/2024.</p>"
            "<p>This is a clean, unmodified document as per standard procedures.</p>"
            "<p>Please review and process the attached ASL lien for radiology services.</p>"
            "<p>The document is complete and requires no further modifications.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Sincerely,<br>"
            "Legal Processing Team<br>"
            "Rodriguez & Associates</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "OCR APIs Doc Classifier.pdf", 
                "filepath": "scripts/OCR APIs Doc Classifier.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL"]
    },
    "10": {
        "description": "Juana Perez Cordero - Apt status req - Client inquiry about open MRI scheduling status with Patient ID PRE1063320",
        "subject": "Is the patient scheduled for an open MRI?",
        "body_html": (
            "<p>Is the patient scheduled for an open MRI?</p>"
            "<p>Patient ID: PRE1063320- JUANA PEREZ CORDERO</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt status req"]
    },
    "11": {
        "description": "OCR Rad Lien Override - Email with attachment containing Rad Lien OCR data, should override LLM classification",
        "subject": "Radiology Lien Documentation - PRE3456789",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>Attached is the radiology lien documentation for Patient ID PRE3456789.</p>"
            "<p>Please process the attached lien documentation.</p>"
            "<p>Thank you.</p>"
            "<p>Attorney Services</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "radiology_lien_document.pdf",
                "filepath": "scripts/radiology_lien_document.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Rad Lien"]
    },
    "12": {
        "description": "OCR Tech Lien Override - Email with attachment containing Tech Lien OCR data, should override LLM classification",
        "subject": "Tech Lien Documentation - PRE7890123",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>Attached is the tech lien documentation for Patient ID PRE7890123.</p>"
            "<p>Please process the attached lien documentation.</p>"
            "<p>Thank you.</p>"
            "<p>Johnson & Partners</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "tech_lien_document.pdf",
                "filepath": "scripts/tech_lien_document.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Tech Lien"]
    },
    "13": {
        "description": "OCR No Override - Missing Lien Request should not be overridden by OCR",
        "subject": "Missing Lien Request - PRE1234567",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>We need the missing lien documentation for Patient ID PRE1234567.</p>"
            "<p>Please provide the missing lien documents.</p>"
            "<p>Thank you.</p>"
            "<p>Legal Processing Team</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "sample_document.pdf", 
                "filepath": "scripts/radiology_lien_document.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Missing Lien Request"]
    },
    "14": {
        "description": "OCR No Override - Non-lien email should not be affected by OCR lien data",
        "subject": "Schedule MRI Appointment - PRE5555555",
        "body_html": (
            "<p>Dear Scheduling Team,</p>"
            "<p>Please schedule an MRI appointment for Patient ID PRE5555555.</p>"
            "<p>Please provide available time slots for next week.</p>"
            "<p>Thank you.</p>"
            "<p>Medical Coordinator</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "irrelevant_document.pdf",
                "filepath": "scripts/radiology_lien_document.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Schedule Request"]
    },
    "15": {
        "description": "OCR PSL Rad Lien Override - Email classified as PSL with Rad Lien OCR data (sent by patient)",
        "subject": "My Radiology Lien Documents - PRE6666666",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am sending my signed radiology lien documentation for Patient ID PRE6666666.</p>"
            "<p>Please process the attached lien documentation.</p>"
            "<p>Thank you.</p>"
            "<p>John Smith (Patient)</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "psl_radiology_lien.pdf",
                "filepath": "scripts/psl_radiology_lien.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Rad Lien"]
    },
    "16": {
        "description": "OCR PSL Tech Lien Override - Email classified as PSL with Tech Lien OCR data (sent by patient)",
        "subject": "My Tech Lien Documents - PRE7777777",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>I am sending my signed tech lien documentation for Patient ID PRE7777777.</p>"
            "<p>Please process the attached lien documentation.</p>"
            "<p>Thank you.</p>"
            "<p>Maria Rodriguez (Patient)</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "psl_tech_lien.pdf",
                "filepath": "scripts/psl_tech_lien.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Tech Lien"]
    },
    "17": {
        "description": "OCR ASL Rad Lien Override - Email classified as ASL with Rad Lien OCR data (sent by attorney)",
        "subject": "Client Radiology Lien Documentation - PRE8888888",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached the attorney signed radiology lien documentation for our client, Patient ID PRE8888888.</p>"
            "<p>This ASL lien has been executed and is ready for processing.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Best regards,<br>Sarah Johnson, Esq.<br>Johnson & Associates Law Firm</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "asl_radiology_lien.pdf",
                "filepath": "scripts/asl_radiology_lien.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Rad Lien"]
    },
    "18": {
        "description": "OCR ASL Tech Lien Override - Email classified as ASL with Tech Lien OCR data (sent by attorney)",
        "subject": "Client Tech Lien Documentation - PRE9999999",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached the attorney signed tech lien documentation for our client, Patient ID PRE9999999.</p>"
            "<p>This ASL lien has been executed and is ready for processing.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Best regards,<br>Michael Davis, Esq.<br>Davis & Partners Law Firm</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "asl_tech_lien.pdf",
                "filepath": "scripts/asl_tech_lien.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Tech Lien"]
    },
    "19": {
        "description": "Lien Modified with Strikethrough - PDF with visual strikethrough effects should trigger lien modification detection",
        "subject": "Lien Documentation - PRE1049827", 
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached the lien documentation for Patient ID PRE1049827.</p>"
            "<p>Please process the attached lien documentation.</p>"
            "<p>Thank you for your prompt attention to this matter.</p>"
            "<p>Best regards,<br>Legal Services Inc.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "modified_lien_document.pdf",
                "filepath": "scripts/modified_lien_document.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["PSL", "Rad Lien", "Lien Modified"]
    },
    "20": {
        "description": "Tharanga Chamara Wickramaarachchi - Apt status req - Client inquiry with DOB instead of DOL",
        "subject": "ggjgj",
        "body_html": (
            "<p>Good afternoon Team</p>"
            "<p>May we kindly confirm the appointment date and time for the client below, please?</p>"
            "<p>Tharanga Chamara Wickramaarachchi</p>"
            "<p>DOB 08/14/1980</p>"
            "<p>Thank you for the assistance</p>"
            "<p>Thanks,</p>"
            "<p>Enjoying our service? Please share your experience with Google. Thank you for putting your faith in Power Liens!</p>"
            "<p>Rocky Jay So<br>"
            "Client Relations</p>"
            "<p>Email: rocky@powerliens.com<br>"
            "Web: www.powerliens.com<br>"
            "Toll-Free: 800.680.5526</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Apt status req"]
    },
    "21": {
        "description": "Generic acknowledgment/thank you - Simple follow-up acknowledgment message",
        "subject": "Follow-up Response",
        "body_html": (
            "<p>Good afternoon Veronica,</p>"
            "<p>Thank you for following up on this matter.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": []
    },
    "22": {
        "description": "Imported from Front conversation cnv_1gip9rmj",
        "subject": "Fw: EXTERNAL: Re: Antonia Garcia",
        "body_html": (
            """
[Sent from Front]
----------- Forwarded message -----------
From: drackow2008@gmail.com<mailto:drackow2008@gmail.com>
Date: August 28, 2025 at 10:58 PM GMT+5:30
Subject: EXTERNAL: Re: Antonia Garcia
To: test123abc@mediflow360.com<mailto:test123abc@mediflow360.com>

----------- Forwarded message -----------
From: phillip@sepulvedalawgroup.com<mailto:phillip@sepulvedalawgroup.com>
Date: August 15, 2025 at 2:36 PM PDT
Subject: EXTERNAL: Re: Antonia Garcia
To: scheduling@precisemri.com<mailto:scheduling@precisemri.com>
Cc: 2111774@bcc.casepeer.com<mailto:2111774@bcc.casepeer.com>

Hello!

This current patient has been recommended for additional MRI and xrays. See attached. Thanks!

This communication is the property of Sepulveda Sanchez Accident Lawyers/Sepulveda Law Group and may contain confidential or privileged information. Unauthorized use of this communication is strictly prohibited and may be unlawful. If you have received this communication in error, please immediately notify the sender by replying to this e-mail and destroy all copies of the communication and any attachments.



Regards,


PHILLIP CUARTAS
Case Manager

[Sepulveda Sanchez Accident Lawyers]<https://sepulvedalawgroup.com/>
Los Angeles  |  Stockton  |  New York

W: sepulvedalawgroup.com<http://sepulvedalawgroup.com/>
P: (213) 426-1051
F: (213) 426-1052
A: 3530 Wilshire Blvd, Suite 1515, Los Angeles, CA 90010
_________________________________________

[image.png]


On Wed, Apr 2, 2025 at 2:22 PM Phillip Cuartas <phillip@sepulvedalawgroup.com<mailto:phillip@sepulvedalawgroup.com>> wrote:
Hello,

This client has been recommended another MRI with your office for her lumbar spine. Below are her demographics and attached is the MRI referral:

Name: Antonia Garcia
DOL:  07/12/2024
DOB: 12/29/1963
Address: 2340 Sanguinetti Ln Sp 4, Stockton, CA, 95205
Contact: (209) 938-9340



Notice Regarding Electronic Service
E-Service pursuant to C.C.P. §1010.6(e), CRC 2.251 and any other applicable statute or rule, IS DEEMED INVALID UNLESS SERVED TO THE FOLLOWING DESIGNATED EMAIL ADDRESSES:     eservice@sepulvedalawgroup.com<mailto:eservice@sepulvedalawgroup.com>

This communication is the property of Sepulveda Sanchez Accident Lawyers/Sepulveda Law Group and may contain confidential or privileged information. Unauthorized use of this communication is strictly prohibited and may be unlawful. If you have received this communication in error, please immediately notify the sender by replying to this e-mail and destroy all copies of the communication and any attachments.



Regards,


PHILLIP CUARTAS
Case Manager

[Sepulveda Sanchez Accident Lawyers]<https://sepulvedalawgroup.com/>
Los Angeles  |  Stockton  |  New York

W: sepulvedalawgroup.com<http://sepulvedalawgroup.com/>
P: (213) 426-1051
F: (213) 426-1052
A: 3530 Wilshire Blvd, Suite 1515, Los Angeles, CA 90010
_________________________________________

[image.png]

Precise Imaging Scheduling & Orders
Scheduling Department
[https://precisemri.com/emailsig/precise-logo.png]<https://www.precisemri.com/>
Quick Access
📋 Upload RX<https://precisemri.com/rx>🏥 Provider Portal<https://app.radflow360.com/>⚖️ Attorney Portal<https://app.radflow360.com/>👤 Patient Portal<https://app.radflow360.com/patient-portal>📍 View Locations<https://precisemri.com/locations>
Contact
📞 800-558-2223<tel:800-558-2223>
✉️ scheduling@precisemri.com<mailto:scheduling@precisemri.com>
🌐 www.PreciseMRI.com<https://www.precisemri.com/>
[https://precisemri.com/emailsig/fb.png]<https://www.facebook.com/preciseimaging/> [https://precisemri.com/emailsig/tt.png] <https://twitter.com/preciseimaging>  [https://precisemri.com/emailsig/yt.png] <https://youtube.com/@preciseimagingmri3857?si=H9HGQ21f-htuWDUV>  [https://precisemri.com/emailsig/ln.png] <https://www.linkedin.com/company/precise-imaging/>  [https://precisemri.com/emailsig/it.png] <https://www.instagram.com/preciseimaging/>
📍 Find Your Nearest Location
Multiple convenient locations near you<https://www.precisemri.com/facility-locations/>
Precise Imaging Disclaimer: This email message, its contents and any attachments hereto, are for the sole use of the intended recipient(s) and may contain confidential and privileged information. Any unauthorized review, use, disclosure or distribution is prohibited. Notwithstanding the Uniform Electronic Transactions Act or the applicability of any other law of similar substance or effect, absent an express statement to the contrary hereinabove, this e-mail communication, its contents and any attachments hereto, are not intended to represent an offer or acceptance to enter into a contract and are not otherwise intended to bind the sender, any of its clients, or any other person or entity.


<p>Test ID: {UNIQUE_TEST_ID}</p>"""
        ),
        "expected_tags": [],
        "attachments": [
            {
                "filename": "Order_Plain_X-ray__Outside_Imaging__45149.pdf",
                "filepath": "data/documents/Order_Plain_X-ray__Outside_Imaging__45149.pdf",
                "content_type": "application/pdf"
            }
        ]
    }
,
    "23": {
        "description": "Fw: EXTERNAL: Bertha Delgado DOL 01/21/2024",
        "subject": "Fw: EXTERNAL: Bertha Delgado DOL 01/21/2024",
        "body_html": (
            """


----------- Forwarded message -----------
From: 
scheduling@precisemri.com
Date: August 17, 2025 at 1:47 AM GMT+5:30
Subject: EXTERNAL: Bertha Delgado DOL 01/21/2024
To: 
test123abc@mediflow360.com







----------- Forwarded message -----------
From: 
pischeduling.mmc@gmail.com
Date: August 16, 2025 at 9:21 AM PDT
Subject: EXTERNAL: Bertha Delgado DOL 01/21/2024
To: 
scheduling@precisemri.com


Good morning


Please schedule a client for MRI's near her home.


Bertha Delgado
DOL: 01/21/2024
DOB: 11/20/1967


Address: 19257 Farallon Rd , Madera CA 93638


Phone: 559-871-2370




Let me know the date, time and location.


Once completed please refer to me.


Attorney info:
Shelby Ganuza-case manager
866-4my-ally
shelby@saidianlaw.com
5990 Sepulveda Blvd Ste 250 Van Nuys, Ca 91411


Thank you


Jesse Rodriguez 






Precise Imaging Scheduling & Orders

Scheduling Department




Quick Access
📋 Upload RX

🏥 Provider Portal 
⚖️ Attorney Portal 
👤 Patient Portal 
📍 View Locations 
Contact

📞 
800-558-2223

✉️ 
scheduling@precisemri.com

🌐 
www.PreciseMRI.com




📍
Find Your Nearest Location
Multiple convenient locations near you 

Precise Imaging Disclaimer: This email message, its contents and any attachments hereto, are for the sole use of the intended recipient(s) and may contain confidential and privileged information.
Any unauthorized review, use, disclosure or distribution is prohibited. Notwithstanding the Uniform Electronic Transactions Act or the applicability of any other law of similar substance or effect, absent an express statement to the contrary hereinabove, this
e-mail communication, its contents and any attachments hereto, are not intended to represent an offer or acceptance to enter into a contract and are not otherwise intended to bind the sender, any of its clients, or any other person or entity.

Test ID: {UNIQUE_TEST_ID}"""
        ),
        "expected_tags": [],
        "attachments": [
            {
                "filename": "Delgado, Bertha_Dr. Abeles_Order_MRI Shoulder_05-22-2025.pdf",
                "filepath": "data/documents/Delgado, Bertha_Dr. Abeles_Order_MRI Shoulder_05-22-2025.pdf",
                "content_type": "application/pdf"
            },
            {
                "filename": "Delgado, Bertha_Dr. Abeles_Order_MRI Wrist_05-22-2025.pdf",
                "filepath": "data/documents/Delgado, Bertha_Dr. Abeles_Order_MRI Wrist_05-22-2025.pdf",
                "content_type": "application/pdf"
            }
        ]
    },
    "23": {
        "description": "Genesis Puche - Signed Liens V&A LAW FIRM - Forwarded email with signed lien attachments for multiple clients",
        "subject": "EXTERNAL: Signed Liens V&A LAW FIRM - Case Manager Genesis Puche",
        "body_html": (
            "<p>----------- Forwarded message -----------<br>"
            "From: genesis@valawfirm.com<br>"
            "Date: July 7, 2025 at 11:51 AM PDT<br>"
            "Subject: EXTERNAL: Signed Liens V&A LAW FIRM - Case Manager Genesis Puche<br>"
            "To: billing@precisemri.com</p>"
            "<p>Good afternoon, these are the signed lien for my clients. Please update the portal accordingly. Thanks!</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["ASL", "Rad Lien"],
        "attachments": [
            {
                "filename": "20250703 - RAD signed Lien - Precise Imaging - Kathleen Neeck.pdf",
                "filepath": "data/documents/20250703 - RAD signed Lien - Precise Imaging - Kathleen Neeck.pdf",
                "content_type": "application/pdf"
            }
        ]
    },
    "24": {
        "description": "Genesis Puche - Tech Lien Submission V&A LAW FIRM - Forwarded email with tech lien attachment for client processing",
        "subject": "EXTERNAL: Tech Lien Documentation V&A LAW FIRM - Case Manager Genesis Puche",
        "body_html": (
            "<p>----------- Forwarded message -----------<br>"
            "From: genesis@valawfirm.com<br>"
            "Date: July 7, 2025 at 2:15 PM PDT<br>"
            "Subject: EXTERNAL: Tech Lien Documentation V&A LAW FIRM - Case Manager Genesis Puche<br>"
            "To: billing@precisemri.com</p>"
            "<p>Good afternoon, attached is the completed tech lien documentation for our client. Please process accordingly and update your records. Thanks!</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["ASL", "Tech Lien"],
        "attachments": [
            {
                "filename": "20250703 - TECH  signed Lien - Precise Imaging - Kathleen Neeck.pdf",
                "filepath": "data/documents/20250703 - TECH  signed Lien - Precise Imaging - Kathleen Neeck.pdf",
                "content_type": "application/pdf"
            }
        ]
    },
    "25": {
        "description": "Dillon Sedaghat - Bill or balance Request - Simple bill request for client with DOL 07/04/2025 and DOS 09/19/2025",
        "subject": "Bill Request - Dillon Sedaghat DOL 07/04/2025",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I am requesting bills for my client Dillon Sedaghat DOL 07/04/2025.</p>"
            "<p>DOS 09/19/2025</p>"
            "<p>Thank you,</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Bill or balance Request"]
    },
    "26": {
        "description": "Williams, Sharon - Bill or balance Request - Legal firm requesting bills for settlement with detailed client info and contact details",
        "subject": "Bill Request - Williams, Sharon DOB 10/08/1951 DOL 04/08/2020",
        "body_html": (
            "<p>Hi Precise Imaging- Oakland,</p>"
            "<p>Our client has received treatment from your facility for injuries caused by the above-referenced accident.</p>"
            "<p>In order to affect a settlement of claims, please forward any bills pertaining to the below.</p>"
            "<p>Our Client/Your Patient: Williams, Sharon<br>"
            "Date of Birth: 10/08/1951<br>"
            "Date of Loss: 04/08/2020</p>"
            "<p>Beejay Woo<br>"
            "Medical Records Clerk</p>"
            "<p>612 S Broadway,<br>"
            "Los Angeles, CA 90014<br>"
            "Tel.: (213) 291-7905 Extension 1496<br>"
            "Fax: (877)389-2775<br>"
            "Email: Beejay.Woo@Downtownlalaw.com<br>"
            "Website: www.DowntownLALaw.com</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Bill or balance Request"]
    },
    "27": {
        "description": "Williams, Sharon - Release of Records - Legal firm requesting medical records for settlement with detailed client info and contact details",
        "subject": "Medical Records Request - Williams, Sharon DOB 10/08/1951 DOL 04/08/2020",
        "body_html": (
            "<p>Hi Precise Imaging- Oakland,</p>"
            "<p>Our client has received treatment from your facility for injuries caused by the above-referenced accident.</p>"
            "<p>In order to affect a settlement of claims, please forward any Medical Records report pertaining to the below.</p>"
            "<p>Our Client/Your Patient: Williams, Sharon<br>"
            "Date of Birth: 10/08/1951<br>"
            "Date of Loss: 04/08/2020</p>"
            "<p>Beejay Woo<br>"
            "Medical Records Clerk</p>"
            "<p>612 S Broadway,<br>"
            "Los Angeles, CA 90014<br>"
            "Tel.: (213) 291-7905 Extension 1496<br>"
            "Fax: (877)389-2775<br>"
            "Email: Beejay.Woo@Downtownlalaw.com<br>"
            "Website: www.DowntownLALaw.com</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Release of Records"]
    },
    "28": {
        "description": "Edy Posas-Valdes - Release of Records - Mixed request for bills and MRI records (should prioritize Medical Records over billing)",
        "subject": "Records and Bills Request - Edy Posas-Valdes DOL 04/07/2025",
        "body_html": (
            "<p>Hello,</p>"
            "<p>I am requesting bills & MRI Lumbar + Left Shoulder records for my client Edy Posas-Valdes DOL 04/07/2025.</p>"
            "<p>DOS 09/19/2025</p>"
            "<p>Thank you,</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "expected_tags": ["Release of Records"]
    },
    "29": {
        "description": "Reports Request - Simple MRI report request with patient ID attachment for medical records retrieval",
        "subject": "MRI Report Request",
        "body_html": (
            "<p>Hi team</p>"
            "<p>Can we please have the MRI report for this client?</p>"
            "<p>Thanks</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "Precise Imaging_patientid.pdf",
                "filepath": "data/documents/Precise Imaging_patientid.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Reports Request"]
    },
    "30": {
        "description": "Cherie Roedel - ASL Lien - Attorney signed RAD lien document for processing",
        "subject": "Cherie Roedel - Signed Document",
        "body_html": (
            "<p>Hello Precise Imaging,</p>"
            "<p>Please find attached the signed document for our client Cherie Roedel.</p>"
            "<p>This has been signed and is ready for processing.</p>"
            "<p>Please confirm receipt and let us know once this has been uploaded to the patient file.</p>"
            "<p>Thank you,</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "20250703 - RAD Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "filepath": "data/documents/20250703 - RAD Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL > Rad Lien"]
    },
    "31": {
        "description": "Cherie Roedel - ASL Lien - Attorney signed TECH lien document for processing",
        "subject": "Cherie Roedel - Signed Document",
        "body_html": (
            "<p>Hello Precise Imaging,</p>"
            "<p>Please find attached the signed document for our client Cherie Roedel.</p>"
            "<p>This has been signed and is ready for processing.</p>"
            "<p>Please confirm receipt and let us know once this has been uploaded to the patient file.</p>"
            "<p>Thank you,</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "20250703 - TECH Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "filepath": "data/documents/20250703 - TECH Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL > Tech Lien"]
    },
    "32": {
        "description": "Cherie Roedel - ASL Lien - Both RAD and TECH liens attached in same email for processing",
        "subject": "Cherie Roedel - Signed Lien Documents",
        "body_html": (
            "<p>Hello Precise Imaging,</p>"
            "<p>Please find attached the signed lien documents for our client Cherie Roedel.</p>"
            "<p>Both the Radiology and Technologist liens have been signed and are ready for processing.</p>"
            "<p>Please confirm receipt and let us know once these have been uploaded to the patient file.</p>"
            "<p>Thank you,</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "20250703 - RAD Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "filepath": "data/documents/20250703 - RAD Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "content_type": "application/pdf"
            },
            {
                "filename": "20250703 - TECH Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "filepath": "data/documents/20250703 - TECH Signed Lien - Precise Imaging - Cherie Roedel.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Rad Lien", "Tech Lien"]
    },
    "33": {
        "description": "Kathleen Neeck - RAD Signed Lien - Single RAD lien attachment for processing",
        "subject": "Kathleen Neeck - Signed RAD Lien Document",
        "body_html": "<p>Please find attached the signed RAD lien for Kathleen Neeck.</p>",
        "attachments": [
            {
                "filename": "20250703 - RAD signed Lien - Precise Imaging - Kathleen Neeck.pdf",
                "filepath": "data/documents/20250703 - RAD signed Lien - Precise Imaging - Kathleen Neeck.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Rad Lien"]
    },
    "34": {
        "description": "Inder Singh - ASL Combined Lien - Both TECH and RAD liens in single 2-page document (should be split)",
        "subject": "Inder Singh - Signed Lien Documents",
        "body_html": "<p>Please find attached the signed lien documents for Inder Singh.</p>",
        "attachments": [
            {
                "filename": "ESIGN_PRE1089351_ASL.pdf",
                "filepath": "data/documents/ESIGN_PRE1089351_ASL.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Rad Lien", "Tech Lien"]
    },
    "35": {
        "description": "December 9 PI Client - Dual lien packet with separate radiologist and technologist files for processing",
        "subject": "Signed PI Lien Packet - Radiologist & Tech (Dec 9)",
        "body_html": (
            "<p>Hello Precise Imaging Team,</p>"
            "<p>Attached are the finalized Precise Imaging lien packets for our PI client that were executed on December 9.</p>"
            "<p>Both the Radiologist and Technologist lien forms are included so your team can upload them to the patient account and confirm receipt.</p>"
            "<p>Please let us know once everything is filed with the chart.</p>"
            "<p>Thank you,<br>"
            "Lien Processing Desk</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "2025-12-09-Lien-PI Radiologist-Precise Imaging.pdf",
                "filepath": "data/documents/2025-12-09-Lien-PI Radiologist-Precise Imaging.pdf",
                "content_type": "application/pdf"
            },
            {
                "filename": "2025-12-09-Lien-PI Tech-Precise Imaging.pdf",
                "filepath": "data/documents/2025-12-09-Lien-PI Tech-Precise Imaging.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Rad Lien", "Tech Lien"]
    },
    "36": {
        "description": "Case 258521 - Attorney signed lien packet with single consolidated PDF attachment",
        "subject": "Signed Lien Packet - Case 258521",
        "body_html": (
            "<p>Hi Precise Imaging Billing,</p>"
            "<p>Please see the attached signed lien packet for case 258521.</p>"
            "<p>Kindly confirm receipt and update the patient account accordingly.</p>"
            "<p>Thank you for your help!</p>"
            "<p>Best regards,<br>"
            "Accounting Support</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "AR-Precise Imaging-258521-Signed.pdf",
                "filepath": "data/documents/AR-Precise Imaging-258521-Signed.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Rad Lien"]
    },
    "37": {
        "description": "PRE1092256 - ASL Radiology lien test from lientest folder",
        "subject": "Signed Radiology Lien - PRE1092256",
        "body_html": (
            "<p>Hello,</p>"
            "<p>Please find the attorney signed radiology lien for patient PRE1092256 attached.</p>"
            "<p>Kindly upload and confirm receipt.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "PRE1092256_RAD_ASL.pdf",
                "filepath": "data/documents/lientest/PRE1092256_RAD_ASL.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Rad Lien"]
    },
    "38": {
        "description": "PRE1092256 - ASL Technologist lien test from lientest folder",
        "subject": "Signed Tech Lien - PRE1092256",
        "body_html": (
            "<p>Hello,</p>"
            "<p>Attached is the attorney signed technologist lien for patient PRE1092256.</p>"
            "<p>Please upload to the patient file and confirm.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "PRE1092256_TC_ASL.pdf",
                "filepath": "data/documents/lientest/PRE1092256_TC_ASL.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["ASL", "Tech Lien"]
    },
    "39": {
        "description": "PRE1159780 - PSL Radiology lien test from lientest folder",
        "subject": "Patient Signed Radiology Lien - PRE1159780",
        "body_html": (
            "<p>Hi team,</p>"
            "<p>Patient PRE1159780 has signed the radiology lien attached.</p>"
            "<p>Kindly process and confirm upload.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "PRE1159780_RAD_PSL.pdf",
                "filepath": "data/documents/lientest/PRE1159780_RAD_PSL.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["PSL", "Rad Lien"]
    },
    "40": {
        "description": "PRE1159780 - PSL Technologist lien test from lientest folder",
        "subject": "Patient Signed Tech Lien - PRE1159780",
        "body_html": (
            "<p>Hi team,</p>"
            "<p>Attached is the patient signed technologist lien for PRE1159780.</p>"
            "<p>Please upload and confirm receipt.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "PRE1159780_TC_PSL.pdf",
                "filepath": "data/documents/lientest/PRE1159780_TC_PSL.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["PSL", "Tech Lien"]
    },
    "41": {
        "description": "Strikethrough lien document - should flag lien modifications",
        "subject": "Lien Submission with Edits",
        "body_html": (
            "<p>Hello,</p>"
            "<p>Please find the attached lien document for processing.</p>"
            "<p>Thank you.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "1d6e60248fa5a9eeeb2aa2e438738dbd2a7ea84e.pdf",
                "filepath": "data/documents/strikethrough/1d6e60248fa5a9eeeb2aa2e438738dbd2a7ea84e.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified"]
    },
    "42": {
        "description": "Victoria Concepcion Orozco - Fraudulent Lien (LB 254676) - Should detect conditional language and modifications",
        "subject": "Signed Lien - Victoria Concepcion Orozco Case 254676",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached the signed lien for our client Victoria Concepcion Orozco.</p>"
            "<p>Case Number: 254676 (LB)</p>"
            "<p>Please process and upload to the patient file.</p>"
            "<p>Thank you,</p>"
            "<p>Law Office</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "(LB) 254676 - Victoria Concepcion Orozco -SIGNED LIEN.pdf",
                "filepath": "data/documents/fraudulentliens/(LB) 254676 - Victoria Concepcion Orozco -SIGNED LIEN.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "43": {
        "description": "Dhunna - Fraudulent Notice of Lien - Should detect non-standard lien format with cover letter conditions",
        "subject": "Notice of Lien - Dhunna from Precise Imaging",
        "body_html": (
            "<p>Hello Billing Team,</p>"
            "<p>Attached is the Notice of Lien document for our client.</p>"
            "<p>Please review and process accordingly.</p>"
            "<p>Best regards,</p>"
            "<p>Legal Department</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "10.01.25 Dhunna fr Precise Imaging re Notice of Lien.pdf",
                "filepath": "data/documents/fraudulentliens/10.01.25 Dhunna fr Precise Imaging re Notice of Lien.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "44": {
        "description": "Fraudulent Lien Document (2d5f56bb) - Should detect modifications and conditional language",
        "subject": "Lien Document Submission",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Attached is the completed lien documentation for our client.</p>"
            "<p>Please upload to patient records.</p>"
            "<p>Thank you,</p>"
            "<p>Attorney Services</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "2d5f56bbbb6051603dc2133c3d0769eb99f40d99.pdf",
                "filepath": "data/documents/fraudulentliens/2d5f56bbbb6051603dc2133c3d0769eb99f40d99.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "45": {
        "description": "LT Atkinson - Fraudulent Lien (6.9.2008) - Old fraudulent lien document should be flagged",
        "subject": "LT Atkinson Lien Documentation",
        "body_html": (
            "<p>Please find the attached lien document for LT Atkinson.</p>"
            "<p>This document has been signed and is ready for processing.</p>"
            "<p>Best regards,</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "6.9.2008 LT Atkinson.pdf",
                "filepath": "data/documents/fraudulentliens/6.9.2008 LT Atkinson.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "46": {
        "description": "Fraudulent Lien Document (6622f1e6) - Should detect non-standard lien format",
        "subject": "Lien Agreement Submission",
        "body_html": (
            "<p>Dear Billing Department,</p>"
            "<p>Please process the attached lien agreement.</p>"
            "<p>Thank you for your assistance.</p>"
            "<p>Legal Processing Team</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "6622f1e6eae239d18d64afb8941b19bae6d7242e.pdf",
                "filepath": "data/documents/fraudulentliens/6622f1e6eae239d18d64afb8941b19bae6d7242e.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "47": {
        "description": "Case 253099 - Fraudulent Tech Lien - Should detect modifications in tech lien document",
        "subject": "Signed Tech Lien - Case 253099",
        "body_html": (
            "<p>Hello Precise Imaging,</p>"
            "<p>Attached is the signed technologist lien for case 253099.</p>"
            "<p>Please upload to the patient account and confirm receipt.</p>"
            "<p>Thank you,</p>"
            "<p>Accounts Receivable</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "AR-Precise Imaging- Tech Lien-253099-SIGNED.pdf",
                "filepath": "data/documents/fraudulentliens/AR-Precise Imaging- Tech Lien-253099-SIGNED.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "48": {
        "description": "Palomo - Fraudulent Lien Document - Should detect modifications and flag for review",
        "subject": "Palomo Lien Submission",
        "body_html": (
            "<p>Dear Precise Imaging Team,</p>"
            "<p>Please find attached the lien document for our client Palomo.</p>"
            "<p>Kindly process and confirm upload.</p>"
            "<p>Regards,</p>"
            "<p>Legal Services</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "palomo.pdf",
                "filepath": "data/documents/fraudulentliens/palomo.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "49": {
        "description": "Email with conditional language - Should be rejected before document analysis",
        "subject": "Lien Submission with Special Terms",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>We are submitting the attached lien for our client. However, please note that this lien is subject to final approval by our managing attorney and we will only proceed if you agree to modify the payment terms to net 60 days instead of the standard terms.</p>"
            "<p>We also require that you provide weekly status updates on the settlement process.</p>"
            "<p>Thank you for your cooperation.</p>"
            "<p>Best regards,<br>"
            "<p>Law Firm XYZ</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "standard_lien.pdf",
                "filepath": "data/documents/lientest/PRE1092256_RAD_ASL.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    },
    "50": {
        "description": "Cover letter with conditional terms - Should detect cover letter with modification language",
        "subject": "Lien Documents with Cover Letter",
        "body_html": (
            "<p>Dear Precise Imaging,</p>"
            "<p>Please find attached our client's lien documentation with cover letter.</p>"
            "<p>Thank you.</p>"
            "<p>Test ID: {UNIQUE_TEST_ID}</p>"
        ),
        "attachments": [
            {
                "filename": "lien_with_cover.pdf",
                "filepath": "data/documents/fraudulentliens/10.01.25 Dhunna fr Precise Imaging re Notice of Lien.pdf",
                "content_type": "application/pdf"
            }
        ],
        "expected_tags": ["Lien Modified", "AI: Human review required"]
    }
}
