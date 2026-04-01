function setupQuotationWhatsAppButtons(frm) {
	if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
		frappe.after_ajax(() => {
			setTimeout(() => snrg_whatsapp.setup_document_buttons(frm, "Quotation"), 300);
		});
	}
}

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		setupQuotationWhatsAppButtons(frm);
	},
	after_save(frm) {
		setupQuotationWhatsAppButtons(frm);
	},
	on_submit(frm) {
		setupQuotationWhatsAppButtons(frm);
	},
});
