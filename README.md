# SNRG WhatsApp

Headless Frappe app for ERPNext-to-WhatsApp automations using Chatwoot's WhatsApp inbox.

## ERPNext Compatibility

This app is intended to run on both ERPNext/Frappe v15 and v16 from the same main branch.
The bench dependency compatibility metadata pins Frappe and ERPNext to `>=15.0.0,<17.0.0`.

Compatibility rules for future changes:

- Keep framework-specific differences behind helper functions in `snrg_whatsapp/api.py`.
- Treat custom ERPNext fields as optional unless this app creates them during migrate.
- Avoid importing optional companion apps, such as Customer Ledger, at module import time.
- Prefer stable document, hook, scheduler, and whitelisted-method APIs over direct framework internals.

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
  "enable_quotation_whatsapp_on_cancel": 1,
  "whatsapp_quotation_cancellation_template_name": "sales_quotation_cancellation",
  "whatsapp_quotation_cancellation_template_language": "en_US",
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

- Approved templates that send a PDF must include a `document` header.
- Quotation cancellation uses the body-only `sales_quotation_cancellation` utility template with variables: customer name, quotation number, and quotation date.
- Configure a Chatwoot webhook to `POST` inbound message events to `/api/method/snrg_whatsapp.api.handle_chatwoot_confirmation_webhook`.
- Add the Chatwoot webhook secret in `SNRG WhatsApp Settings` on Desk. `site_config.json` still works as a fallback for existing setups.
- Quotation submit/cancel, Sales Invoice submit, and Payment Entry submit hooks queue WhatsApp sends in the background.
- Pending Quotation confirmations are also re-synced from Chatwoot every 30 minutes in small background batches, so older pending replies can be picked up without opening the form.
- ERPNext sends through Chatwoot, so outgoing messages appear in the Chatwoot conversation thread.
- Mobile lookup prefers document-level contact mobile, then customer mobile, then contact mobile. Payment Entry can also fall back to linked Sales Invoice contact details.
- Quotation sends now persist outbound Chatwoot message and conversation ids so inbound customer confirmations can be matched back safely.
- The Quotation form includes both a manual customer-confirmation override and a `Sync from Chatwoot` fallback action for privileged users, and stores an audit comment.
- This app is intentionally backend-only and does not add a Desk module or frontend UI.
- Successful sends are marked on the document timeline to prevent duplicate sends on repeat execution.
- Customer Payment Entry sends only run for `party_type = Customer`; supplier payments are skipped.
- Set each `enable_*_whatsapp_on_submit` flag to `0` on production if you want the app installed before enabling a given automation.

Recommended `sales_quotation_cancellation` template body:

```text
Dear {{1}},

This is to inform you that quotation {{2}} dated {{3}} has been cancelled in our records.

If you believe this has occurred in error or require any clarification, please reply to this message or contact us.

Regards,
SNRG Electricals India Private Limited
```

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

## WhatsApp Templates and Campaigns

Run `bench --site <site> migrate` after deploying the updated app. Enable the
site scheduler and run the long-queue worker. The existing Chatwoot settings
identify the inbox used for all campaigns. The pilot screens and actions are
available to System Managers.

Add these server-side site config settings:

| Key | Value |
| --- | --- |
| `snrg_whatsapp_waba_id` | WABA ID behind the configured Chatwoot Cloud API inbox |
| `snrg_whatsapp_graph_version` | Supported Meta Graph API version, including the `v` prefix |
| `snrg_whatsapp_meta_token` | Meta token with `whatsapp_business_management` and access to this WABA |
| `snrg_whatsapp_meta_app_id` | Meta app ID used to upload sample images for template approval |
| `snrg_whatsapp_test_number` | Internal WhatsApp test number in international format |
| `snrg_whatsapp_campaigns_enabled` | Defaults to 0. Set to 1 to explicitly enable campaign sending. Preview and template sync work while sending is disabled. |
| `snrg_whatsapp_campaign_batch_size` | Optional. Messages per scheduler batch, from 1 to 10. Default 3. |

Keep the Meta and Chatwoot tokens on the server. Open **SNRG WhatsApp
Template** through the Desk search, then click **Refresh Templates**. Create a
draft Utility or Marketing template and submit it to Meta. Enter one example
per numbered placeholder in order. For an Image header, save the draft, then
upload a JPEG or PNG sample directly to the record. The app syncs Meta template
status every 30 minutes. Sync approved templates to the configured Chatwoot
inbox as well if they are not there yet.

From the Customer list, select customers and choose **Create WhatsApp Campaign**
under Actions. Pick a template, set its variables, save, and click **Preview
Recipients**. For image campaigns, save once, upload the campaign image directly
to the record, save again, and run the preview. For now, the campaign uses a
single JPEG or PNG up to 5 MB and personalized body text. Chatwoot must return
an HTTPS media URL accessible to WhatsApp throughout the send. Use private
ERPNext attachments where available.

Campaign eligibility requires consent for the selected category. The Customer
fields **Opted In to WhatsApp Utility Campaigns** and **Opted In to WhatsApp
Marketing** default to off. Grant read/write access at Customer permission level
1 to the roles responsible for recording consent. Review the audience and run
**Send Test** before launching a campaign. The test uses sample values and the
configured internal number. Campaigns are limited to 500 selected customer records.

**Send Now** makes the campaign eligible at the next scheduler tick. **Schedule
Send** takes a one-time local date and time in the ERPNext site timezone.
Scheduled campaigns can be rescheduled or cancelled before sending. At dispatch,
the worker rechecks the approved template, campaign image, consent, and resolved
phone number. The worker pauses after a failed or unconfirmed attempt. Resume
continues with unsent recipients. It does not automatically resend any attempted
recipient. **Refresh Delivery Status** looks for exact message IDs in Chatwoot
and displays the delivery information Chatwoot returns.

For the pilot, verify template listing and creation, one internal text campaign,
one internal image campaign, a scheduled send and cancellation, and a normal
invoice send while a campaign is queued. Confirm message rendering and delivery
on the test phone and verify that replies reach the expected Chatwoot inbox.
