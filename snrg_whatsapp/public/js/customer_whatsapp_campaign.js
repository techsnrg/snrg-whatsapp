(() => {
    const settings = frappe.listview_settings.Customer || {};
    const originalOnload = settings.onload;
    frappe.listview_settings.Customer = {
        ...settings,
        onload(listview) {
            originalOnload?.call(this, listview);
            if (!frappe.user.has_role("System Manager")) return;
            listview.page.add_action_item(__("Create WhatsApp Campaign"), async () => {
                const customers = listview.get_checked_items().map((row) => row.name);
                if (!customers.length) {
                    frappe.msgprint(__("Select the customers for your WhatsApp campaign."));
                    return;
                }
                const result = await frappe.call({
                    method: "snrg_whatsapp.campaigns.create_draft",
                    args: { customers },
                    freeze: true,
                });
                await frappe.set_route("Form", "SNRG WhatsApp Campaign", result.message);
            });
        },
    };
})();
