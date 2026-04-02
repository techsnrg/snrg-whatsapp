function setupQuotationWhatsAppButtons(frm, retries = 5) {
	if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
		frappe.after_ajax(() => {
			setTimeout(() => snrg_whatsapp.setup_document_buttons(frm, "Quotation"), 300);
		});
	} else if (retries > 0) {
		setTimeout(() => setupQuotationWhatsAppButtons(frm, retries - 1), 500);
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
