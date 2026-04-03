const GROUP_LABEL = __("Send WhatsApp");

function getWhatsAppMessage(response, fallback) {
	return (response && response.message && response.message.message) || fallback;
}

function normalizeRecipientLabel(recipient) {
	return recipient.button_label || recipient.label || recipient.mobile;
}

async function fetchWhatsAppRecipients(args) {
	const response = await frappe.call({
		method: "snrg_whatsapp.api.get_manual_whatsapp_recipients",
		args,
	});
	return (response && response.message && response.message.recipients) || [];
}

async function sendDocumentWhatsApp(doctype, docname, recipient) {
	const label = normalizeRecipientLabel(recipient);
	try {
		const response = await frappe.call({
			method: "snrg_whatsapp.api.send_document_whatsapp_manual",
			args: {
				doctype,
				docname,
				recipient_mobile: recipient.mobile,
				recipient_label: label,
			},
			freeze: true,
			freeze_message: __("Sending WhatsApp..."),
		});
		frappe.show_alert({
			message: getWhatsAppMessage(response, __("{0} sent to {1}", [doctype, label])),
			indicator: "green",
		});
	} catch (error) {
		console.error("Failed to send document on WhatsApp", error);
		frappe.show_alert({
			message: __("Could not send WhatsApp message."),
			indicator: "red",
		});
	}
}

async function setupDocumentWhatsAppButtons(frm, doctype) {
	if (frm.is_new() || frm.doc.docstatus !== 1) return;

	const existingLabels = frm.__snrg_whatsapp_labels || [];
	existingLabels.forEach((label) => frm.remove_custom_button(label, GROUP_LABEL));
	frm.__snrg_whatsapp_labels = [];

	try {
		const recipients = await fetchWhatsAppRecipients({ doctype, docname: frm.doc.name });
		if (!recipients.length) {
			const label = __("No WhatsApp recipients");
			frm.add_custom_button(
				label,
				() => frappe.msgprint(__("No WhatsApp recipients are configured for this document.")),
				GROUP_LABEL
			);
			frm.__snrg_whatsapp_labels.push(label);
			return;
		}

		recipients.forEach((recipient) => {
			const label = normalizeRecipientLabel(recipient);
			frm.add_custom_button(label, () => sendDocumentWhatsApp(doctype, frm.doc.name, recipient), GROUP_LABEL);
			frm.__snrg_whatsapp_labels.push(label);
		});
	} catch (error) {
		console.error("Failed to load WhatsApp recipients", error);
		frappe.show_alert({
			message: __("Could not load WhatsApp recipients."),
			indicator: "red",
		});
	}
}

function bindDocumentWhatsApp(doctype) {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			frappe.after_ajax(() => {
				setTimeout(() => setupDocumentWhatsAppButtons(frm, doctype), 300);
			});
		},
		after_save(frm) {
			frappe.after_ajax(() => {
				setTimeout(() => setupDocumentWhatsAppButtons(frm, doctype), 300);
			});
		},
		on_submit(frm) {
			frappe.after_ajax(() => {
				setTimeout(() => setupDocumentWhatsAppButtons(frm, doctype), 300);
			});
		},
	});
}

bindDocumentWhatsApp("Quotation");
bindDocumentWhatsApp("Sales Invoice");
