function setupQuotationWhatsAppButtons(frm) {
	if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
		const delays = [100, 600, 1500];
		frappe.after_ajax(() => {
			delays.forEach((delay) => {
				setTimeout(() => snrg_whatsapp.setup_document_buttons(frm, "Quotation"), delay);
			});
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
