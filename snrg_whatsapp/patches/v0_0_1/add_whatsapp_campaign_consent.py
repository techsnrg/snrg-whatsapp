from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields(
        {"Customer": [
            {
                "fieldname": "snrg_whatsapp_campaign_opt_in",
                "fieldtype": "Check",
                "label": "Opted In to WhatsApp Utility Campaigns",
                "insert_after": "customer_name",
                "default": "0",
                "permlevel": 1,
            },
            {
                "fieldname": "snrg_whatsapp_marketing_opt_in",
                "fieldtype": "Check",
                "label": "Opted In to WhatsApp Marketing",
                "insert_after": "snrg_whatsapp_campaign_opt_in",
                "default": "0",
                "permlevel": 1,
            },
        ]},
        update=True,
    )
