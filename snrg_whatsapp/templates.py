import json
import mimetypes
import re

import frappe
import requests
from frappe.utils import now_datetime

TEMPLATE = "SNRG WhatsApp Template"
PLACEHOLDER = re.compile(r"{{\s*([1-9][0-9]*)\s*}}")
LOCALE = re.compile(r"[a-z]{2,3}(?:_[A-Z]{2})?")
IMAGE_TYPES = {"image/jpeg", "image/png"}


class MetaRequestRejected(frappe.ValidationError):
    pass


def meta_config():
    account = str(frappe.conf.get("snrg_whatsapp_waba_id") or "")
    version = str(frappe.conf.get("snrg_whatsapp_graph_version") or "")
    token = frappe.conf.get("snrg_whatsapp_meta_token")
    if not account.isdigit() or not re.fullmatch(r"v\d+\.\d+", version) or not token:
        frappe.throw("Configure the WhatsApp Business Account ID, Graph API version and Meta token.")
    return account, version, token


def graph_request(method, path, *, params=None, payload=None, data=None, headers=None):
    _, version, token = meta_config()
    authorization = {"Authorization": f"Bearer {token}"}
    authorization.update(headers or {})
    proxy = frappe.conf.get("snrg_whatsapp_graph_proxy")
    try:
        response = requests.request(
            method, f"https://graph.facebook.com/{version}/{path}",
            headers=authorization, params=params, json=payload, data=data,
            timeout=20, allow_redirects=False, proxies={"https": proxy} if proxy else None,
        )
        result = response.json()
    except (requests.RequestException, ValueError):
        frappe.throw("Meta did not return a usable response. Refresh templates to reconcile any submission.")
    if not response.ok or not isinstance(result, dict) or result.get("error"):
        error = result.get("error", {}) if isinstance(result, dict) else {}
        detail = error.get("error_user_msg") or error.get("message") or f"HTTP {response.status_code}"
        message = "Meta request failed. " + str(detail).replace(token, "[redacted]")
        if 400 <= response.status_code < 500 and isinstance(error, dict) and error.get("code"):
            frappe.throw(message, exc=MetaRequestRejected)
        frappe.throw(message)
    return result


def positional_keys(body):
    keys = sorted({int(match) for match in PLACEHOLDER.findall(body)})
    remainder = PLACEHOLDER.sub("", body)
    if "{{" in remainder or "}}" in remainder or any(
        key != index for index, key in enumerate(keys, 1)
    ):
        frappe.throw("Use consecutive numbered placeholders such as {{1}} and {{2}}.")
    return [str(key) for key in keys]


def image_file(url, doctype, name):
    file_name = frappe.db.get_value(
        "File", {"file_url": url, "attached_to_doctype": doctype, "attached_to_name": name}, "name"
    ) if url else None
    if not file_name:
        frappe.throw("Upload an image directly to this record.")
    file = frappe.get_doc("File", file_name)
    mime = mimetypes.guess_type(file.file_name)[0]
    if mime not in IMAGE_TYPES or not 0 < int(file.file_size or 0) <= 5 * 1024 * 1024:
        frappe.throw("Upload a JPEG or PNG image up to 5 MB.")
    content = file.get_content()
    signature = b"\xff\xd8\xff" if mime == "image/jpeg" else b"\x89PNG\r\n\x1a\n"
    if not isinstance(content, bytes) or not content.startswith(signature) or len(content) > 5 * 1024 * 1024:
        frappe.throw("The uploaded image is invalid or exceeds 5 MB.")
    return file.file_name, mime, content


def upload_review_image(doc):
    filename, mime, content = image_file(doc.sample_image, doc.doctype, doc.name)
    app = str(frappe.conf.get("snrg_whatsapp_meta_app_id") or "")
    if not app.isdigit():
        frappe.throw("Configure the Meta app ID to submit image-header templates.")
    session = graph_request("POST", f"{app}/uploads", params={
        "file_name": filename, "file_length": len(content), "file_type": mime,
    })
    session_id = session.get("id") or ""
    if not re.fullmatch(r"upload:[A-Za-z0-9_+/%=-]+(?:\?sig=[A-Za-z0-9_%-]+)?", session_id):
        frappe.throw("Meta did not return an upload session.")
    _, _, token = meta_config()
    upload = graph_request("POST", session_id, data=content, headers={
        "Authorization": f"OAuth {token}", "file_offset": "0", "Content-Type": "application/octet-stream",
    })
    if not upload.get("h"):
        frappe.throw("Meta did not return an image handle.")
    return upload["h"]


@frappe.whitelist(methods=["POST"])
def submit_template(name):
    frappe.only_for("System Manager")
    account, _, _ = meta_config()
    with frappe.cache().lock(f"{frappe.local.site}:snrg_whatsapp_template_sync", timeout=120, blocking_timeout=1):
        doc = frappe.get_doc(TEMPLATE, name, for_update=True)
        doc.check_permission("write")
        if doc.status != "Draft":
            frappe.throw("Select a draft template.")
        if not re.fullmatch(r"[a-z0-9_]+", doc.template_name) or not LOCALE.fullmatch(doc.language):
            frappe.throw("Use a lowercase template name with underscores and a valid language code.")
        if doc.category not in {"MARKETING", "UTILITY"}:
            frappe.throw("Draft creation supports Utility and Marketing templates.")
        keys = positional_keys(doc.body)
        examples = (doc.sample_values or "").splitlines()
        if len(keys) != len(examples) or any(not value.strip() for value in examples):
            frappe.throw("Enter one nonempty sample value per body placeholder.")
        body = {"type": "BODY", "text": doc.body}
        if keys:
            body["example"] = {"body_text": [examples]}
        components = [body]
        if doc.header_format == "Image":
            components.insert(0, {"type": "HEADER", "format": "IMAGE",
                                  "example": {"header_handle": [upload_review_image(doc)]}})
        doc.db_set({"status": "Submitting", "waba_id": account}, commit=True)
        try:
            result = graph_request("POST", f"{account}/message_templates", payload={
                "name": doc.template_name, "language": doc.language,
                "category": doc.category, "components": components,
            })
            if not result.get("id"):
                frappe.throw("Meta did not return a template ID.")
        except MetaRequestRejected as exc:
            doc.db_set({"status": "Draft", "status_details": str(exc)}, commit=True)
            raise
        except Exception:
            doc.db_set({"status": "Submission Unconfirmed", "status_details":
                        "Refresh Templates to reconcile the submission before creating another draft."}, commit=True)
            raise
        doc.db_set({
            "meta_id": str(result["id"]), "status": result.get("status") or "PENDING",
            "category": result.get("category") or doc.category,
            "components": json.dumps(components), "last_sync": now_datetime(),
        }, commit=True)


def iter_meta_templates(name=None):
    account, _, _ = meta_config()
    params = {"fields": "id,name,language,category,status,components,parameter_format", "limit": 100}
    if name:
        params["name"] = name
    seen = set()
    while True:
        result = graph_request("GET", f"{account}/message_templates", params=params)
        if not isinstance(result.get("data"), list):
            frappe.throw("Meta returned an invalid template list.")
        yield from result["data"]
        paging = result.get("paging") or {}
        if not paging.get("next"):
            return
        cursor = (paging.get("cursors") or {}).get("after")
        if not cursor or cursor in seen:
            frappe.throw("Meta template pagination did not complete.")
        seen.add(cursor)
        params["after"] = cursor


def sync_templates():
    if not frappe.conf.get("snrg_whatsapp_waba_id"):
        return 0
    account, _, _ = meta_config()
    with frappe.cache().lock(f"{frappe.local.site}:snrg_whatsapp_template_sync", timeout=300, blocking_timeout=1):
        found = set()
        for item in iter_meta_templates():
            meta_id = str(item["id"])
            found.add(meta_id)
            components = item.get("components") or []
            values = {
                "meta_id": meta_id, "waba_id": account,
                "template_name": item["name"], "language": item["language"],
                "category": item["category"], "status": item["status"], "last_sync": now_datetime(),
                "components": json.dumps(components), "parameter_format": item.get("parameter_format"),
                "body": next((part.get("text") for part in components if part.get("type") == "BODY"), None),
                "header_format": "Image" if any(part.get("format") == "IMAGE" for part in components) else "None",
                "status_details": None,
            }
            name = frappe.db.get_value(TEMPLATE, {"meta_id": meta_id})
            if not name:
                candidates = frappe.get_all(TEMPLATE, filters={
                    "waba_id": account, "template_name": item["name"], "language": item["language"],
                    "status": ["in", ["Submitting", "Submission Unconfirmed"]],
                }, pluck="name", limit=2)
                name = candidates[0] if len(candidates) == 1 else None
            if name:
                frappe.db.set_value(TEMPLATE, name, values)
            else:
                doc = frappe.get_doc({"doctype": TEMPLATE, **values})
                doc.flags.from_meta = True
                doc.insert(ignore_permissions=True, ignore_mandatory=True)
        for row in frappe.get_all(TEMPLATE, filters={"waba_id": account, "meta_id": ["is", "set"]},
                                  fields=["name", "meta_id", "status"]):
            if row.meta_id not in found and row.status != "Unavailable":
                frappe.db.set_value(TEMPLATE, row.name, "status", "Unavailable")
        frappe.db.commit()
    return len(found)


@frappe.whitelist(methods=["POST"])
def refresh_templates():
    frappe.only_for("System Manager")
    meta_config()
    return sync_templates()
