import io
import json
import re

import frappe
import requests
from frappe.utils import formatdate
from frappe.utils.pdf import get_pdf


DEFAULT_TEMPLATE_LANGUAGE = "en_US"
REQUEST_TIMEOUT = 30
MANUAL_DOC_SEND_GROUP = "Send WhatsApp"
SUPPORTED_REPORTS = {
    "Customer Ledger Report": {
        "label": "Customer Ledger",
        "include_ar": 0,
        "include_ledger": 1,
    },
    "Customer AR Report": {
        "label": "Customer AR",
        "include_ar": 1,
        "include_ledger": 0,
    },
}

AUTOMATIONS = {
    "Quotation": {
        "send_fn": "send_sales_quotation_whatsapp",
        "queue_fn": "enqueue_sales_quotation_whatsapp",
        "name_key": "quotation_name",
        "enable_key": "enable_quotation_whatsapp_on_submit",
        "template_name_key": "whatsapp_quotation_template_name",
        "template_name_default": "sales_quotation_confirmation",
        "template_language_key": "whatsapp_quotation_template_language",
        "print_format_key": "whatsapp_quotation_print_format",
        "send_marker": "SNRG WhatsApp quotation sent",
        "failure_marker": "SNRG WhatsApp quotation failed",
        "event_name": "quotation_whatsapp_sent",
        "action_label": "quotation",
        "template_action_label": "quotation template",
        "preview_builder": "_render_quotation_preview",
        "doc_date_field": "transaction_date",
        "party_field": "party_name",
        "party_type_field": "quotation_to",
        "customer_name_field": "customer_name",
        "contact_mobile_field": "contact_mobile",
        "contact_person_field": "contact_person",
    },
    "Sales Invoice": {
        "send_fn": "send_sales_invoice_whatsapp",
        "queue_fn": "enqueue_sales_invoice_whatsapp",
        "name_key": "sales_invoice_name",
        "enable_key": "enable_sales_invoice_whatsapp_on_submit",
        "template_name_key": "whatsapp_sales_invoice_template_name",
        "template_name_default": "sales_invoice_confirmation",
        "template_language_key": "whatsapp_sales_invoice_template_language",
        "print_format_key": "whatsapp_sales_invoice_print_format",
        "send_marker": "SNRG WhatsApp sales invoice sent",
        "failure_marker": "SNRG WhatsApp sales invoice failed",
        "event_name": "sales_invoice_whatsapp_sent",
        "action_label": "sales invoice",
        "template_action_label": "sales invoice template",
        "preview_builder": "_render_sales_invoice_preview",
        "doc_date_field": "posting_date",
        "party_field": "customer",
        "party_type": "Customer",
        "customer_name_field": "customer_name",
        "contact_mobile_field": "contact_mobile",
        "contact_person_field": "contact_person",
    },
    "Payment Entry": {
        "send_fn": "send_payment_entry_whatsapp",
        "queue_fn": "enqueue_payment_entry_whatsapp",
        "name_key": "payment_entry_name",
        "enable_key": "enable_payment_entry_whatsapp_on_submit",
        "template_name_key": "whatsapp_payment_entry_template_name",
        "template_name_default": "payment_entry_confirmation",
        "template_language_key": "whatsapp_payment_entry_template_language",
        "print_format_key": "whatsapp_payment_entry_print_format",
        "send_marker": "SNRG WhatsApp payment entry sent",
        "failure_marker": "SNRG WhatsApp payment entry failed",
        "event_name": "payment_entry_whatsapp_sent",
        "action_label": "payment entry",
        "template_action_label": "payment entry template",
        "preview_builder": "_render_payment_entry_preview",
        "doc_date_field": "posting_date",
        "party_field": "party_name",
        "party_type_field": "party_type",
        "party_type": "Customer",
        "customer_name_field": "party_name",
    },
}


def enqueue_sales_quotation_whatsapp(doc, method=None):
    _enqueue_whatsapp_send("Quotation", doc.name)


def send_sales_quotation_whatsapp(quotation_name, raise_on_error=False, force=False):
    _send_document_whatsapp("Quotation", quotation_name, raise_on_error=raise_on_error, force=force)


def enqueue_sales_invoice_whatsapp(doc, method=None):
    _enqueue_whatsapp_send("Sales Invoice", doc.name)


def send_sales_invoice_whatsapp(sales_invoice_name, raise_on_error=False, force=False):
    _send_document_whatsapp(
        "Sales Invoice",
        sales_invoice_name,
        raise_on_error=raise_on_error,
        force=force,
    )


def enqueue_payment_entry_whatsapp(doc, method=None):
    _enqueue_whatsapp_send("Payment Entry", doc.name)


def send_payment_entry_whatsapp(payment_entry_name, raise_on_error=False, force=False):
    _send_document_whatsapp(
        "Payment Entry",
        payment_entry_name,
        raise_on_error=raise_on_error,
        force=force,
    )


@frappe.whitelist()
def get_manual_whatsapp_recipients(doctype=None, docname=None, customer=None):
    customer_name = _resolve_customer_for_manual_send(doctype=doctype, docname=docname, customer=customer)
    if not customer_name:
        return {"customer": None, "recipients": []}

    recipients = _get_customer_recipients(customer_name)
    return {
        "customer": customer_name,
        "recipients": recipients,
    }


@frappe.whitelist()
def send_document_whatsapp_manual(doctype, docname, recipient_mobile, recipient_label=None):
    if doctype not in AUTOMATIONS:
        frappe.throw(f"Unsupported DocType for WhatsApp send: {doctype}")

    automation = AUTOMATIONS[doctype]
    response = _deliver_document_whatsapp(
        doctype,
        docname,
        automation,
        force=True,
        recipient_override=recipient_mobile,
        note_context=recipient_label or recipient_mobile,
    )
    return {
        "message": f"{doctype} sent on WhatsApp to {recipient_label or recipient_mobile}",
        "response": response,
    }


@frappe.whitelist()
def send_customer_report_whatsapp(report_name, recipient_mobile, recipient_label=None, filters=None):
    report_config = SUPPORTED_REPORTS.get(report_name)
    if not report_config:
        frappe.throw(f"Unsupported report for WhatsApp send: {report_name}")

    parsed_filters = _parse_report_filters(filters)
    if not parsed_filters.get("customer"):
        frappe.throw("Customer filter is required before sending this report on WhatsApp.")

    config = _get_common_config()
    filename, pdf_bytes = _build_customer_report_pdf(
        report_name=report_name,
        filters=parsed_filters,
        include_ar=report_config["include_ar"],
        include_ledger=report_config["include_ledger"],
    )

    customer_doc = frappe.get_doc("Customer", parsed_filters.customer)
    content = (
        f"Dear {_safe_name(customer_doc.customer_name)},\n\n"
        f"Please find attached the {report_config['label']} report for {customer_doc.customer_name}.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )
    response = _send_attachment_message(
        config=config,
        recipient=recipient_mobile,
        content=content,
        filename=filename,
        file_bytes=pdf_bytes,
        contact_name=_safe_name(customer_doc.customer_name),
    )
    return {
        "message": f"{report_name} sent on WhatsApp to {recipient_label or recipient_mobile}",
        "response": response,
    }


def _enqueue_whatsapp_send(doctype, docname):
    automation = AUTOMATIONS[doctype]
    if not _is_send_enabled(automation):
        return

    frappe.enqueue(
        f"snrg_whatsapp.api.{automation['send_fn']}",
        queue="short",
        timeout=300,
        **{automation["name_key"]: docname},
    )


def _send_document_whatsapp(doctype, docname, raise_on_error=False, force=False):
    automation = AUTOMATIONS[doctype]

    try:
        _deliver_document_whatsapp(doctype, docname, automation, force=force)
    except Exception:
        frappe.db.rollback()
        safe_name = docname or "Unknown"
        message = frappe.get_traceback()
        frappe.log_error(message=message, title=f"{automation['failure_marker']}: {safe_name}")

        if frappe.db.exists(doctype, safe_name):
            doc = frappe.get_doc(doctype, safe_name)
            _add_timeline_note(doc, automation["failure_marker"], "See Error Log for traceback.")

        if raise_on_error:
            raise


def _deliver_document_whatsapp(
    doctype,
    docname,
    automation,
    force=False,
    recipient_override=None,
    note_context=None,
):
    doc = frappe.get_doc(doctype, docname)
    if doc.docstatus != 1:
        return None

    if not _is_eligible_doc(doc, automation):
        return None

    if not force and _already_sent(doc, automation["send_marker"]):
        return None

    config = _get_common_config()
    document_config = _get_document_config(automation)
    recipient = _normalize_phone(recipient_override) or _get_recipient_number(doc, automation)
    if not recipient:
        _add_timeline_note(doc, automation["failure_marker"], "No mobile number found.")
        return None

    filename = f"{doc.name}.pdf"
    response = _send_template_message(
        config=config,
        document_config=document_config,
        doc=doc,
        automation=automation,
        recipient=recipient,
        filename=filename,
    )

    message_id = response.get("source_id") if isinstance(response, dict) else None
    suffix = f" | Target: {note_context}" if note_context else ""
    _add_timeline_note(
        doc,
        automation["send_marker"],
        f"Recipient: {recipient} | Message ID: {message_id or 'n/a'}{suffix}",
    )

    frappe.logger().info(
        {
            "event": automation["event_name"],
            "doctype": doctype,
            "docname": doc.name,
            "recipient": recipient,
            "chatwoot_response": response,
        }
    )
    frappe.db.commit()
    return response


def _get_common_config():
    config = {
        "chatwoot_base_url": (frappe.conf.get("chatwoot_base_url") or "").rstrip("/"),
        "chatwoot_account_id": frappe.conf.get("chatwoot_account_id"),
        "chatwoot_api_access_token": frappe.conf.get("chatwoot_api_access_token"),
        "chatwoot_inbox_id": frappe.conf.get("chatwoot_inbox_id"),
    }

    missing = [
        key
        for key in (
            "chatwoot_base_url",
            "chatwoot_account_id",
            "chatwoot_api_access_token",
            "chatwoot_inbox_id",
        )
        if not config[key]
    ]
    if missing:
        frappe.throw("Missing WhatsApp config in site_config.json: " + ", ".join(missing))

    return config


def _get_document_config(automation):
    return {
        "template_name": frappe.conf.get(automation["template_name_key"])
        or automation["template_name_default"],
        "template_language": frappe.conf.get(automation["template_language_key"])
        or DEFAULT_TEMPLATE_LANGUAGE,
        "print_format": frappe.conf.get(automation["print_format_key"]),
    }


def _is_send_enabled(automation):
    return cint_or_none(frappe.conf.get(automation["enable_key"]), default=1) == 1


def _is_eligible_doc(doc, automation):
    expected_party_type = automation.get("party_type")
    party_type_field = automation.get("party_type_field")
    if expected_party_type and party_type_field and doc.get(party_type_field) != expected_party_type:
        return False
    return True


def _get_recipient_number(doc, automation):
    candidates = []
    contact_mobile_field = automation.get("contact_mobile_field")
    if contact_mobile_field:
        candidates.append(doc.get(contact_mobile_field))

    party_field = automation.get("party_field")
    party_type = automation.get("party_type")
    party_type_field = automation.get("party_type_field")
    party_name = doc.get(party_field) if party_field else None
    resolved_party_type = party_type or (doc.get(party_type_field) if party_type_field else None)

    if party_name and resolved_party_type == "Customer":
        candidates.append(frappe.db.get_value("Customer", party_name, "mobile_no"))
    elif party_name and resolved_party_type == "Lead":
        candidates.append(frappe.db.get_value("Lead", party_name, "mobile_no"))

    contact_person_field = automation.get("contact_person_field")
    if contact_person_field and doc.get(contact_person_field):
        contact = frappe.db.get_value(
            "Contact",
            doc.get(contact_person_field),
            ["mobile_no", "phone"],
            as_dict=True,
        )
        if contact:
            candidates.extend([contact.mobile_no, contact.phone])

    reference_mobile = _get_reference_mobile(doc)
    if reference_mobile:
        candidates.append(reference_mobile)

    for candidate in candidates:
        normalized = _normalize_phone(candidate)
        if normalized:
            return normalized

    return None


def _resolve_customer_for_manual_send(doctype=None, docname=None, customer=None):
    if customer:
        return customer

    if not doctype or not docname:
        return None

    if doctype not in ("Quotation", "Sales Invoice"):
        return None

    doc = frappe.get_doc(doctype, docname)
    if doctype == "Sales Invoice":
        return doc.get("customer")

    if doc.get("customer"):
        return doc.get("customer")

    if doc.get("quotation_to") == "Customer":
        party_name = doc.get("party_name")
        if party_name and frappe.db.exists("Customer", party_name):
            return party_name

    return None


def _get_customer_recipients(customer_name):
    if not frappe.db.exists("Customer", customer_name):
        return []

    customer_doc = frappe.get_doc("Customer", customer_name)
    recipients = []
    customer_mobile = _normalize_phone(customer_doc.get("custom_mobile_number"))
    if customer_mobile:
        recipients.append(
            {
                "kind": "customer",
                "label": customer_doc.customer_name or customer_doc.name,
                "button_label": f"Customer: {customer_doc.customer_name or customer_doc.name} ({customer_mobile})",
                "mobile": customer_mobile,
            }
        )

    for row in customer_doc.get("sales_team") or []:
        mobile = _normalize_phone(row.get("custom_official_mobile_number"))
        if not mobile:
            continue
        sales_person = row.get("sales_person") or "Sales Person"
        recipients.append(
            {
                "kind": "sales_person",
                "label": sales_person,
                "button_label": f"Sales: {sales_person} ({mobile})",
                "mobile": mobile,
            }
        )

    return recipients


def _get_reference_mobile(doc):
    if doc.doctype != "Payment Entry":
        return None

    references = doc.get("references") or []
    for reference in references:
        if reference.reference_doctype == "Sales Invoice" and reference.reference_name:
            invoice = frappe.db.get_value(
                "Sales Invoice",
                reference.reference_name,
                ["contact_mobile", "contact_person", "customer"],
                as_dict=True,
            )
            if not invoice:
                continue
            if invoice.contact_mobile:
                return invoice.contact_mobile
            if invoice.contact_person:
                contact = frappe.db.get_value("Contact", invoice.contact_person, ["mobile_no", "phone"], as_dict=True)
                if contact:
                    return contact.mobile_no or contact.phone
            if invoice.customer:
                return frappe.db.get_value("Customer", invoice.customer, "mobile_no")

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


def _already_sent(doc, marker):
    return bool(
        frappe.db.exists(
            "Comment",
            {
                "reference_doctype": doc.doctype,
                "reference_name": doc.name,
                "comment_type": "Comment",
                "content": ["like", f"%{marker}%"],
            },
        )
    )


def _add_timeline_note(doc, marker, detail):
    doc.add_comment("Comment", f"{marker}. {detail}")


def _build_pdf(doc, print_format=None):
    chosen_print_format = print_format or doc.get("select_print_heading") or None
    html = frappe.get_print(doc.doctype, doc.name, print_format=chosen_print_format, doc=doc)
    return get_pdf(html), f"{doc.name}.pdf"


def _send_template_message(config, document_config, doc, automation, recipient, filename):
    chatwoot_file = _upload_to_chatwoot(config, document_config, doc, filename)
    contact = _find_or_create_chatwoot_contact(config, doc, automation, recipient)
    conversation = _find_or_create_chatwoot_conversation(config, contact)
    conversation_id = conversation.get("id") or conversation.get("display_id")
    if not conversation_id:
        frappe.throw(f"Chatwoot conversation ID missing in response: {conversation}")

    payload = {
        "content": _build_preview(doc, automation),
        "message_type": "outgoing",
        "content_type": "text",
        "private": False,
        "attachments": [chatwoot_file["blob_id"]],
        "template_params": {
            "name": document_config["template_name"],
            "language": document_config["template_language"],
            "category": "UTILITY",
            "processed_params": {
                "header": {
                    "media_url": chatwoot_file["file_url"],
                    "media_type": "document",
                    "media_name": filename,
                },
                "body": _build_template_body(doc, automation),
            },
        },
    }

    response = requests.post(
        _chatwoot_url(config, f"conversations/{conversation_id}/messages"),
        headers=_chatwoot_headers(config),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, f"send {automation['template_action_label']} via Chatwoot")


def _upload_to_chatwoot(config, document_config, doc, filename):
    pdf_bytes, _ = _build_pdf(doc, document_config["print_format"])
    return _upload_file_bytes_to_chatwoot(config, pdf_bytes, filename)


def _upload_file_bytes_to_chatwoot(config, file_bytes, filename):
    response = requests.post(
        _chatwoot_url(config, "upload"),
        headers={"api_access_token": config["chatwoot_api_access_token"]},
        files={"attachment": (filename, io.BytesIO(file_bytes), "application/pdf")},
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, f"upload {filename} to Chatwoot")


def _send_attachment_message(config, recipient, content, filename, file_bytes, contact_name=None):
    chatwoot_file = _upload_file_bytes_to_chatwoot(config, file_bytes, filename)
    contact = _find_or_create_chatwoot_contact(
        config,
        display_name=contact_name or recipient,
        recipient=recipient,
    )
    conversation = _find_or_create_chatwoot_conversation(config, contact)
    conversation_id = conversation.get("id") or conversation.get("display_id")
    if not conversation_id:
        frappe.throw(f"Chatwoot conversation ID missing in response: {conversation}")

    payload = {
        "content": content,
        "message_type": "outgoing",
        "content_type": "text",
        "private": False,
        "attachments": [chatwoot_file["blob_id"]],
    }
    response = requests.post(
        _chatwoot_url(config, f"conversations/{conversation_id}/messages"),
        headers=_chatwoot_headers(config),
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, "send attachment message via Chatwoot")


def _find_or_create_chatwoot_contact(config, doc=None, automation=None, recipient=None, display_name=None):
    phone_number = _chatwoot_phone_number(recipient)
    contact = _find_chatwoot_contact(config, phone_number, recipient)
    if contact:
        return contact

    payload = {
        "name": display_name or _get_contact_name(doc, automation),
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


def _find_or_create_chatwoot_conversation(config, contact):
    response = requests.get(
        _chatwoot_url(config, f"contacts/{contact['id']}/conversations"),
        headers=_chatwoot_headers(config),
        timeout=REQUEST_TIMEOUT,
    )
    payload = _parse_chatwoot_response(response, "fetch Chatwoot conversations")
    inbox_id = int(config["chatwoot_inbox_id"])
    for conversation in payload.get("payload", []):
        if conversation.get("inbox_id") == inbox_id:
            return conversation

    response = requests.post(
        _chatwoot_url(config, "conversations"),
        headers=_chatwoot_headers(config),
        json={"inbox_id": inbox_id, "contact_id": contact["id"], "status": "open"},
        timeout=REQUEST_TIMEOUT,
    )
    return _parse_chatwoot_response(response, "create Chatwoot conversation")


def _get_contact_name(doc, automation):
    customer_name_field = automation.get("customer_name_field")
    if customer_name_field and doc.get(customer_name_field):
        return doc.get(customer_name_field)

    party_field = automation.get("party_field")
    if party_field and doc.get(party_field):
        return doc.get(party_field)

    return doc.name


def _build_template_body(doc, automation):
    if doc.doctype == "Sales Invoice":
        return {
            "1": _get_contact_name(doc, automation),
            "2": doc.name,
            "3": formatdate(doc.get(automation["doc_date_field"])),
            "4": _format_amount(doc.get("grand_total")),
        }

    if doc.doctype == "Payment Entry":
        return {
            "1": _get_contact_name(doc, automation),
            "2": _format_amount(_get_payment_entry_amount(doc)),
            "3": formatdate(doc.get(automation["doc_date_field"])),
        }

    return {
        "1": _get_contact_name(doc, automation),
        "2": doc.name,
        "3": formatdate(doc.get(automation["doc_date_field"])),
    }


def _build_preview(doc, automation):
    return globals()[automation["preview_builder"]](doc)


def _render_quotation_preview(doc):
    return (
        f"Dear {_safe_name(doc.customer_name or doc.party_name)},\n\n"
        f"Your quotation {doc.name} dated {formatdate(doc.transaction_date)} is generated.\n\n"
        "Please acknowledge receipt of this quotation. In case of any clarification or "
        "modification required, you may respond to this message.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )


def _render_sales_invoice_preview(doc):
    return (
        f"Dear {_safe_name(doc.customer_name or doc.customer)},\n\n"
        f"Your invoice {doc.name} dated {formatdate(doc.posting_date)} for amount "
        f"Rs. {_format_amount(doc.grand_total)} has been generated.\n\n"
        "Please find the invoice document attached for your reference.\n\n"
        "Kindly review the details and process the payment as per agreed terms.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )


def _render_payment_entry_preview(doc):
    return (
        f"Dear {_safe_name(doc.party_name)},\n\n"
        f"We acknowledge receipt of your payment of Rs. {_format_amount(_get_payment_entry_amount(doc))} "
        f"on {formatdate(doc.posting_date)}.\n\n"
        "The same has been recorded against your account. Please find the receipt attached "
        "for your reference.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )


def _safe_name(value):
    return value or "Customer"


def _get_payment_entry_amount(doc):
    for fieldname in ("received_amount", "paid_amount", "base_received_amount", "base_paid_amount"):
        value = doc.get(fieldname)
        if value:
            return value
    return 0


def _format_amount(value):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0
    return f"{amount:,.2f}"


def _chatwoot_headers(config):
    return {
        "api_access_token": config["chatwoot_api_access_token"],
        "Content-Type": "application/json",
    }


def _chatwoot_url(config, endpoint):
    return f"{config['chatwoot_base_url']}/api/v1/accounts/{config['chatwoot_account_id']}/{endpoint}"


def _parse_report_filters(filters):
    if isinstance(filters, str):
        return frappe._dict(json.loads(filters))
    return frappe._dict(filters or {})


def _build_customer_report_pdf(report_name, filters, include_ar, include_ledger):
    try:
        from customer_ledger.customer_ledger.report.customer_ledger_report import customer_ledger_report
    except ImportError as exc:
        frappe.throw(f"Customer Ledger app is required to send {report_name} on WhatsApp: {exc}")

    customer_ledger_report.download_customer_ledger_pdf(
        filters,
        include_ar=include_ar,
        include_ledger=include_ledger,
    )
    pdf_bytes = frappe.local.response.filecontent
    filename = frappe.local.response.filename
    frappe.local.response.type = "json"
    frappe.local.response.filecontent = None
    frappe.local.response.filename = None
    if not pdf_bytes or not filename:
        frappe.throw(f"Unable to generate PDF for {report_name}.")
    return filename, pdf_bytes


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
