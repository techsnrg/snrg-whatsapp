# SNRG WhatsApp

Headless Frappe app for ERPNext-to-WhatsApp automations using Chatwoot's WhatsApp inbox.

Initial feature:
- Send approved WhatsApp quotation template with Quotation PDF when a Quotation is submitted.
- Send approved WhatsApp invoice template with Sales Invoice PDF when a Sales Invoice is submitted.
- Send approved WhatsApp receipt template with Payment Entry PDF when a customer Payment Entry is submitted.
- Send WhatsApp cash-discount reminders using the active CD Scheme for opted-in customers.

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
- Pending Quotation confirmations are also re-synced from Chatwoot every 30 minutes in small background batches, so older pending replies can be picked up without opening the form.
- ERPNext sends through Chatwoot, so outgoing messages appear in the Chatwoot conversation thread.
- Mobile lookup prefers document-level contact mobile, then customer mobile, then contact mobile. Payment Entry can also fall back to linked Sales Invoice contact details.
- Quotation sends now persist outbound Chatwoot message and conversation ids so inbound customer confirmations can be matched back safely.
- The Quotation form includes both a manual customer-confirmation override and a `Sync from Chatwoot` fallback action for privileged users, and stores an audit comment.
- This app is intentionally backend-only and does not add a Desk module or frontend UI.
- Successful sends are marked on the document timeline to prevent duplicate sends on repeat execution.
- Customer Payment Entry sends only run for `party_type = Customer`; supplier payments are skipped.
- Set each `enable_*_whatsapp_on_submit` flag to `0` on production if you want the app installed before enabling a given automation.

## Cash Discount Reminders

- Enable reminders per customer from the `Enable WhatsApp Cash Discount Reminders` checkbox on `Customer`.
- Enable the automation globally and configure template names from `SNRG WhatsApp Settings`.
- The scheduler sends:
  - a Monday weekly summary or blocked-status message per opted-in customer
  - a daily invoice alert during the final 3 days before the current CD slab drops
- The active `CD Scheme` is treated as global. The reminder engine reads its valid dates, active flag, slabs, and eligible item groups directly.
- If any unpaid invoice for the customer is older than 45 days from `posting_date`, across any company, the customer is blocked from normal CD reminders until the old overdue invoice is cleared.

Recommended WhatsApp body placeholders:

- `cash_discount_weekly_summary`
  - `1` customer name
  - `2` total outstanding
  - `3` total current CD amount
  - `4` eligible invoice count
  - `5` nearest slab drop date
  - `6-9` invoice 1: invoice no, outstanding, CD amount, days left
  - `10-13` invoice 2: invoice no, outstanding, CD amount, days left
  - `14-17` invoice 3: invoice no, outstanding, CD amount, days left
  - `18` overflow note like `+N more invoices`
- `cash_discount_blocked_notice`
  - `1` customer name
  - `2` overdue invoice count above 45 days
  - `3` overdue amount above 45 days
  - `4` oldest overdue age in days
- `cash_discount_slab_drop_alert`
  - `1` customer name
  - `2` invoice number
  - `3` outstanding amount
  - `4` current CD amount
  - `5` current CD %
  - `6` slab drop date
