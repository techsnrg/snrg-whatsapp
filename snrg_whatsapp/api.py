from datetime import datetime
import hashlib
import hmac
import io
import json
import re
import time

import frappe
import requests
from frappe.utils import formatdate, now_datetime
from frappe.utils.pdf import get_pdf


DEFAULT_TEMPLATE_LANGUAGE = "en_US"
REQUEST_TIMEOUT = 30
MANUAL_DOC_SEND_GROUP = "Send WhatsApp"
CHATWOOT_SIGNATURE_HEADER = "X-Chatwoot-Signature"
CHATWOOT_TIMESTAMP_HEADER = "X-Chatwoot-Timestamp"
CONFIRMATION_SOURCE_WHATSAPP = "WhatsApp"
CONFIRMATION_SOURCE_MANUAL = "Manual"
CONFIRMATION_PENDING = "Pending"
CONFIRMATION_CONFIRMED = "Confirmed"
CONFIRMATION_CHANGES_REQUESTED = "Changes Requested"
CONFIRMATION_EVENT_MARKER = "SNRG WhatsApp customer confirmation processed"
CONFIRMATION_MANUAL_MARKER = "SNRG WhatsApp customer confirmation set manually"
CONFIRMATION_UNMATCHED_TITLE = "SNRG WhatsApp customer confirmation unmatched"
CONFIRMATION_AMBIGUOUS_TITLE = "SNRG WhatsApp customer confirmation ambiguous"
CHATWOOT_MAX_SIGNATURE_AGE_SECONDS = 300
CONFIRMATION_STATUS_VALUES = {
    "confirm": CONFIRMATION_CONFIRMED,
    "confirmed": CONFIRMATION_CONFIRMED,
    "request_changes": CONFIRMATION_CHANGES_REQUESTED,
    "changes_requested": CONFIRMATION_CHANGES_REQUESTED,
    "changes requested": CONFIRMATION_CHANGES_REQUESTED,
    "pending": CONFIRMATION_PENDING,
}
SUPPORTED_REPORTS = {
    "Customer Ledger Report": {
        "label": "Customer Ledger",
        "single_include_ar": 0,
        "single_include_ledger": 1,
        "combined_include_ar": 1,
        "combined_include_ledger": 1,
        "single_action_label": "Ledger",
        "combined_action_label": "Ledger + AR",
    },
    "Customer AR Report": {
        "label": "Customer AR",
        "single_include_ar": 1,
        "single_include_ledger": 0,
        "combined_include_ar": 1,
        "combined_include_ledger": 1,
        "single_action_label": "AR",
        "combined_action_label": "Ledger + AR",
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
        "credit_note_template_name_key": "whatsapp_credit_note_template_name",
        "credit_note_template_name_default": "credit_note_erpnext",
        "credit_note_template_language_key": "whatsapp_credit_note_template_language",
        "credit_note_print_format_key": "whatsapp_credit_note_print_format",
        "credit_note_print_format_default": "Credit Note New",
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
        "print_format_default": "Payment Entry",
        "pay_template_name_key": "whatsapp_payment_pay_template_name",
        "pay_template_name_default": "payment_pay_erpnext",
        "pay_template_language_key": "whatsapp_payment_pay_template_language",
        "send_marker": "SNRG WhatsApp payment entry sent",
        "failure_marker": "SNRG WhatsApp payment entry failed",
        "event_name": "payment_entry_whatsapp_sent",
        "action_label": "payment entry",
        "template_action_label": "payment entry template",
        "preview_builder": "_render_payment_entry_preview",
        "doc_date_field": "posting_date",
        "party_field": "party_name",
        "party_type_field": "party_type",
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


def enqueue_pending_customer_confirmation_sync():
    _ensure_quotation_confirmation_setup()
    frappe.enqueue(
        "snrg_whatsapp.api.sync_pending_customer_confirmations",
        queue="long",
        timeout=600,
        enqueue_after_commit=True,
    )


def sync_pending_customer_confirmations(batch_size=20, max_age_days=14):
    _ensure_quotation_confirmation_setup()
    if not _can_sync_pending_customer_confirmations():
        return {"status": "skipped", "message": "Customer confirmation fields are not ready."}

    batch_size = max(1, cint_or_none(batch_size, default=20) or 20)
    max_age_days = max(1, cint_or_none(max_age_days, default=14) or 14)

    pending_rows = frappe.get_all(
        "Quotation",
        filters={
            "docstatus": 1,
            "customer_confirmation_status": CONFIRMATION_PENDING,
            "customer_confirmation_source": CONFIRMATION_SOURCE_WHATSAPP,
            "modified": [">=", frappe.utils.add_days(frappe.utils.now_datetime(), -max_age_days)],
            "customer_confirmation_outbound_conversation_id": ["is", "set"],
            "customer_confirmation_outbound_message_id": ["is", "set"],
        },
        fields=["name"],
        order_by="modified asc",
        limit=batch_size,
    )

    summary = {
        "status": "completed",
        "scanned": len(pending_rows),
        "processed": 0,
        "duplicates": 0,
        "not_found": 0,
        "ignored": 0,
        "errors": 0,
    }

    for row in pending_rows:
        try:
            quotation = frappe.get_doc("Quotation", row.name)
            result = _sync_customer_confirmation_from_chatwoot(quotation)
            status = result.get("status")
            if status == "processed":
                summary["processed"] += 1
                frappe.db.commit()
            elif status == "duplicate":
                summary["duplicates"] += 1
            elif status == "not_found":
                summary["not_found"] += 1
            else:
                summary["ignored"] += 1
        except Exception:
            summary["errors"] += 1
            frappe.db.rollback()
            frappe.log_error(
                title="SNRG WhatsApp pending confirmation sync failed",
                message=frappe.get_traceback(),
            )

    return summary


@frappe.whitelist(allow_guest=True)
def handle_chatwoot_confirmation_webhook():
    _ensure_quotation_confirmation_setup()
    raw_payload = frappe.request.get_data(cache=False) or b""
    parsed_payload = _parse_json_payload(raw_payload)
    if parsed_payload is None:
        return _webhook_response(400, {"status": "error", "message": "Malformed JSON payload."})

    if not _is_valid_chatwoot_signature(raw_payload):
        return _webhook_response(401, {"status": "error", "message": "Invalid Chatwoot signature."})

    if not _is_confirmation_event(parsed_payload):
        return _webhook_response(200, {"status": "ignored", "message": "Event is not a customer confirmation."})

    intent = _extract_confirmation_intent(parsed_payload)
    if not intent:
        return _webhook_response(200, {"status": "ignored", "message": "Inbound message is not a confirmation action."})

    try:
        quotation = _resolve_quotation_for_confirmation(parsed_payload)
    except AmbiguousConfirmationError as exc:
        _log_confirmation_issue(CONFIRMATION_AMBIGUOUS_TITLE, parsed_payload, str(exc))
        return _webhook_response(409, {"status": "error", "message": str(exc)})

    if not quotation:
        _log_confirmation_issue(CONFIRMATION_UNMATCHED_TITLE, parsed_payload, "No matching quotation found.")
        return _webhook_response(404, {"status": "error", "message": "No matching quotation found."})

    event_id = _extract_event_id(parsed_payload)
    if _confirmation_event_already_processed(quotation, event_id):
        return _webhook_response(
            200,
            {
                "status": "duplicate",
                "message": "Webhook event already processed.",
                "quotation": quotation.name,
            },
        )

    _apply_confirmation_update(quotation, parsed_payload, intent, event_id)
    frappe.db.commit()
    return _webhook_response(
        200,
        {
            "status": "processed",
            "quotation": quotation.name,
            "customer_confirmation_status": _intent_to_status(intent),
        },
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
def set_customer_confirmation_status(quotation_name, status, notes):
    _ensure_quotation_confirmation_setup()
    normalized_status = _normalize_manual_confirmation_status(status)
    notes = (notes or "").strip()
    if not notes:
        frappe.throw("Notes are required when setting customer confirmation manually.")

    quotation = frappe.get_doc("Quotation", quotation_name)
    if not quotation.has_permission("write"):
        frappe.throw("You do not have permission to update this quotation.")

    fields = {
        "customer_confirmation_status": normalized_status,
        "customer_confirmation_datetime": now_datetime(),
        "customer_confirmation_source": CONFIRMATION_SOURCE_MANUAL,
        "customer_confirmation_notes": notes,
    }
    _set_quotation_confirmation_fields(quotation, fields)
    _add_timeline_note(
        quotation,
        CONFIRMATION_MANUAL_MARKER,
        f"Status: {normalized_status}. Notes: {notes}",
    )
    frappe.db.commit()
    return {"message": f"Customer confirmation updated to {normalized_status}."}


@frappe.whitelist()
def sync_customer_confirmation_from_chatwoot(quotation_name):
    _ensure_quotation_confirmation_setup()

    quotation = frappe.get_doc("Quotation", quotation_name)
    if not quotation.has_permission("write"):
        frappe.throw("You do not have permission to update this quotation.")

    result = _sync_customer_confirmation_from_chatwoot(quotation)
    if result["status"] == "processed":
        frappe.db.commit()

    return result


@frappe.whitelist()
def ensure_customer_confirmation_setup():
    if "System Manager" not in frappe.get_roles():
        frappe.throw("Only a System Manager can initialize customer confirmation fields.")

    created = _ensure_quotation_confirmation_setup()
    return {
        "message": "Customer confirmation fields are ready.",
        "created": created,
    }


@frappe.whitelist()
def send_customer_report_whatsapp(
    report_name,
    recipient_mobile,
    recipient_label=None,
    filters=None,
    include_ar=None,
    include_ledger=None,
):
    report_config = SUPPORTED_REPORTS.get(report_name)
    if not report_config:
        frappe.throw(f"Unsupported report for WhatsApp send: {report_name}")

    parsed_filters = _parse_report_filters(filters)
    if not parsed_filters.get("customer"):
        frappe.throw("Customer filter is required before sending this report on WhatsApp.")

    include_ar = cint_or_none(include_ar, default=report_config["single_include_ar"])
    include_ledger = cint_or_none(include_ledger, default=report_config["single_include_ledger"])
    action_label = _get_report_action_label(report_config, include_ar, include_ledger)
    report_date = formatdate(parsed_filters.get("to_date") or frappe.utils.nowdate())

    config = _get_common_config()
    document_config = _get_report_template_config()
    filename, pdf_bytes = _build_customer_report_pdf(
        report_name=report_name,
        filters=parsed_filters,
        include_ar=include_ar,
        include_ledger=include_ledger,
    )

    customer_doc = frappe.get_doc("Customer", parsed_filters.customer)
    content = (
        f"Dear {_safe_name(customer_doc.customer_name)},\n\n"
        f"Please find attached your account statement as on {report_date}.\n\n"
        "Kindly review the details and let us know in case of any discrepancy or clarification required.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )
    response = _send_report_template_message(
        config=config,
        document_config=document_config,
        recipient=recipient_mobile,
        content=content,
        filename=filename,
        file_bytes=pdf_bytes,
        contact_name=_safe_name(customer_doc.customer_name),
        report_date=report_date,
    )
    return {
        "message": f"{action_label} sent on WhatsApp to {recipient_label or recipient_mobile}",
        "response": response,
    }


def _get_report_action_label(report_config, include_ar, include_ledger):
    if cint_or_none(include_ar) == cint_or_none(report_config["combined_include_ar"]) and cint_or_none(
        include_ledger
    ) == cint_or_none(report_config["combined_include_ledger"]):
        return report_config["combined_action_label"]

    return report_config["single_action_label"]


def _enqueue_whatsapp_send(doctype, docname):
    automation = AUTOMATIONS[doctype]
    if not _is_send_enabled(automation):
        return

    frappe.enqueue(
        f"snrg_whatsapp.api.{automation['send_fn']}",
        queue="short",
        timeout=300,
        enqueue_after_commit=True,
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
    document_config = _get_document_config(doc, automation)
    recipient = _normalize_phone(recipient_override) or _get_recipient_number(doc, automation)
    if not recipient:
        _add_timeline_note(doc, automation["failure_marker"], "No mobile number found.")
        return None

    if doctype == "Quotation":
        doc.customer_confirmation_token = _get_or_create_confirmation_token(doc)

    filename = f"{doc.name}.pdf"
    response = _send_template_message(
        config=config,
        document_config=document_config,
        doc=doc,
        automation=automation,
        recipient=recipient,
        filename=filename,
    )

    message_id = _extract_chatwoot_message_id(response)
    external_id = _extract_chatwoot_external_message_id(response)
    conversation_id = _extract_chatwoot_conversation_id(response)
    if doctype == "Quotation":
        _record_quotation_outbound_confirmation_context(
            doc,
            recipient=recipient,
            message_id=message_id,
            external_id=external_id,
            conversation_id=conversation_id,
        )

    suffix = f" | Target: {note_context}" if note_context else ""
    _add_timeline_note(
        doc,
        automation["send_marker"],
        f"Recipient: {recipient} | Message ID: {message_id or 'n/a'} | External ID: {external_id or 'n/a'} | Conversation ID: {conversation_id or 'n/a'}{suffix}",
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


def _get_document_config(doc, automation):
    if doc.doctype == "Sales Invoice" and cint_or_none(doc.get("is_return")) == 1:
        return {
            "template_name": _get_whatsapp_setting(
                automation["credit_note_template_name_key"],
                default=automation["credit_note_template_name_default"],
            ),
            "template_language": _get_whatsapp_setting(
                automation["credit_note_template_language_key"], default=DEFAULT_TEMPLATE_LANGUAGE
            ),
            "print_format": _get_whatsapp_setting(
                automation["credit_note_print_format_key"],
                default=automation["credit_note_print_format_default"],
            ),
        }

    if doc.doctype == "Payment Entry" and (doc.get("payment_type") or "") == "Pay":
        return {
            "template_name": _get_whatsapp_setting(
                automation["pay_template_name_key"],
                default=automation["pay_template_name_default"],
            ),
            "template_language": _get_whatsapp_setting(
                automation["pay_template_language_key"], default=DEFAULT_TEMPLATE_LANGUAGE
            ),
            "print_format": _get_whatsapp_setting(
                automation["print_format_key"], default=automation.get("print_format_default")
            ),
        }

    return {
        "template_name": _get_whatsapp_setting(
            automation["template_name_key"], default=automation["template_name_default"]
        ),
        "template_language": _get_whatsapp_setting(
            automation["template_language_key"], default=DEFAULT_TEMPLATE_LANGUAGE
        ),
        "print_format": _get_whatsapp_setting(
            automation["print_format_key"], default=automation.get("print_format_default")
        ),
    }


def _get_report_template_config():
    return {
        "template_name": _get_whatsapp_setting(
            "whatsapp_report_template_name", default="customer_ledger_statement"
        ),
        "template_language": _get_whatsapp_setting(
            "whatsapp_report_template_language", default="en"
        ),
    }


def _is_send_enabled(automation):
    return cint_or_none(_get_whatsapp_setting(automation["enable_key"], default=1), default=1) == 1


def _get_whatsapp_setting(key, default=None):
    settings = _get_whatsapp_settings()
    if settings:
        value = None
        if key == "chatwoot_webhook_secret":
            try:
                value = settings.get_password(key)
            except Exception:
                value = None
        if value in (None, ""):
            value = settings.get(key)
        if value not in (None, ""):
            return value

    config_value = frappe.conf.get(key)
    if config_value not in (None, ""):
        return config_value

    return default


def _get_whatsapp_settings():
    try:
        if not frappe.db.exists("DocType", "SNRG WhatsApp Settings"):
            return None
        return frappe.get_cached_doc("SNRG WhatsApp Settings")
    except Exception:
        return None


def _is_eligible_doc(doc, automation):
    if doc.doctype == "Payment Entry":
        payment_type = doc.get("payment_type") or ""
        party_type = doc.get("party_type") or ""
        if party_type == "Employee":
            return False
        if payment_type == "Receive":
            return party_type == "Customer"
        if payment_type == "Pay":
            return party_type == "Supplier"
        return False

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

    if party_name and resolved_party_type:
        candidates.extend(_get_party_mobile_candidates(resolved_party_type, party_name))

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


def _get_party_mobile_candidates(party_type, party_name):
    if party_type == "Customer":
        return _get_customer_mobile_candidates(party_name)
    if party_type == "Lead":
        return _get_linked_contact_mobile_candidates("Lead", party_name) + [
            frappe.db.get_value("Lead", party_name, "mobile_no")
        ]
    if party_type == "Supplier":
        return _get_supplier_mobile_candidates(party_name)
    return _get_linked_contact_mobile_candidates(party_type, party_name)


def _get_customer_mobile_candidates(customer_name):
    if not customer_name or not frappe.db.exists("Customer", customer_name):
        return []

    customer = frappe.db.get_value(
        "Customer",
        customer_name,
        ["mobile_no", "custom_mobile_number"],
        as_dict=True,
    )
    candidates = []
    if customer:
        candidates.extend([customer.mobile_no, customer.custom_mobile_number])

    candidates.extend(_get_linked_contact_mobile_candidates("Customer", customer_name))

    return candidates


def _get_supplier_mobile_candidates(supplier_name):
    if not supplier_name or not frappe.db.exists("Supplier", supplier_name):
        return []

    candidates = []
    for fieldname in ("mobile_no", "phone"):
        if frappe.db.has_column("Supplier", fieldname):
            candidates.append(frappe.db.get_value("Supplier", supplier_name, fieldname))

    candidates.extend(_get_linked_contact_mobile_candidates("Supplier", supplier_name))

    return candidates


def _get_linked_contact_mobile_candidates(link_doctype, link_name):
    dynamic_links = frappe.get_all(
        "Dynamic Link",
        filters={
            "link_doctype": link_doctype,
            "link_name": link_name,
            "parenttype": "Contact",
        },
        pluck="parent",
    )
    candidates = []
    if dynamic_links:
        contacts = frappe.get_all(
            "Contact",
            filters={"name": ["in", dynamic_links]},
            fields=["mobile_no", "phone"],
        )
        for contact in contacts:
            candidates.extend([contact.get("mobile_no"), contact.get("phone")])

    return candidates


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
        button_label = f"Customer: {customer_doc.customer_name or customer_doc.name} ({customer_mobile})"
    else:
        button_label = f"Customer: {customer_doc.customer_name or customer_doc.name} (No Mobile)"
        
    recipients.append(
        {
            "kind": "customer",
            "label": customer_doc.customer_name or customer_doc.name,
            "button_label": button_label,
            "mobile": customer_mobile,
        }
    )

    for row in customer_doc.get("sales_team") or []:
        mobile = _normalize_phone(row.get("custom_official_mobile_number"))
        sales_person = row.get("sales_person") or "Sales Person"
        
        if not mobile:
            button_label = f"Sales: {sales_person} (No Mobile)"
        else:
            button_label = f"Sales: {sales_person} ({mobile})"
            
        recipients.append(
            {
                "kind": "sales_person",
                "label": sales_person,
                "button_label": button_label,
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
    parsed = _parse_chatwoot_response(response, f"send {automation['template_action_label']} via Chatwoot")
    return _hydrate_chatwoot_message_reference(
        config=config,
        conversation_id=conversation_id,
        response_payload=parsed,
        content=payload["content"],
    )


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


def _send_report_template_message(
    config,
    document_config,
    recipient,
    content,
    filename,
    file_bytes,
    contact_name,
    report_date,
):
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
                "body": {
                    "1": contact_name,
                    "2": report_date,
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
    return _parse_chatwoot_response(response, "send customer report template via Chatwoot")


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
        if (doc.get("payment_type") or "") == "Pay":
            return {
                "1": _get_contact_name(doc, automation),
                "2": _format_amount(_get_payment_entry_amount(doc)),
                "3": formatdate(doc.get(automation["doc_date_field"])),
                "4": doc.get("reference_no") or doc.name,
            }

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
    token = doc.get("customer_confirmation_token") or _get_or_create_confirmation_token(doc)
    return (
        f"Dear {_safe_name(doc.customer_name or doc.party_name)},\n\n"
        f"Your quotation {doc.name} dated {formatdate(doc.transaction_date)} is generated.\n\n"
        "Please acknowledge receipt of this quotation. In case of any clarification or "
        "modification required, you may respond to this message.\n\n"
        f"Reference: {doc.name} | Token: {token}\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )


def _render_sales_invoice_preview(doc):
    if cint_or_none(doc.get("is_return")) == 1:
        return (
            f"Dear {_safe_name(doc.customer_name or doc.customer)},\n\n"
            f"Your Credit Note {doc.name} dated {formatdate(doc.posting_date)} for amount "
            f"Rs. {_format_amount(doc.grand_total)} has been generated.\n\n"
            "Please find the Credit Note document attached for your reference.\n\n"
            "Kindly review the details and confirm if any changes required.\n\n"
            "Regards,\nSNRG Electricals India Private Limited"
        )

    return (
        f"Dear {_safe_name(doc.customer_name or doc.customer)},\n\n"
        f"Your invoice {doc.name} dated {formatdate(doc.posting_date)} for amount "
        f"Rs. {_format_amount(doc.grand_total)} has been generated.\n\n"
        "Please find the invoice document attached for your reference.\n\n"
        "Kindly review the details and process the payment as per agreed terms.\n\n"
        "Regards,\nSNRG Electricals India Private Limited"
    )


def _render_payment_entry_preview(doc):
    if (doc.get("payment_type") or "") == "Pay":
        return (
            f"Dear {_safe_name(doc.party_name)},\n\n"
            f"This is to inform you that a payment of Rs. {_format_amount(_get_payment_entry_amount(doc))} "
            f"has been made on {formatdate(doc.posting_date)}.\n\n"
            f"The transaction reference number is {doc.get('reference_no') or doc.name}.\n\n"
            "Please find the payment details attached for your reference.\n\n"
            "Regards,\nSNRG Electricals India Private Limited"
        )

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


class AmbiguousConfirmationError(Exception):
    pass


def _parse_json_payload(raw_payload):
    try:
        return json.loads((raw_payload or b"{}").decode("utf-8"))
    except Exception:
        return None


def _webhook_response(status_code, payload):
    frappe.local.response["http_status_code"] = status_code
    return payload


def _is_valid_chatwoot_signature(raw_payload):
    secret = _get_whatsapp_setting("chatwoot_webhook_secret")
    if not secret:
        frappe.throw("Missing Chatwoot webhook secret in SNRG WhatsApp Settings or site config.")

    provided = (frappe.get_request_header(CHATWOOT_SIGNATURE_HEADER) or "").strip()
    timestamp = (frappe.get_request_header(CHATWOOT_TIMESTAMP_HEADER) or "").strip()
    if not provided or not timestamp:
        return False

    if not _is_recent_chatwoot_timestamp(timestamp):
        return False

    message = f"{timestamp}.".encode("utf-8") + (raw_payload or b"")
    expected = "sha256=" + hmac.new(
        secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided, expected)


def _is_recent_chatwoot_timestamp(timestamp):
    try:
        signed_at = int(timestamp)
    except (TypeError, ValueError):
        return False

    return abs(int(time.time()) - signed_at) <= CHATWOOT_MAX_SIGNATURE_AGE_SECONDS


def _is_confirmation_event(payload):
    event_name = (payload.get("event") or "").strip().lower()
    if event_name and event_name not in {"message_created", "message_updated"}:
        return False

    message = _get_message_payload(payload)
    if not message:
        return False

    if cint_or_none(message.get("private"), default=0):
        return False

    message_type = str(message.get("message_type") or "").strip().lower()
    if message_type in {"outgoing", "template", "activity"}:
        return False
    if str(message.get("message_type")) == "1":
        return False

    sender = _get_sender_payload(payload)
    sender_type = str(sender.get("type") or sender.get("sender_type") or "").strip().lower()
    if sender_type in {"agent", "user"}:
        return False

    return True


def _get_message_payload(payload):
    return payload.get("message") or payload


def _get_sender_payload(payload):
    message = _get_message_payload(payload)
    sender = message.get("sender") or payload.get("sender")
    if isinstance(sender, dict):
        return sender

    meta_sender = (((payload.get("conversation") or {}).get("meta") or {}).get("sender")) or {}
    return meta_sender if isinstance(meta_sender, dict) else {}


def _extract_confirmation_intent(payload):
    candidate_texts = _collect_confirmation_texts(payload)
    for candidate in candidate_texts:
        normalized = _normalize_confirmation_text(candidate)
        if normalized in {"confirm", "confirmed"}:
            return "confirm"
        if normalized in {"request changes", "changes requested", "request_changes", "changes_requested"}:
            return "request_changes"
    return None


def _collect_confirmation_texts(payload):
    message = _get_message_payload(payload)
    content_attributes = message.get("content_attributes") or {}
    values = [
        message.get("content"),
        message.get("content_type"),
        payload.get("content"),
        content_attributes.get("submitted_values"),
        content_attributes.get("selected_option"),
        content_attributes.get("title"),
        content_attributes.get("value"),
        content_attributes.get("button_text"),
        content_attributes.get("text"),
        content_attributes.get("display_text"),
        content_attributes.get("payload"),
    ]
    values.extend(_flatten_strings(content_attributes))
    return [value for value in values if isinstance(value, str) and value.strip()]


def _flatten_strings(value):
    items = []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for nested in value.values():
            items.extend(_flatten_strings(nested))
    elif isinstance(value, (list, tuple)):
        for nested in value:
            items.extend(_flatten_strings(nested))
    return items


def _normalize_confirmation_text(value):
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    text = re.sub(r"[^a-z ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _sync_customer_confirmation_from_chatwoot(quotation):
    conversation_id = str(quotation.get("customer_confirmation_outbound_conversation_id") or "").strip()
    if not conversation_id:
        return {
            "status": "missing_context",
            "message": "No Chatwoot conversation is stored for this quotation yet.",
        }

    config = _get_common_config()
    messages = _fetch_chatwoot_conversation_messages(config, conversation_id)
    message = _find_chatwoot_confirmation_message_for_quotation(quotation, conversation_id, messages)
    if not message:
        return {
            "status": "not_found",
            "message": "No customer confirmation reply was found in Chatwoot for this quotation yet.",
        }

    payload = _build_chatwoot_sync_payload(message, conversation_id)
    intent = _extract_confirmation_intent(payload)
    if not intent:
        return {
            "status": "ignored",
            "message": "The latest linked Chatwoot reply is not a supported confirmation action.",
        }

    event_id = _extract_event_id(payload)
    if _confirmation_event_already_processed(quotation, event_id):
        return {
            "status": "duplicate",
            "message": "This customer confirmation was already processed.",
            "quotation": quotation.name,
            "event_id": event_id,
        }

    _apply_confirmation_update(quotation, payload, intent, event_id)
    return {
        "status": "processed",
        "message": f"Customer confirmation updated to {_intent_to_status(intent)}.",
        "quotation": quotation.name,
        "event_id": event_id,
        "customer_confirmation_status": _intent_to_status(intent),
    }


def _resolve_quotation_for_confirmation(payload):
    matchers = [
        _find_quotation_by_referenced_message,
        _find_quotation_by_referenced_external_id,
        _find_quotation_by_chatwoot_reply_context,
        _find_quotation_by_conversation,
        _find_quotation_by_explicit_reference,
        _find_quotation_by_contact,
    ]
    for matcher in matchers:
        quotation = matcher(payload)
        if quotation:
            return quotation
    return None


def _find_chatwoot_confirmation_message_for_quotation(quotation, conversation_id, messages):
    ordered_messages = _sort_chatwoot_messages(messages)
    outbound_message_id = str(quotation.get("customer_confirmation_outbound_message_id") or "").strip()
    outbound_external_id = str(quotation.get("customer_confirmation_outbound_external_id") or "").strip()
    outbound_contact = _normalize_phone(quotation.get("customer_confirmation_outbound_contact"))

    exact_match = None
    fallback_match = None
    for message in ordered_messages:
        payload = _build_chatwoot_sync_payload(message, conversation_id)
        if not _is_confirmation_event(payload):
            continue

        intent = _extract_confirmation_intent(payload)
        if not intent:
            continue

        referenced_message_id = _extract_referenced_message_id(payload)
        referenced_external_id = _extract_referenced_external_message_id(payload)
        if outbound_message_id and referenced_message_id == outbound_message_id:
            return message
        if outbound_external_id and referenced_external_id == outbound_external_id:
            return message

        if outbound_contact and _extract_contact_number(payload) == outbound_contact and not fallback_match:
            fallback_match = message

        if not exact_match:
            exact_match = message

    return fallback_match or exact_match


def _find_quotation_by_referenced_message(payload):
    referenced_message_id = _extract_referenced_message_id(payload)
    if not referenced_message_id:
        return None

    matches = _find_quotations_by_field("customer_confirmation_outbound_message_id", referenced_message_id)
    return _resolve_unique_quotation_match(matches, "Quoted message matches multiple quotations.")


def _find_quotation_by_referenced_external_id(payload):
    referenced_external_id = _extract_referenced_external_message_id(payload)
    if not referenced_external_id:
        return None

    matches = _find_quotations_by_field("customer_confirmation_outbound_external_id", referenced_external_id)
    return _resolve_unique_quotation_match(matches, "Quoted external message matches multiple quotations.")


def _find_quotation_by_chatwoot_reply_context(payload):
    conversation_id = _extract_conversation_id(payload)
    if not conversation_id:
        return None

    referenced_message_id = _extract_referenced_message_id(payload)
    referenced_external_id = _extract_referenced_external_message_id(payload)
    if not referenced_message_id and not referenced_external_id:
        return None

    config = _get_common_config()
    message = _fetch_chatwoot_referenced_message(
        config=config,
        conversation_id=conversation_id,
        message_id=referenced_message_id,
        external_id=referenced_external_id,
    )
    if not message:
        return None

    reference_payload = {
        "content": message.get("content"),
        "message": {
            "content": message.get("content"),
            "content_attributes": message.get("content_attributes") or {},
        },
    }
    return _find_quotation_by_explicit_reference(reference_payload)


def _find_quotation_by_conversation(payload):
    conversation_id = _extract_conversation_id(payload)
    if not conversation_id:
        return None

    matches = _find_quotations_by_field("customer_confirmation_outbound_conversation_id", str(conversation_id))
    if len(matches) == 1:
        return matches[0]

    pending_matches = [doc for doc in matches if doc.get("customer_confirmation_status") == CONFIRMATION_PENDING]
    if len(pending_matches) == 1:
        return pending_matches[0]
    if len(matches) > 1:
        raise AmbiguousConfirmationError("Conversation matches multiple quotations.")
    return None


def _find_quotation_by_explicit_reference(payload):
    candidates = _extract_reference_candidates(payload)
    if not candidates:
        return None

    for candidate in candidates:
        if frappe.db.exists("Quotation", candidate):
            return frappe.get_doc("Quotation", candidate)

    token_matches = []
    if frappe.db.has_column("Quotation", "customer_confirmation_token"):
        for token in candidates:
            token_matches.extend(_find_quotations_by_field("customer_confirmation_token", token))
    return _resolve_unique_quotation_match(token_matches, "Reference token matches multiple quotations.")


def _find_quotation_by_contact(payload):
    contact = _extract_contact_number(payload)
    if not contact:
        return None

    matches = _find_quotations_by_field("customer_confirmation_outbound_contact", contact)
    if len(matches) == 1:
        return matches[0]

    pending_matches = [doc for doc in matches if doc.get("customer_confirmation_status") == CONFIRMATION_PENDING]
    if len(pending_matches) == 1:
        return pending_matches[0]
    if len(pending_matches) > 1:
        raise AmbiguousConfirmationError("Contact matches multiple pending quotations.")
    return None


def _resolve_unique_quotation_match(matches, error_message):
    unique_names = []
    seen = set()
    for match in matches or []:
        if match.name in seen:
            continue
        seen.add(match.name)
        unique_names.append(match)

    if len(unique_names) > 1:
        raise AmbiguousConfirmationError(error_message)
    return unique_names[0] if unique_names else None


def _find_quotations_by_field(fieldname, value):
    if not value or not frappe.db.has_column("Quotation", fieldname):
        return []

    names = frappe.get_all(
        "Quotation",
        filters={fieldname: str(value), "docstatus": 1},
        fields=["name"],
        order_by="modified desc",
        limit=5,
    )
    return [frappe.get_doc("Quotation", row.name) for row in names]


def _extract_reference_candidates(payload):
    candidates = set()
    for value in _collect_confirmation_texts(payload):
        for pattern in (
            r"quotation\s+([A-Za-z0-9./_-]+)",
            r"reference\s*[:#-]?\s*([A-Za-z0-9./_-]+)",
            r"token\s*[:#-]?\s*([A-Za-z0-9_-]+)",
        ):
            for match in re.findall(pattern, value, flags=re.IGNORECASE):
                if match:
                    candidates.add(match.strip())
    return list(candidates)


def _extract_referenced_message_id(payload):
    message = _get_message_payload(payload)
    content_attributes = message.get("content_attributes") or {}
    candidates = [
        content_attributes.get("in_reply_to"),
        content_attributes.get("in_reply_to_message_id"),
        content_attributes.get("in_reply_to_external_id"),
        content_attributes.get("quoted_message_id"),
        content_attributes.get("context_message_id"),
        payload.get("in_reply_to"),
    ]
    for candidate in candidates:
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _extract_referenced_external_message_id(payload):
    message = _get_message_payload(payload)
    content_attributes = message.get("content_attributes") or {}
    for candidate in (
        content_attributes.get("in_reply_to_external_id"),
        content_attributes.get("quoted_message_external_id"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _extract_event_id(payload):
    message = _get_message_payload(payload)
    for candidate in (
        message.get("id"),
        message.get("source_id"),
        payload.get("id"),
        payload.get("source_id"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _extract_conversation_id(payload):
    message = _get_message_payload(payload)
    conversation = payload.get("conversation") or {}
    for candidate in (
        message.get("conversation_id"),
        conversation.get("id"),
        conversation.get("display_id"),
        payload.get("conversation_id"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _extract_chatwoot_conversation_id(response):
    if not isinstance(response, dict):
        return None

    conversation = response.get("conversation") or {}
    for candidate in (
        response.get("conversation_id"),
        conversation.get("id"),
        conversation.get("display_id"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _extract_chatwoot_message_id(response):
    if not isinstance(response, dict):
        return None

    for candidate in (
        response.get("id"),
        response.get("message_id"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _extract_chatwoot_external_message_id(response):
    if not isinstance(response, dict):
        return None

    for candidate in (
        response.get("source_id"),
        response.get("external_id"),
    ):
        if candidate not in (None, ""):
            return str(candidate)
    return None


def _hydrate_chatwoot_message_reference(config, conversation_id, response_payload, content):
    if not isinstance(response_payload, dict):
        return response_payload

    if _extract_chatwoot_message_id(response_payload) and _extract_chatwoot_external_message_id(response_payload):
        return response_payload

    message = _find_matching_chatwoot_message(
        config=config,
        conversation_id=conversation_id,
        content=content,
    )
    if not message:
        return response_payload

    merged = dict(response_payload)
    merged.setdefault("id", message.get("id"))
    merged.setdefault("message_id", message.get("id"))
    merged.setdefault("source_id", message.get("source_id"))
    merged.setdefault("conversation_id", conversation_id)
    return merged


def _find_matching_chatwoot_message(config, conversation_id, content):
    messages = _fetch_chatwoot_conversation_messages(config, conversation_id)
    normalized_content = (content or "").strip()
    for message in messages:
        if str(message.get("message_type")) not in {"outgoing", "1"}:
            continue
        if (message.get("content") or "").strip() == normalized_content:
            return message
    return messages[0] if messages else None


def _fetch_chatwoot_referenced_message(config, conversation_id, message_id=None, external_id=None):
    messages = _fetch_chatwoot_conversation_messages(config, conversation_id)
    for message in messages:
        if message_id and str(message.get("id")) == str(message_id):
            return message
        if external_id and str(message.get("source_id")) == str(external_id):
            return message
    return None


def _fetch_chatwoot_conversation_messages(config, conversation_id):
    response = requests.get(
        _chatwoot_url(config, f"conversations/{conversation_id}/messages"),
        headers=_chatwoot_headers(config),
        timeout=REQUEST_TIMEOUT,
    )
    payload = _parse_chatwoot_response(response, "fetch Chatwoot conversation messages")
    messages = payload.get("payload") if isinstance(payload, dict) else None
    return messages if isinstance(messages, list) else []


def _sort_chatwoot_messages(messages):
    def sort_key(message):
        created_at = _parse_datetime_value(message.get("created_at"))
        if created_at:
            return (created_at.timestamp(), cint_or_none(message.get("id"), default=0))
        return (0, cint_or_none(message.get("id"), default=0))

    return sorted(messages or [], key=sort_key, reverse=True)


def _build_chatwoot_sync_payload(message, conversation_id):
    payload = {
        "event": "message_created",
        "conversation": {"id": conversation_id},
        "message": message,
    }
    for key in ("id", "source_id", "content", "message_type", "sender"):
        if key in message:
            payload[key] = message.get(key)
    return payload


def _extract_contact_number(payload):
    sender = _get_sender_payload(payload)
    conversation = payload.get("conversation") or {}
    meta_sender = (conversation.get("meta") or {}).get("sender") or {}
    for candidate in (
        sender.get("phone_number"),
        meta_sender.get("phone_number"),
        payload.get("phone_number"),
    ):
        normalized = _normalize_phone(candidate)
        if normalized:
            return normalized
    return None


def _apply_confirmation_update(quotation, payload, intent, event_id):
    fields = {
        "customer_confirmation_status": _intent_to_status(intent),
        "customer_confirmation_datetime": _extract_event_datetime(payload) or now_datetime(),
        "customer_confirmation_source": CONFIRMATION_SOURCE_WHATSAPP,
        "customer_confirmation_message_id": event_id,
        "customer_confirmation_conversation_id": _extract_conversation_id(payload),
        "customer_confirmation_contact": _extract_contact_number(payload),
        "customer_confirmation_payload": _compact_json(payload),
    }
    _set_quotation_confirmation_fields(quotation, fields)

    if intent == "confirm":
        detail = f"Customer confirmed via WhatsApp. Event ID: {event_id or 'n/a'}"
    else:
        detail = f"Customer requested changes via WhatsApp. Event ID: {event_id or 'n/a'}"
    _add_timeline_note(quotation, CONFIRMATION_EVENT_MARKER, detail)


def _intent_to_status(intent):
    return CONFIRMATION_STATUS_VALUES[intent]


def _extract_event_datetime(payload):
    message = _get_message_payload(payload)
    for candidate in (
        message.get("created_at"),
        message.get("updated_at"),
        payload.get("created_at"),
        payload.get("timestamp"),
    ):
        parsed = _parse_datetime_value(candidate)
        if parsed:
            return parsed
    return None


def _parse_datetime_value(value):
    if value in (None, ""):
        return None

    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None
    try:
        return frappe.utils.get_datetime(text)
    except Exception:
        return None


def _ensure_quotation_confirmation_setup():
    required_columns = (
        "customer_confirmation_status",
        "customer_confirmation_datetime",
        "customer_confirmation_source",
        "customer_confirmation_notes",
    )
    required_custom_fields = (
        "customer_confirmation_tab",
        "snrg_customer_confirmation_section",
        "customer_confirmation_status",
        "customer_confirmation_datetime",
        "customer_confirmation_source",
        "customer_confirmation_notes",
    )
    if all(frappe.db.has_column("Quotation", fieldname) for fieldname in required_columns) and all(
        frappe.db.exists("Custom Field", f"Quotation-{fieldname}") for fieldname in required_custom_fields
    ):
        return False

    from snrg_whatsapp.patches.v0_0_1.add_quotation_confirmation_fields import execute as add_confirmation_fields
    from snrg_whatsapp.patches.v0_0_1.reposition_quotation_confirmation_fields import (
        execute as reposition_confirmation_fields,
    )

    add_confirmation_fields()
    reposition_confirmation_fields()
    frappe.clear_cache(doctype="Quotation")
    return True


def _can_sync_pending_customer_confirmations():
    required_columns = (
        "customer_confirmation_status",
        "customer_confirmation_source",
        "customer_confirmation_outbound_conversation_id",
        "customer_confirmation_outbound_message_id",
    )
    return all(frappe.db.has_column("Quotation", fieldname) for fieldname in required_columns)


def _set_quotation_confirmation_fields(doc, fields):
    if not fields:
        return

    _ensure_quotation_confirmation_setup()

    for fieldname, value in fields.items():
        if not frappe.db.has_column("Quotation", fieldname):
            continue
        doc.db_set(fieldname, value, update_modified=False)
        doc.set(fieldname, value)


def _record_quotation_outbound_confirmation_context(doc, recipient, message_id, external_id, conversation_id):
    fields = {
        "customer_confirmation_status": CONFIRMATION_PENDING,
        "customer_confirmation_source": CONFIRMATION_SOURCE_WHATSAPP,
        "customer_confirmation_datetime": None,
        "customer_confirmation_message_id": None,
        "customer_confirmation_conversation_id": None,
        "customer_confirmation_contact": None,
        "customer_confirmation_payload": None,
        "customer_confirmation_outbound_message_id": message_id,
        "customer_confirmation_outbound_external_id": external_id,
        "customer_confirmation_outbound_conversation_id": conversation_id,
        "customer_confirmation_outbound_contact": recipient,
        "customer_confirmation_token": doc.get("customer_confirmation_token") or _get_or_create_confirmation_token(doc),
    }
    _set_quotation_confirmation_fields(doc, fields)


def _get_or_create_confirmation_token(doc):
    token = (doc.get("customer_confirmation_token") or "").strip()
    if token:
        return token
    return hashlib.sha1(doc.name.encode("utf-8")).hexdigest()[:10].upper()


def _confirmation_event_already_processed(doc, event_id):
    if not event_id:
        return False

    if str(doc.get("customer_confirmation_message_id") or "") == str(event_id):
        return True

    return bool(
        frappe.db.exists(
            "Comment",
            {
                "reference_doctype": doc.doctype,
                "reference_name": doc.name,
                "comment_type": "Comment",
                "content": ["like", f"%Event ID: {event_id}%"],
            },
        )
    )


def _normalize_manual_confirmation_status(status):
    normalized = CONFIRMATION_STATUS_VALUES.get((status or "").strip().lower())
    if not normalized:
        frappe.throw("Status must be Pending, Confirmed, or Changes Requested.")
    return normalized


def _compact_json(payload):
    try:
        return json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except Exception:
        return json.dumps({"raw": str(payload)})


def _log_confirmation_issue(title, payload, detail):
    frappe.log_error(
        title=title,
        message=_compact_json({"detail": detail, "payload": payload}),
    )


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
