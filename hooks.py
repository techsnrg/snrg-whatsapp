app_name = "snrg_whatsapp"
app_title = "SNRG WhatsApp"
app_publisher = "SNRG"
app_description = "WhatsApp automations for ERPNext using Chatwoot"
app_email = "hello@aerele.in"
app_license = "mit"


doc_events = {
    "Quotation": {
        "on_submit": "snrg_whatsapp.api.enqueue_sales_quotation_whatsapp",
    }
}
