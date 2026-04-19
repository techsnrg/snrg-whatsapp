import frappe


DEFAULTS = {
    "enable_cash_discount_whatsapp_reminders": 0,
    "whatsapp_cash_discount_summary_template_name": "cash_discount_weekly_summary",
    "whatsapp_cash_discount_summary_template_language": "en",
    "whatsapp_cash_discount_blocked_template_name": "cash_discount_blocked_notice",
    "whatsapp_cash_discount_blocked_template_language": "en",
    "whatsapp_cash_discount_alert_template_name": "cash_discount_slab_drop_alert",
    "whatsapp_cash_discount_alert_template_language": "en",
}


def execute():
    if not frappe.db.exists("DocType", "SNRG WhatsApp Settings"):
        return

    for fieldname, value in DEFAULTS.items():
        current = frappe.db.get_single_value("SNRG WhatsApp Settings", fieldname)
        if current in (None, ""):
            frappe.db.set_single_value("SNRG WhatsApp Settings", fieldname, value)
