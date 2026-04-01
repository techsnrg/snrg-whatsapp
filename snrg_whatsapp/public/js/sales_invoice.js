frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
			snrg_whatsapp.setup_document_buttons(frm, "Sales Invoice");
		}
	},
});
