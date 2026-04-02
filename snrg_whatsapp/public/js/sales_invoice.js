function setupSalesInvoiceWhatsAppButtons(frm, retries = 5) {
	if (window.snrg_whatsapp && snrg_whatsapp.setup_document_buttons) {
		frappe.after_ajax(() => {
			setTimeout(() => snrg_whatsapp.setup_document_buttons(frm, "Sales Invoice"), 300);
		});
	} else if (retries > 0) {
		setTimeout(() => setupSalesInvoiceWhatsAppButtons(frm, retries - 1), 500);
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
