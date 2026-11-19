app_name = "snrg_whatsapp"
app_title = "SNRG WhatsApp"
app_publisher = "SNRG"
app_description = "WhatsApp automations for ERPNext using Chatwoot"
app_email = "hello@aerele.in"
app_license = "mit"
required_apps = ["erpnext"]
after_install = "snrg_whatsapp.patches.v0_0_1.add_whatsapp_campaign_consent.execute"

app_include_js = "/assets/snrg_whatsapp/js/snrg_whatsapp_ui.js"

doctype_js = {
    "Quotation": "public/js/document_whatsapp.js",
    "Sales Invoice": "public/js/document_whatsapp.js",
}

doctype_list_js = {"Customer": "public/js/customer_whatsapp_campaign.js"}

doc_events = {
    "Quotation": {
        "on_submit": "snrg_whatsapp.api.enqueue_sales_quotation_whatsapp",
        "on_cancel": "snrg_whatsapp.api.enqueue_sales_quotation_cancellation_whatsapp",
    },
    "Sales Invoice": {
        "on_submit": "snrg_whatsapp.api.enqueue_sales_invoice_whatsapp",
    },
    "Payment Entry": {
        "on_submit": "snrg_whatsapp.api.enqueue_payment_entry_whatsapp",
    },
}

scheduler_events = {
    "all": ["snrg_whatsapp.campaigns.enqueue_campaign_queue"],
    "cron": {
        "*/30 * * * *": [
            "snrg_whatsapp.api.enqueue_pending_customer_confirmation_sync",
            "snrg_whatsapp.templates.sync_templates",
        ],
        "0 10 * * 1": [
            "snrg_whatsapp.api.enqueue_cash_discount_weekly_reminders",
        ],
        "0 10 * * *": [
            "snrg_whatsapp.api.enqueue_cash_discount_daily_alerts",
        ],
    }
}
