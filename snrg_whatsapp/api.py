import io
import re

import frappe
import requests
from frappe.utils import formatdate
from frappe.utils.pdf import get_pdf


DEFAULT_API_VERSION = "v25.0"
DEFAULT_TEMPLATE_LANGUAGE = "en_US"
DEFAULT_TEMPLATE_NAME = "sales_quotation_confirmation"
REQUEST_TIMEOUT = 30


def enqueue_sales_quotation_whatsapp(doc, method=None):
    frappe.enqueue(
        "snrg_whatsapp.api.send_sales_quotation_whatsapp",
        queue="short",
        timeout=300,
        quotation_name=doc.name,
    )


def send_sales_quotation_whatsapp(quotation_name):
    doc = frappe.get_doc("Quotation", quotation_name)

    if doc.docstatus != 1:
        return

    config = _get_config()
    recipient = _get_recipient_number(doc)
    if not recipient:
        frappe.log_error(
            title="Quotation WhatsApp skipped",
            message=f"No mobile number found for Quotation {doc.name}.",
        )
        return

    pdf_bytes, filename = _build_quotation_pdf(doc, config["print_format"])
    media_id = _upload_media(config, pdf_bytes, filename)
    response = _send_template_message(config, doc, recipient, media_id, filename)

    frappe.logger().info(
        {
            "event": "quotation_whatsapp_sent",
            "quotation": doc.name,
            "recipient": recipient,
            "meta_response": response,
        }
    )


def _get_config():
    config = {
        "access_token": frappe.conf.get("whatsapp_cloud_access_token"),
        "phone_number_id": frappe.conf.get("whatsapp_cloud_phone_number_id"),
        "api_version": frappe.conf.get("whatsapp_cloud_api_version") or DEFAULT_API_VERSION,
        "template_name": frappe.conf.get("whatsapp_quotation_template_name")
        or DEFAULT_TEMPLATE_NAME,
        "template_language": frappe.conf.get("whatsapp_quotation_template_language")
        or DEFAULT_TEMPLATE_LANGUAGE,
        "print_format": frappe.conf.get("whatsapp_quotation_print_format"),
    }

    missing = []
    if not config["access_token"]:
        missing.append("whatsapp_cloud_access_token")
    if not config["phone_number_id"]:
        missing.append("whatsapp_cloud_phone_number_id")

    if missing:
        frappe.throw("Missing WhatsApp config in site_config.json: " + ", ".join(missing))

    return config


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


def _upload_media(config, pdf_bytes, filename):
    response = requests.post(
        _graph_url(config, "media"),
        headers={"Authorization": f"Bearer {config['access_token']}"},
        data={"messaging_product": "whatsapp"},
        files={"file": (filename, io.BytesIO(pdf_bytes), "application/pdf")},
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_meta_response(response, "upload quotation PDF")["id"]


def _send_template_message(config, doc, recipient, media_id, filename):
    payload = {
        "messaging_product": "whatsapp",
        "to": recipient,
        "type": "template",
        "template": {
            "name": config["template_name"],
            "language": {"code": config["template_language"]},
            "components": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {"id": media_id, "filename": filename},
                        }
                    ],
                },
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": doc.customer_name or doc.party_name},
                        {"type": "text", "text": doc.name},
                        {"type": "text", "text": formatdate(doc.transaction_date)},
                    ],
                },
            ],
        },
    }

    response = requests.post(
        _graph_url(config, "messages"),
        headers={
            "Authorization": f"Bearer {config['access_token']}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_meta_response(response, "send quotation WhatsApp template")


def _graph_url(config, endpoint):
    return (
        f"https://graph.facebook.com/{config['api_version']}/"
        f"{config['phone_number_id']}/{endpoint}"
    )


def _parse_meta_response(response, action):
    try:
        payload = response.json()
    except Exception:
        payload = response.text

    if not response.ok:
        frappe.throw(f"Failed to {action}: {payload}")

    return payload
