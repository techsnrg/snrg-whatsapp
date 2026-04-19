import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


CUSTOM_FIELDS = {
    "Customer": [
        {
            "fieldname": "snrg_whatsapp_reminders_section",
            "fieldtype": "Section Break",
            "label": "WhatsApp Reminders",
        },
        {
            "fieldname": "enable_whatsapp_cash_discount_reminders",
            "fieldtype": "Check",
            "label": "Enable WhatsApp Cash Discount Reminders",
            "insert_after": "snrg_whatsapp_reminders_section",
            "default": "0",
        },
        {
            "fieldname": "last_cash_discount_weekly_message_on",
            "fieldtype": "Date",
            "label": "Last Cash Discount Weekly Message On",
            "insert_after": "enable_whatsapp_cash_discount_reminders",
            "hidden": 1,
            "read_only": 1,
        },
        {
            "fieldname": "last_cash_discount_weekly_message_type",
            "fieldtype": "Select",
            "label": "Last Cash Discount Weekly Message Type",
            "options": "\nsummary\nblocked",
            "insert_after": "last_cash_discount_weekly_message_on",
            "hidden": 1,
            "read_only": 1,
        },
    ],
    "Sales Invoice": [
        {
            "fieldname": "last_cash_discount_alert_on",
            "fieldtype": "Date",
            "label": "Last Cash Discount Alert On",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
        {
            "fieldname": "last_cash_discount_alert_boundary_day",
            "fieldtype": "Int",
            "label": "Last Cash Discount Alert Boundary Day",
            "insert_after": "last_cash_discount_alert_on",
            "hidden": 1,
            "read_only": 1,
            "allow_on_submit": 1,
        },
    ],
}


def execute():
    for doctype in CUSTOM_FIELDS:
        if not frappe.db.exists("DocType", doctype):
            return

    create_custom_fields(CUSTOM_FIELDS, update=True)
