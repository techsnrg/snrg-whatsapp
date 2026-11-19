import hashlib
import json
import os
import re

import frappe
import requests
from frappe.utils import cint, get_datetime, get_system_timezone, now_datetime

from snrg_whatsapp import api, templates

CAMPAIGN = "SNRG WhatsApp Campaign"
RECIPIENT = "SNRG WhatsApp Campaign Recipient"
MAX_RECIPIENTS = 500
CONSENT_FIELDS = {
    "UTILITY": "snrg_whatsapp_campaign_opt_in",
    "MARKETING": "snrg_whatsapp_marketing_opt_in",
}
CUSTOMER_VARIABLES = {
    "@customer_name": "customer_name",
    "@customer_id": "name",
    "@customer_group": "customer_group",
    "@territory": "territory",
}
DELIVERY_STATES = {"sent": "Sent", "delivered": "Delivered", "read": "Read", "failed": "Failed"}


def get_campaign(name, lock=False):
    frappe.only_for("System Manager")
    doc = frappe.get_doc(CAMPAIGN, name, for_update=lock)
    doc.check_permission("write")
    return doc


@frappe.whitelist(methods=["POST"])
def create_draft(customers):
    frappe.only_for("System Manager")
    selected = frappe.parse_json(customers)
    if not isinstance(selected, list) or not 0 < len(selected) <= MAX_RECIPIENTS:
        frappe.throw(f"Select between 1 and {MAX_RECIPIENTS} customers.")
    doc = frappe.new_doc(CAMPAIGN)
    doc.campaign_name = "WhatsApp campaign"
    for customer in dict.fromkeys(selected):
        frappe.get_doc("Customer", customer).check_permission("read")
        doc.append("recipients", {"customer": customer})
    doc.insert()
    return doc.name


def template_content(template):
    if not template or template["status"] != "APPROVED" or template["category"] not in CONSENT_FIELDS:
        frappe.throw("Choose an approved Utility or Marketing template.")
    if template.get("parameter_format") not in (None, "", "POSITIONAL"):
        frappe.throw("Campaigns currently support numbered body variables.")
    components = template["components"]
    kinds = [part["type"] for part in components]
    if kinds.count("BODY") != 1 or len(kinds) != len(set(kinds)) or set(kinds) - {"BODY", "HEADER", "FOOTER"}:
        frappe.throw("Choose a template with a text body, an optional static text or image header, and an optional static footer.")
    header = next((part for part in components if part["type"] == "HEADER"), {})
    header_format = header.get("format")
    header_text = header.get("text") or ""
    if header and (
        header_format not in {"TEXT", "IMAGE"}
        or (header_format == "TEXT" and templates.positional_keys(header_text))
    ):
        frappe.throw("Choose a template with a static text or image header.")
    body = next(part["text"] for part in components if part["type"] == "BODY")
    footer = next((part["text"] for part in components if part["type"] == "FOOTER"), "")
    return {
        "id": str(template["id"]), "name": template["name"], "language": template["language"],
        "category": template["category"], "body": body, "footer": footer,
        "header": header_text, "image": header_format == "IMAGE", "keys": templates.positional_keys(body),
    }


def get_live_template(template):
    matches = [item for item in templates.iter_meta_templates(template["name"])
               if str(item["id"]) == template["id"] and item["language"] == template["language"]]
    return template_content(matches[0] if matches else None)


def cached_template(doc):
    template = frappe.get_doc(templates.TEMPLATE, doc.template)
    template.check_permission("read")
    account, _, _ = templates.meta_config()
    if template.waba_id != account:
        frappe.throw("Choose a template synced from the configured WhatsApp Business Account.")
    return template_content({
        "id": template.meta_id, "name": template.template_name, "language": template.language,
        "category": template.category, "status": template.status,
        "parameter_format": template.parameter_format, "components": json.loads(template.components or "[]"),
    })


def routing():
    inbox = {
        "chatwoot_base_url": str(frappe.conf.get("chatwoot_base_url") or "").rstrip("/"),
        "chatwoot_account_id": str(frappe.conf.get("chatwoot_account_id") or ""),
        "chatwoot_inbox_id": str(frappe.conf.get("chatwoot_inbox_id") or ""),
    }
    if not all(inbox.values()):
        frappe.throw("Configure the Chatwoot URL, account ID and inbox ID before reviewing a campaign.")
    return inbox


def render_body(template, parameters):
    body = templates.PLACEHOLDER.sub(lambda match: parameters[match.group(1)], template["body"])
    return "\n\n".join(part for part in (template.get("header"), body, template["footer"]) if part)


def eligible_phone(customer, category):
    if customer.disabled:
        return None, "Customer is disabled."
    if not customer.get(CONSENT_FIELDS[category]):
        return None, "Customer has no consent for this campaign category."
    for candidate in api._get_customer_mobile_candidates(customer.name):
        phone = api._normalize_phone(candidate)
        if phone and re.fullmatch(r"[1-9][0-9]{7,14}", phone):
            return phone, None
    return None, "No valid customer mobile number."


def image_digest(doc, template):
    if not template["image"]:
        if doc.campaign_image:
            frappe.throw("Select an image-header template to send an image.")
        return None
    _, _, content = templates.image_file(doc.campaign_image, CAMPAIGN, doc.name)
    return hashlib.sha256(content).hexdigest()


@frappe.whitelist(methods=["POST"])
def preview(name):
    doc = get_campaign(name, lock=True)
    if doc.status != "Draft" or not doc.template:
        frappe.throw("Save a campaign draft and select an approved template.")
    if not 0 < len(doc.recipients) <= MAX_RECIPIENTS:
        frappe.throw(f"Add between 1 and {MAX_RECIPIENTS} recipients.")
    template = cached_template(doc)
    values = (doc.variable_values or "").splitlines()
    values = [value.strip() for value in values]
    if len(values) != len(template["keys"]) or any(not value for value in values):
        frappe.throw("Enter one nonempty value per template placeholder.")
    inbox = routing()
    snapshot = {"template": template, "inbox": inbox, "image_digest": image_digest(doc, template)}
    phones = set()
    counts = {"ready": 0, "skipped": 0}
    for row in doc.recipients:
        customer = frappe.get_doc("Customer", row.customer)
        customer.check_permission("read")
        phone, detail = eligible_phone(customer, template["category"])
        parameters = {}
        for key, value in zip(template["keys"], values):
            if value in CUSTOMER_VARIABLES:
                value = str(customer.get(CUSTOMER_VARIABLES[value]) or "").strip()
            parameters[key] = value
        if not detail and not all(parameters.values()):
            detail = "A customer field for a template variable is empty."
        if not detail and phone in phones:
            detail = "Duplicate WhatsApp number."
        if not detail:
            phones.add(phone)
        counts["skipped" if detail else "ready"] += 1
        row.db_set({
            "phone": phone, "detail": detail, "status": "Skipped" if detail else "Ready",
            "parameters": json.dumps(parameters),
            "message_preview": render_body(template, parameters) if all(parameters.values()) else None,
        }, update_modified=False)
    doc.db_set({"snapshot": json.dumps(snapshot), "sender_inbox": inbox["chatwoot_inbox_id"]})
    return counts


def validated_snapshot(doc):
    if not doc.snapshot:
        frappe.throw("Review and preview the campaign first.")
    snapshot = json.loads(doc.snapshot)
    snapshot["template"].setdefault("header", "")
    inbox = routing()
    if snapshot["inbox"] != inbox:
        frappe.throw("The configured Chatwoot inbox has changed.")
    account, _, _ = templates.meta_config()
    if frappe.db.get_value(templates.TEMPLATE, doc.template, "waba_id") != account:
        frappe.throw("The configured WhatsApp Business Account has changed.")
    if get_live_template(snapshot["template"]) != snapshot["template"]:
        frappe.throw("The Meta template changed. Review an updated draft.")
    if image_digest(doc, snapshot["template"]) != snapshot["image_digest"]:
        frappe.throw("The campaign image changed. Review an updated draft.")
    return snapshot


def pilot_phone():
    if not frappe.conf.get("snrg_whatsapp_disable_sending") or os.environ.get("SNRG_WHATSAPP_INTERNAL_PILOT") != "1":
        return None
    phone = api._normalize_phone(frappe.conf.get("snrg_whatsapp_internal_pilot_number"))
    return phone if phone and re.fullmatch(r"[1-9][0-9]{7,14}", phone) else None


def campaign_sending_enabled():
    return bool(pilot_phone()) or (
        not frappe.conf.get("snrg_whatsapp_disable_sending")
        and bool(cint(frappe.conf.get("snrg_whatsapp_campaigns_enabled")))
    )


def require_campaign_sending(phone=None):
    allowed = pilot_phone()
    if not campaign_sending_enabled():
        frappe.throw("WhatsApp campaign sending is disabled on this site.")
    if not allowed:
        api._require_whatsapp_sending_enabled()
    elif phone is not None and phone != allowed:
        frappe.throw("Staging pilot blocked a recipient outside the approved internal number.")


def campaign_send_config():
    require_campaign_sending()
    return api._get_chatwoot_config()


def restrict_reviewed_recipients(doc):
    if pilot_phone():
        for row in doc.recipients:
            if row.status == "Ready":
                require_campaign_sending(row.phone or "")


def upload_campaign_image(doc, config):
    require_campaign_sending()
    filename, mime, content = templates.image_file(doc.campaign_image, CAMPAIGN, doc.name)
    uploaded = api._upload_file_bytes_to_chatwoot(config, content, filename, content_type=mime)
    url = uploaded.get("file_url") or ""
    if not url.startswith("https://"):
        frappe.throw("Chatwoot did not return an HTTPS image URL.")
    return url


def send_message(config, template, phone, contact_name, parameters, media_url):
    require_campaign_sending(phone or "")
    contact = api._find_or_create_chatwoot_contact(config, recipient=phone, display_name=contact_name)
    if pilot_phone() and api._normalize_phone(contact.get("phone_number")) != phone:
        frappe.throw("The Chatwoot contact does not match the approved internal number.")
    conversation = api._find_or_create_chatwoot_conversation(config, contact)
    if pilot_phone():
        sender = (conversation.get("meta") or {}).get("sender") or {}
        if (str(conversation.get("inbox_id")) != str(config["chatwoot_inbox_id"])
                or str(sender.get("id")) != str(contact["id"])
                or api._normalize_phone(sender.get("phone_number")) != phone):
            frappe.throw("Chatwoot did not confirm the approved recipient and inbox.")
    conversation_id = conversation.get("id") or conversation.get("display_id")
    if not conversation_id:
        frappe.throw("Chatwoot did not return a conversation ID.")
    processed = {"body": parameters}
    if media_url:
        processed["header"] = {"media_url": media_url, "media_type": "image"}
    response = requests.post(
        api._chatwoot_url(config, f"conversations/{conversation_id}/messages"),
        headers=api._chatwoot_headers(config), timeout=api.REQUEST_TIMEOUT, json={
            "content": render_body(template, parameters), "message_type": "outgoing",
            "content_type": "text", "private": False,
            "template_params": {
                "name": template["name"], "language": template["language"],
                "category": template["category"], "processed_params": processed,
            },
        },
    )
    if response.status_code in {400, 401, 403, 404, 422, 429}:
        return "Failed", f"Chatwoot rejected the send (HTTP {response.status_code}).", conversation_id, None
    if not response.ok:
        return "Unconfirmed", f"Chatwoot returned HTTP {response.status_code}.", conversation_id, None
    message = response.json()
    if not isinstance(message, dict) or not message.get("id"):
        return "Unconfirmed", "Chatwoot did not confirm a message ID.", conversation_id, None
    status = DELIVERY_STATES.get(message.get("status"), "Accepted")
    detail = "Chatwoot reported a provider failure." if status == "Failed" else None
    return status, detail, conversation_id, message["id"]


@frappe.whitelist(methods=["POST"])
def send_test(name):
    require_campaign_sending()
    doc = get_campaign(name, lock=True)
    if doc.status != "Draft":
        frappe.throw("Test sends are available on reviewed drafts.")
    phone = api._normalize_phone(frappe.conf.get("snrg_whatsapp_test_number"))
    if not phone or not re.fullmatch(r"[1-9][0-9]{7,14}", phone):
        frappe.throw("Configure an internal WhatsApp test number in site config.")
    require_campaign_sending(phone)
    config = campaign_send_config()
    snapshot = validated_snapshot(doc)
    row = next((row for row in doc.recipients if row.status == "Ready"), None)
    if not row:
        frappe.throw("Preview at least one eligible recipient.")
    media_url = upload_campaign_image(doc, config) if snapshot["template"]["image"] else None
    # Use placeholder examples in the internal message to avoid copying live customer data.
    parameters = {key: f"Sample {key}" for key in snapshot["template"]["keys"]}
    status, detail, _, _ = send_message(config, snapshot["template"], phone, "Internal test", parameters, media_url)
    return {"status": status, "detail": detail}


def parse_schedule(value):
    if not re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", value):
        frappe.throw("Enter the schedule as YYYY-MM-DD HH:MM in the ERPNext site timezone.")
    try:
        scheduled = get_datetime(value)
    except ValueError:
        frappe.throw("Enter a valid date and time.")
    if scheduled <= now_datetime():
        frappe.throw("Choose a future send time.")
    return scheduled


@frappe.whitelist(methods=["POST"])
def launch(name, scheduled_at=None):
    require_campaign_sending()
    doc = get_campaign(name, lock=True)
    if doc.status not in {"Draft", "Scheduled"} or (doc.status == "Scheduled" and not scheduled_at):
        frappe.throw("Choose a draft campaign or reschedule a scheduled campaign.")
    if not any(row.status == "Ready" for row in doc.recipients):
        frappe.throw("Preview at least one eligible recipient.")
    restrict_reviewed_recipients(doc)
    scheduled = parse_schedule(scheduled_at) if scheduled_at else None
    validated_snapshot(doc)
    status = "Scheduled" if scheduled else "Queued"
    doc.db_set({
        "status": status, "scheduled_at": scheduled, "schedule_timezone": get_system_timezone(),
        "launched_by": frappe.session.user, "status_detail": None,
    })
    return status


@frappe.whitelist(methods=["POST"])
def change_campaign_status(name, action):
    doc = get_campaign(name, lock=True)
    allowed = {
        "cancel": ({"Scheduled", "Queued", "Paused"}, "Cancelled"),
        "pause": ({"Queued", "Sending"}, "Paused"),
        "resume": ({"Paused"}, "Queued"),
    }
    if action not in allowed or doc.status not in allowed[action][0]:
        frappe.throw("This action is unavailable for the current campaign status.")
    if action == "resume":
        require_campaign_sending()
        restrict_reviewed_recipients(doc)
        validated_snapshot(doc)
        doc.media_url = None
        doc.schedule_timezone = get_system_timezone()
    if action == "cancel":
        for row in doc.recipients:
            if row.status == "Ready":
                row.db_set({"status": "Skipped", "detail": "Campaign cancelled."}, update_modified=False)
    doc.db_set({"status": allowed[action][1], "status_detail": None, "media_url": doc.media_url,
                "schedule_timezone": doc.schedule_timezone})


def next_campaign():
    names = frappe.get_all(CAMPAIGN, filters={"status": ["in", ["Queued", "Sending"]]},
                           order_by="modified asc", pluck="name", limit=1)
    if not names:
        names = frappe.get_all(CAMPAIGN, filters={"status": "Scheduled", "scheduled_at": ["<=", now_datetime()]},
                               order_by="scheduled_at asc", pluck="name", limit=1)
    return names[0] if names else None


def enqueue_campaign_queue():
    if campaign_sending_enabled() and not pilot_phone() and next_campaign():
        frappe.enqueue(run_campaign_queue, queue="long", timeout=600)


def run_campaign_queue():
    if not campaign_sending_enabled():
        return
    lock = frappe.cache().lock(f"{frappe.local.site}:snrg_whatsapp_campaign_worker", timeout=900, blocking_timeout=0)
    if not lock.acquire():
        return
    try:
        name = next_campaign()
        if name:
            process_batch(name)
    finally:
        lock.release()


def process_batch(name):
    if not campaign_sending_enabled():
        return
    doc = frappe.get_doc(CAMPAIGN, name, for_update=True)
    if doc.status not in {"Queued", "Sending", "Scheduled"}:
        return
    if doc.status == "Scheduled" and get_datetime(doc.scheduled_at) > now_datetime():
        return
    if doc.schedule_timezone and doc.schedule_timezone != get_system_timezone():
        doc.db_set({"status": "Paused", "status_detail": "ERPNext site timezone changed."}, commit=True)
        return
    # Only the queue worker claims recipients. A persisted claim from a previous job is ambiguous.
    for row in doc.recipients:
        if row.status == "Sending":
            row.db_set({"status": "Unconfirmed", "detail": "Worker stopped before recording the outcome."})
    try:
        config = campaign_send_config()
        restrict_reviewed_recipients(doc)
        snapshot = validated_snapshot(doc)
        if snapshot["template"]["image"] and not doc.media_url:
            doc.media_url = upload_campaign_image(doc, config)
    except Exception:
        doc.db_set({"status": "Paused", "status_detail":
                    "Template, sender or media validation failed. Check configuration before resuming."}, commit=True)
        return
    doc.db_set({"status": "Sending", "started_at": doc.started_at or now_datetime(),
                "media_url": doc.media_url}, commit=True)
    batch_size = max(1, min(10, cint(frappe.conf.get("snrg_whatsapp_campaign_batch_size")) or 3))
    sent = 0
    for row in doc.recipients:
        if row.status != "Ready":
            continue
        state = frappe.db.get_value(CAMPAIGN, doc.name, "status", for_update=True)
        if state != "Sending":
            frappe.db.rollback()
            return
        if not frappe.db.exists("Customer", row.customer):
            row.db_set({"status": "Skipped", "detail": "Customer no longer exists."}, commit=True)
            continue
        customer = frappe.get_doc("Customer", row.customer)
        phone, reason = eligible_phone(customer, snapshot["template"]["category"])
        if reason or phone != row.phone:
            row.db_set({"status": "Skipped", "detail": reason or "Recipient number changed after review."}, commit=True)
            continue
        row.db_set({"status": "Sending", "attempted_at": now_datetime()}, commit=True)
        try:
            status, detail, conversation, message = send_message(
                config, snapshot["template"], phone, customer.customer_name,
                json.loads(row.parameters), doc.media_url,
            )
        except Exception:
            status, detail, conversation, message = (
                "Unconfirmed", "Could not confirm the Chatwoot send. Check the conversation before retrying.", None, None
            )
        row.db_set({"status": status, "detail": detail, "conversation_id": conversation,
                    "message_id": message}, commit=True)
        sent += 1
        if status in {"Failed", "Unconfirmed"}:
            if frappe.db.get_value(CAMPAIGN, doc.name, "status", for_update=True) == "Sending":
                doc.db_set({"status": "Paused", "status_detail": "Review the last recipient outcome before resuming."})
            frappe.db.commit()
            return
        if sent >= batch_size:
            break
    state = frappe.db.get_value(CAMPAIGN, doc.name, "status", for_update=True)
    if state == "Sending" and not frappe.db.exists(RECIPIENT, {"parent": doc.name, "status": "Ready"}):
        doc.db_set("status", "Completed")
    frappe.db.commit()


@frappe.whitelist(methods=["POST"])
def refresh_delivery(name):
    doc = get_campaign(name)
    config = api._get_chatwoot_config()
    inbox = routing()
    if not doc.snapshot or json.loads(doc.snapshot)["inbox"] != inbox:
        frappe.throw("This campaign uses a different Chatwoot inbox.")
    updated = 0
    conversations = {}
    for row in doc.recipients:
        if row.status not in {"Accepted", "Sent", "Delivered"} or not row.message_id or not row.conversation_id:
            continue
        if row.conversation_id not in conversations:
            conversations[row.conversation_id] = api._fetch_chatwoot_conversation_messages(config, row.conversation_id)
        message = next((item for item in conversations[row.conversation_id]
                        if str(item.get("id")) == row.message_id), None)
        status = DELIVERY_STATES.get(message.get("status")) if message else None
        allowed = {
            "Accepted": {"Sent", "Delivered", "Read", "Failed"},
            "Sent": {"Delivered", "Read", "Failed"},
            "Delivered": {"Read"},
        }
        if status in allowed[row.status]:
            row.db_set({"status": status, "detail": "Chatwoot reported a provider failure." if status == "Failed" else None})
            updated += 1
    return updated
