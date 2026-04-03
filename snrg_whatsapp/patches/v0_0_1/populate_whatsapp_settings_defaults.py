import frappe


DEFAULTS = {
    "enable_quotation_whatsapp_on_submit": 1,
    "whatsapp_quotation_template_name": "sales_quotation_confirmation",
    "whatsapp_quotation_template_language": "en_US",
    "whatsapp_quotation_print_format": "Quotation",
    "enable_sales_invoice_whatsapp_on_submit": 1,
    "whatsapp_sales_invoice_template_name": "sales_invoice_erpnext",
    "whatsapp_sales_invoice_template_language": "en",
    "whatsapp_sales_invoice_print_format": "Sales Invoice New",
    "whatsapp_credit_note_template_name": "credit_note_erpnext",
    "whatsapp_credit_note_template_language": "en",
    "whatsapp_credit_note_print_format": "Credit Note New",
    "whatsapp_report_template_name": "customer_ledger_statement",
    "whatsapp_report_template_language": "en",
    "enable_payment_entry_whatsapp_on_submit": 1,
    "whatsapp_payment_entry_template_name": "payment_entry_erpnext",
    "whatsapp_payment_entry_template_language": "en",
    "whatsapp_payment_pay_template_name": "payment_pay_erpnext",
    "whatsapp_payment_pay_template_language": "en",
    "whatsapp_payment_entry_print_format": "Payment Entry",
}


def execute():
    if not frappe.db.exists("DocType", "SNRG WhatsApp Settings"):
        return

    for fieldname, value in DEFAULTS.items():
        current = frappe.db.get_single_value("SNRG WhatsApp Settings", fieldname)
        if current in (None, ""):
            frappe.db.set_single_value("SNRG WhatsApp Settings", fieldname, value)

