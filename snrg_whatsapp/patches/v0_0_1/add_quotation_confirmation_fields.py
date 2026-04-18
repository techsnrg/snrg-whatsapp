import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
    "Quotation": [
        {
            "fieldname": "customer_confirmation_tab",
            "fieldtype": "Tab Break",
            "label": "Customer Confirmation",
            "insert_after": "more_info_tab",
        },
        {
            "fieldname": "snrg_customer_confirmation_section",
            "fieldtype": "Section Break",
            "label": "Customer Confirmation",
            "insert_after": "customer_confirmation_tab",
        },
        {
            "fieldname": "customer_confirmation_status",
            "fieldtype": "Select",
            "label": "Customer Confirmation Status",
            "options": "\nPending\nConfirmed\nChanges Requested",
            "insert_after": "snrg_customer_confirmation_section",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_datetime",
            "fieldtype": "Datetime",
            "label": "Customer Confirmation Datetime",
            "insert_after": "customer_confirmation_status",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_source",
            "fieldtype": "Data",
            "label": "Customer Confirmation Source",
            "default": "WhatsApp",
            "insert_after": "customer_confirmation_datetime",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_message_id",
            "fieldtype": "Data",
            "label": "Customer Confirmation Message ID",
            "insert_after": "customer_confirmation_source",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_conversation_id",
            "fieldtype": "Data",
            "label": "Customer Confirmation Conversation ID",
            "insert_after": "customer_confirmation_message_id",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_contact",
            "fieldtype": "Data",
            "label": "Customer Confirmation Contact",
            "insert_after": "customer_confirmation_conversation_id",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_notes",
            "fieldtype": "Small Text",
            "label": "Customer Confirmation Notes",
            "insert_after": "customer_confirmation_contact",
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_payload",
            "fieldtype": "Long Text",
            "label": "Customer Confirmation Payload",
            "insert_after": "customer_confirmation_notes",
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_token",
            "fieldtype": "Data",
            "label": "Customer Confirmation Token",
            "insert_after": "customer_confirmation_payload",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_outbound_message_id",
            "fieldtype": "Data",
            "label": "Customer Confirmation Outbound Message ID",
            "insert_after": "customer_confirmation_token",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_outbound_external_id",
            "fieldtype": "Data",
            "label": "Customer Confirmation Outbound External ID",
            "insert_after": "customer_confirmation_outbound_message_id",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_outbound_conversation_id",
            "fieldtype": "Data",
            "label": "Customer Confirmation Outbound Conversation ID",
            "insert_after": "customer_confirmation_outbound_external_id",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "customer_confirmation_outbound_contact",
            "fieldtype": "Data",
            "label": "Customer Confirmation Outbound Contact",
            "insert_after": "customer_confirmation_outbound_conversation_id",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
    ]
}


def execute():
    if not frappe.db.exists("DocType", "Quotation"):
        return

    create_custom_fields(CUSTOM_FIELDS, update=True)
