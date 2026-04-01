frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
			snrg_whatsapp.setup_document_buttons(frm, "Quotation");
		}
	},
});
