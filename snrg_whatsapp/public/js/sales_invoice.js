function setupSalesInvoiceWhatsAppButtons(frm) {
	if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
		const delays = [100, 600, 1500];
		frappe.after_ajax(() => {
			delays.forEach((delay) => {
				setTimeout(() => snrg_whatsapp.setup_document_buttons(frm, "Sales Invoice"), delay);
			});
		});
	}
}

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		setupSalesInvoiceWhatsAppButtons(frm);
	},
	after_save(frm) {
		setupSalesInvoiceWhatsAppButtons(frm);
	},
	on_submit(frm) {
		setupSalesInvoiceWhatsAppButtons(frm);
	},
});
