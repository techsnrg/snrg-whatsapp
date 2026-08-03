import frappe


DEFAULTS = {
    "enable_quotation_whatsapp_on_cancel": 1,
    "whatsapp_quotation_cancellation_template_name": "sales_quotation_cancellation",
    "whatsapp_quotation_cancellation_template_language": "en_US",
}


def execute():
    if not frappe.db.exists("DocType", "SNRG WhatsApp Settings"):
        return

    frappe.reload_doc(
        "snrg_whatsapp",
        "doctype",
        "snrg_whatsapp_settings",
    )
    for fieldname, value in DEFAULTS.items():
        current = frappe.db.get_single_value("SNRG WhatsApp Settings", fieldname)
        if current in (None, ""):
            frappe.db.set_single_value("SNRG WhatsApp Settings", fieldname, value)
