# SNRG WhatsApp

Headless Frappe app for ERPNext-to-WhatsApp automations using Chatwoot's WhatsApp inbox.

Initial feature:
- Send approved WhatsApp quotation template with Quotation PDF when a Quotation is submitted.
- Send approved WhatsApp invoice template with Sales Invoice PDF when a Sales Invoice is submitted.
- Send approved WhatsApp receipt template with Payment Entry PDF when a customer Payment Entry is submitted.

## Site Config

Add these keys to `site_config.json` for the ERPNext site:

```json
{
  "chatwoot_base_url": "https://chatwoot.example.com",
  "chatwoot_account_id": 1,
  "chatwoot_api_access_token": "YOUR_CHATWOOT_USER_API_TOKEN",
  "chatwoot_inbox_id": 12,
  "enable_quotation_whatsapp_on_submit": 1,
  "enable_sales_invoice_whatsapp_on_submit": 1,
  "enable_payment_entry_whatsapp_on_submit": 1,
  "whatsapp_quotation_template_name": "sales_quotation_confirmation",
  "whatsapp_quotation_template_language": "en_US",
  "whatsapp_quotation_print_format": "Quotation",
  "whatsapp_sales_invoice_template_name": "sales_invoice_erpnext",
  "whatsapp_sales_invoice_template_language": "en",
  "whatsapp_sales_invoice_print_format": "Sales Invoice New",
  "whatsapp_payment_entry_template_name": "payment_entry_erpnext",
  "whatsapp_payment_entry_template_language": "en",
  "whatsapp_payment_entry_print_format": "Payment Receipt"
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
- Configure a Chatwoot webhook to `POST` inbound message events to `/api/method/snrg_whatsapp.api.handle_chatwoot_confirmation_webhook`.
- Add the Chatwoot webhook secret in `SNRG WhatsApp Settings` on Desk. `site_config.json` still works as a fallback for existing setups.
- The Quotation, Sales Invoice, and Payment Entry submit hooks queue WhatsApp sends in the background.
- ERPNext sends through Chatwoot, so outgoing messages appear in the Chatwoot conversation thread.
- Mobile lookup prefers document-level contact mobile, then customer mobile, then contact mobile. Payment Entry can also fall back to linked Sales Invoice contact details.
- Quotation sends now persist outbound Chatwoot message and conversation ids so inbound customer confirmations can be matched back safely.
- The Quotation form includes a manual customer-confirmation override action for privileged users and stores an audit comment.
- This app is intentionally backend-only and does not add a Desk module or frontend UI.
- Successful sends are marked on the document timeline to prevent duplicate sends on repeat execution.
- Customer Payment Entry sends only run for `party_type = Customer`; supplier payments are skipped.
- Set each `enable_*_whatsapp_on_submit` flag to `0` on production if you want the app installed before enabling a given automation.
