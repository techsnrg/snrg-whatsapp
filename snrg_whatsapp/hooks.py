app_name = "snrg_whatsapp"
app_title = "SNRG WhatsApp"
app_publisher = "SNRG"
app_description = "WhatsApp automations for ERPNext using Chatwoot"
app_email = "hello@aerele.in"
app_license = "mit"

app_include_js = "/assets/snrg_whatsapp/js/snrg_whatsapp_ui.js"

doctype_js = {
    "Quotation": "public/js/document_whatsapp.js",
    "Sales Invoice": "public/js/document_whatsapp.js",
}

doc_events = {
    "Quotation": {
        "on_submit": "snrg_whatsapp.api.enqueue_sales_quotation_whatsapp",
    },
    "Sales Invoice": {
        "on_submit": "snrg_whatsapp.api.enqueue_sales_invoice_whatsapp",
    },
    "Payment Entry": {
        "on_submit": "snrg_whatsapp.api.enqueue_payment_entry_whatsapp",
    },
}

scheduler_events = {
    "cron": {
        "*/30 * * * *": [
            "snrg_whatsapp.api.enqueue_pending_customer_confirmation_sync",
        ],
        "0 10 * * 1": [
            "snrg_whatsapp.api.enqueue_cash_discount_weekly_reminders",
        ],
        "0 10 * * *": [
            "snrg_whatsapp.api.enqueue_cash_discount_daily_alerts",
        ],
    }
}
