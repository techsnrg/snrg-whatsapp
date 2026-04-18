import frappe


FIELD_SEQUENCE = [
    ("customer_confirmation_tab", "more_info_tab"),
    ("snrg_customer_confirmation_section", "customer_confirmation_tab"),
    ("customer_confirmation_status", "snrg_customer_confirmation_section"),
    ("customer_confirmation_datetime", "customer_confirmation_status"),
    ("customer_confirmation_source", "customer_confirmation_datetime"),
    ("customer_confirmation_message_id", "customer_confirmation_source"),
    ("customer_confirmation_conversation_id", "customer_confirmation_message_id"),
    ("customer_confirmation_contact", "customer_confirmation_conversation_id"),
    ("customer_confirmation_notes", "customer_confirmation_contact"),
    ("customer_confirmation_payload", "customer_confirmation_notes"),
    ("customer_confirmation_token", "customer_confirmation_payload"),
    ("customer_confirmation_outbound_message_id", "customer_confirmation_token"),
    ("customer_confirmation_outbound_external_id", "customer_confirmation_outbound_message_id"),
    ("customer_confirmation_outbound_conversation_id", "customer_confirmation_outbound_external_id"),
    ("customer_confirmation_outbound_contact", "customer_confirmation_outbound_conversation_id"),
]


def execute():
    if not frappe.db.exists("DocType", "Quotation"):
        return

    for fieldname, insert_after in FIELD_SEQUENCE:
        custom_field_name = f"Quotation-{fieldname}"
        if not frappe.db.exists("Custom Field", custom_field_name):
            continue

        custom_field = frappe.get_doc("Custom Field", custom_field_name)
        custom_field.insert_after = insert_after
        custom_field.hidden = 1 if fieldname in {
            "customer_confirmation_payload",
            "customer_confirmation_token",
            "customer_confirmation_outbound_message_id",
            "customer_confirmation_outbound_external_id",
            "customer_confirmation_outbound_conversation_id",
            "customer_confirmation_outbound_contact",
        } else 0
        custom_field.allow_on_submit = 1
        custom_field.save(ignore_permissions=True)

    frappe.clear_cache(doctype="Quotation")
