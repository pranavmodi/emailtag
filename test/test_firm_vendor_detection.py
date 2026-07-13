from pifstats.src.firm_researcher import detect_vendor_stack_from_email_messages


def test_detects_vendor_from_message_sender_and_recipient_domains():
    vendors = detect_vendor_stack_from_email_messages(
        [
            {
                "sender": "assistant@omega.filevineapp.com",
                "recipients": ["scheduling@precisemri.com", {"handle": "bcc@bcc.casepeer.com"}],
                "subject": "Referral",
                "content_text": "Please schedule the patient.",
            }
        ]
    )

    by_vendor = {item["vendor"]: item for item in vendors}
    assert by_vendor["filevine"]["source"] == "email_domain"
    assert by_vendor["filevine"]["confidence"] == "high"
    assert by_vendor["casepeer"]["source"] == "email_domain"
    assert by_vendor["casepeer"]["confidence"] == "high"


def test_detects_vendor_from_body_url_and_text_without_generic_domains():
    vendors = detect_vendor_stack_from_email_messages(
        [
            {
                "sender": "paralegal@examplelaw.com",
                "recipients": ["scheduling@precisemri.com"],
                "subject": "Case update",
                "content_text": (
                    "Please use the secure portal at https://matter.casepeer.com/login. "
                    "This message also mentions Dropbox, which should not be a vendor."
                ),
            },
            {
                "sender": "intake@examplelaw.com",
                "recipients": ["scheduling@precisemri.com"],
                "subject": "Lead follow-up",
                "content_text": "Lead Docket has the intake notes.",
            },
        ]
    )

    by_vendor = {item["vendor"]: item for item in vendors}
    assert by_vendor["casepeer"]["source"] == "body_url_domain"
    assert by_vendor["lead-docket"]["source"] == "inbox_text"
    assert "dropbox" not in by_vendor
