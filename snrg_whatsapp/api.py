import io
import re

import frappe
import requests
from frappe.utils import formatdate
from frappe.utils.pdf import get_pdf


DEFAULT_TEMPLATE_LANGUAGE = "en_US"
DEFAULT_TEMPLATE_NAME = "sales_quotation_confirmation"
REQUEST_TIMEOUT = 30
SEND_MARKER = "SNRG WhatsApp quotation sent"
FAILURE_MARKER = "SNRG WhatsApp quotation failed"


def enqueue_sales_quotation_whatsapp(doc, method=None):
    if not _is_quotation_send_enabled():
        return

    frappe.enqueue(
        "snrg_whatsapp.api.send_sales_quotation_whatsapp",
        queue="short",
        timeout=300,
        quotation_name=doc.name,
    )


def send_sales_quotation_whatsapp(quotation_name, raise_on_error=False, force=False):
    try:
        _send_sales_quotation_whatsapp(quotation_name, force=force)
    except Exception:
        frappe.db.rollback()
        docname = quotation_name or "Unknown"
        message = frappe.get_traceback()
        frappe.log_error(message=message, title=f"{FAILURE_MARKER}: {docname}")

        if frappe.db.exists("Quotation", docname):
            doc = frappe.get_doc("Quotation", docname)
            _add_timeline_note(doc, FAILURE_MARKER, "See Error Log for traceback.")

        if raise_on_error:
            raise


def _send_sales_quotation_whatsapp(quotation_name, force=False):
    doc = frappe.get_doc("Quotation", quotation_name)

    if doc.docstatus != 1:
        return

    if not force and _already_sent(doc):
        return

    config = _get_config()
    recipient = _get_recipient_number(doc)
    if not recipient:
        _add_timeline_note(doc, FAILURE_MARKER, "No mobile number found.")
        return

    filename = f"{doc.name}.pdf"
    response = _send_template_message(config, doc, recipient, filename)

    message_id = (
        response.get("messages", [{}])[0].get("id")
        if isinstance(response, dict)
        else None
    )
    _add_timeline_note(doc, SEND_MARKER, f"Recipient: {recipient} | Message ID: {message_id or 'n/a'}")

    frappe.logger().info(
        {
            "event": "quotation_whatsapp_sent",
            "quotation": doc.name,
            "recipient": recipient,
            "meta_response": response,
        }
    )
    frappe.db.commit()


def _get_config():
    config = {
        "chatwoot_base_url": (frappe.conf.get("chatwoot_base_url") or "").rstrip("/"),
        "chatwoot_account_id": frappe.conf.get("chatwoot_account_id"),
        "chatwoot_api_access_token": frappe.conf.get("chatwoot_api_access_token"),
        "chatwoot_inbox_id": frappe.conf.get("chatwoot_inbox_id"),
        "template_name": frappe.conf.get("whatsapp_quotation_template_name")
        or DEFAULT_TEMPLATE_NAME,
        "template_language": frappe.conf.get("whatsapp_quotation_template_language")
        or DEFAULT_TEMPLATE_LANGUAGE,
        "print_format": frappe.conf.get("whatsapp_quotation_print_format"),
    }

    missing = []
    for key in (
        "chatwoot_base_url",
        "chatwoot_account_id",
        "chatwoot_api_access_token",
        "chatwoot_inbox_id",
    ):
        if not config[key]:
            missing.append(key)

    if missing:
        frappe.throw("Missing WhatsApp config in site_config.json: " + ", ".join(missing))

    return config


def _is_quotation_send_enabled():
    return cint_or_none(frappe.conf.get("enable_quotation_whatsapp_on_submit"), default=1) == 1


def _get_recipient_number(doc):
    candidates = [doc.get("contact_mobile")]

    if doc.get("party_name"):
        party_type = doc.get("quotation_to")
        if party_type == "Customer":
            candidates.append(frappe.db.get_value("Customer", doc.party_name, "mobile_no"))
        elif party_type == "Lead":
            candidates.append(frappe.db.get_value("Lead", doc.party_name, "mobile_no"))

    if doc.get("contact_person"):
        contact = frappe.db.get_value(
            "Contact",
            doc.contact_person,
            ["mobile_no", "phone"],
            as_dict=True,
        )
        if contact:
            candidates.extend([contact.mobile_no, contact.phone])

    for candidate in candidates:
        normalized = _normalize_phone(candidate)
        if normalized:
            return normalized

    return None


def _normalize_phone(value):
    if not value:
        return None

    digits = re.sub(r"\D", "", str(value))
    if not digits:
        return None

    if len(digits) == 10:
        return "91" + digits

    if len(digits) == 11 and digits.startswith("0"):
        return "91" + digits[1:]

    return digits


def _chatwoot_phone_number(value):
    normalized = _normalize_phone(value)
    return f"+{normalized}" if normalized else None


def _already_sent(doc):
    return bool(
        frappe.db.exists(
            "Comment",
            {
                "reference_doctype": doc.doctype,
                "reference_name": doc.name,
                "comment_type": "Comment",
                "content": ["like", f"%{SEND_MARKER}%"],
            },
        )
    )


def _add_timeline_note(doc, marker, detail):
    content = f"{marker}. {detail}"
    doc.add_comment("Comment", content)


def _build_quotation_pdf(doc, print_format=None):
    chosen_print_format = print_format or doc.get("select_print_heading") or None
    html = frappe.get_print(
        doc.doctype,
        doc.name,
        print_format=chosen_print_format,
        doc=doc,
    )
    pdf_bytes = get_pdf(html)
    filename = f"{doc.name}.pdf"
    return pdf_bytes, filename


def _send_template_message(config, doc, recipient, filename):
    chatwoot_file = _upload_to_chatwoot(config, doc, filename)
    contact = _find_or_create_chatwoot_contact(config, doc, recipient)
    conversation = _find_or_create_chatwoot_conversation(config, contact, recipient)
    conversation_id = conversation.get("id") or conversation.get("display_id")

    if not conversation_id:
        frappe.throw(f"Chatwoot conversation ID missing in response: {conversation}")

    payload = {
        "content": _render_template_preview(doc),
        "message_type": "outgoing",
        "content_type": "text",
        "private": False,
        "attachments": [chatwoot_file["blob_id"]],
        "template_params": {
            "name": config["template_name"],
            "language": config["template_language"],
            "category": "UTILITY",
            "processed_params": {
                "header": {
                    "media_url": chatwoot_file["file_url"],
                    "media_type": "document",
                    "media_name": filename,
                },
                "body": {
                    "1": doc.customer_name or doc.party_name,
                    "2": doc.name,
                    "3": formatdate(doc.transaction_date),
                },
            },
        },
    }

    response = requests.post(
        _chatwoot_url(config, f"conversations/{conversation_id}/messages"),
        headers=_chatwoot_headers(config),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, "send quotation template via Chatwoot")


def _upload_to_chatwoot(config, doc, filename):
    pdf_bytes, _ = _build_quotation_pdf(doc, config["print_format"])
    response = requests.post(
        _chatwoot_url(config, "upload"),
        headers={"api_access_token": config["chatwoot_api_access_token"]},
        files={"attachment": (filename, io.BytesIO(pdf_bytes), "application/pdf")},
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, "upload quotation PDF to Chatwoot")


def _find_or_create_chatwoot_contact(config, doc, recipient):
    phone_number = _chatwoot_phone_number(recipient)
    contact = _find_chatwoot_contact(config, phone_number, recipient)
    if contact:
        return contact

    payload = {
        "name": doc.customer_name or doc.party_name,
        "phone_number": phone_number,
        "inbox_id": int(config["chatwoot_inbox_id"]),
    }
    response = requests.post(
        _chatwoot_url(config, "contacts"),
        headers=_chatwoot_headers(config),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, "create Chatwoot contact")["payload"]["contact"]


def _find_chatwoot_contact(config, phone_number, recipient):
    candidates = []
    for query in filter(None, [phone_number, recipient, recipient[-10:]]):
        response = requests.get(
            _chatwoot_url(config, "contacts/search"),
            headers=_chatwoot_headers(config),
            params={"q": query},
            timeout=REQUEST_TIMEOUT,
        )
        payload = _parse_chatwoot_response(response, f"search Chatwoot contacts for {query}")
        candidates.extend(payload.get("payload", []))

    normalized_target = _normalize_phone(recipient)
    for contact in candidates:
        candidate_phone = _normalize_phone(contact.get("phone_number"))
        if candidate_phone == normalized_target:
            return contact

    return None


def _find_or_create_chatwoot_conversation(config, contact, recipient):
    response = requests.get(
        _chatwoot_url(config, f"contacts/{contact['id']}/conversations"),
        headers=_chatwoot_headers(config),
        timeout=REQUEST_TIMEOUT,
    )
    payload = _parse_chatwoot_response(response, "fetch Chatwoot conversations")
    inbox_id = int(config["chatwoot_inbox_id"])
    conversations = payload.get("payload", [])
    for conversation in conversations:
        if conversation.get("inbox_id") == inbox_id:
            return conversation

    create_payload = {
        "inbox_id": inbox_id,
        "contact_id": contact["id"],
        "status": "open",
    }
    response = requests.post(
        _chatwoot_url(config, "conversations"),
        headers=_chatwoot_headers(config),
        json=create_payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, "create Chatwoot conversation")


def _render_template_preview(doc):
    customer_name = doc.customer_name or doc.party_name
    quotation_date = formatdate(doc.transaction_date)
    return (
        f"Dear {customer_name},\n\n"
        f"Your quotation {doc.name} dated {quotation_date} is generated.\n\n"
        "Please acknowledge receipt of this quotation. In case of any clarification or "
        "modification required, you may respond to this message.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )


def _chatwoot_headers(config):
    return {
        "api_access_token": config["chatwoot_api_access_token"],
        "Content-Type": "application/json",
    }


def _chatwoot_url(config, endpoint):
    return f"{config['chatwoot_base_url']}/api/v1/accounts/{config['chatwoot_account_id']}/{endpoint}"


def _parse_chatwoot_response(response, action):
    try:
        payload = response.json()
    except Exception:
        payload = response.text

    if not response.ok:
        frappe.throw(f"Failed to {action}: {payload}")

    return payload


def cint_or_none(value, default=0):
    if value is None:
        return default

    if isinstance(value, bool):
        return int(value)

    return 1 if str(value).strip().lower() in {"1", "true", "yes", "on"} else 0
