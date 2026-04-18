import frappe


DEBUG_FIELDS = (
    "customer_confirmation_payload",
    "customer_confirmation_token",
    "customer_confirmation_outbound_message_id",
    "customer_confirmation_outbound_external_id",
    "customer_confirmation_outbound_conversation_id",
    "customer_confirmation_outbound_contact",
)


def execute():
    if not frappe.db.exists("DocType", "Quotation"):
        return

    changed = False
    for fieldname in DEBUG_FIELDS:
        custom_field_name = f"Quotation-{fieldname}"
        if not frappe.db.exists("Custom Field", custom_field_name):
            continue

        custom_field = frappe.get_doc("Custom Field", custom_field_name)
        if custom_field.hidden != 1:
            custom_field.hidden = 1
            custom_field.save(ignore_permissions=True)
            changed = True

    if changed:
        frappe.clear_cache(doctype="Quotation")
