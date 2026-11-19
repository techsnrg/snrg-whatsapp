frappe.listview_settings["SNRG WhatsApp Template"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Refresh Templates"), async () => {
            const result = await frappe.call({
                method: "snrg_whatsapp.templates.refresh_templates",
                freeze: true,
            });
            frappe.show_alert(__("Synced {0} templates", [result.message]));
            listview.refresh();
        });
    },
};
