# SNRG WhatsApp

Headless Frappe app for ERPNext-to-WhatsApp automations using Meta Cloud API.

Initial feature:
- Send approved WhatsApp quotation template with Quotation PDF when a Quotation is submitted.

## Site Config

Add these keys to `site_config.json` for the ERPNext site:

```json
{
  "whatsapp_cloud_access_token": "YOUR_META_ACCESS_TOKEN",
  "whatsapp_cloud_phone_number_id": "1048226118374784",
  "whatsapp_cloud_api_version": "v25.0",
  "enable_quotation_whatsapp_on_submit": 1,
  "whatsapp_quotation_template_name": "sales_quotation_confirmation",
  "whatsapp_quotation_template_language": "en_US",
  "whatsapp_quotation_print_format": "Quotation"
}
```

## Install

Create or copy this app into your bench `apps` directory, install it on the site, then run:

```bash
bench --site your-site migrate
bench --site your-site clear-cache
bench restart
```

## Notes

- The approved WhatsApp template must include a `document` header.
- The Quotation submit hook queues the WhatsApp send in the background.
- Mobile lookup currently prefers `Quotation.contact_mobile`, then `Customer.mobile_no`, then `Contact.mobile_no`.
- This app is intentionally backend-only and does not add a Desk module or frontend UI.
- Successful sends are marked on the quotation timeline to prevent duplicate sends on repeat execution.
- Set `enable_quotation_whatsapp_on_submit` to `0` on production if you want the app installed before enabling automation.
