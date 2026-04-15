const GROUP_LABEL = __("Send WhatsApp");
const CONFIRMATION_GROUP_LABEL = __("Customer Confirmation");

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

async function ensureCustomerConfirmationSetup(frm, doctype) {
	if (doctype !== "Quotation" || frm.is_new() || frm.doc.docstatus !== 1) return false;
	if (frm.fields_dict.customer_confirmation_status) return false;
	if (frm.__snrg_confirmation_setup_checked) return false;

	frm.__snrg_confirmation_setup_checked = true;

	try {
		const response = await frappe.call({
			method: "snrg_whatsapp.api.ensure_customer_confirmation_setup",
		});
		const created = !!(response && response.message && response.message.created);
		if (created || frm.fields_dict.customer_confirmation_status) {
			frappe.show_alert({
				message: __("Customer confirmation fields were initialized. Reloading the form..."),
				indicator: "green",
			});
			setTimeout(() => window.location.reload(), 500);
			return true;
		}
	} catch (error) {
		console.error("Failed to initialize customer confirmation fields", error);
	}

	return false;
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

function setupConfirmationButton(frm, doctype) {
	if (doctype !== "Quotation" || frm.is_new() || frm.doc.docstatus !== 1) return;

	const existingLabels = frm.__snrg_confirmation_labels || [];
	existingLabels.forEach((label) => frm.remove_custom_button(label, CONFIRMATION_GROUP_LABEL));
	frm.__snrg_confirmation_labels = [];

	const label = __("Set Status");
	frm.add_custom_button(
		label,
		() => {
			frappe.prompt(
				[
					{
						fieldname: "status",
						fieldtype: "Select",
						label: __("Status"),
						options: ["Pending", "Confirmed", "Changes Requested"].join("\n"),
						reqd: 1,
						default: frm.doc.customer_confirmation_status || "Pending",
					},
					{
						fieldname: "notes",
						fieldtype: "Small Text",
						label: __("Notes"),
						reqd: 1,
					},
				],
				async (values) => {
					try {
						const response = await frappe.call({
							method: "snrg_whatsapp.api.set_customer_confirmation_status",
							args: {
								quotation_name: frm.doc.name,
								status: values.status,
								notes: values.notes,
							},
							freeze: true,
							freeze_message: __("Updating confirmation..."),
						});
						frappe.show_alert({
							message: getWhatsAppMessage(response, __("Customer confirmation updated.")),
							indicator: "green",
						});
						await frm.reload_doc();
					} catch (error) {
						console.error("Failed to update confirmation", error);
						frappe.show_alert({
							message: __("Could not update customer confirmation."),
							indicator: "red",
						});
					}
				},
				__("Set Customer Confirmation"),
				__("Update")
			);
		},
		CONFIRMATION_GROUP_LABEL
	);
	frm.__snrg_confirmation_labels.push(label);
}

function bindDocumentWhatsApp(doctype) {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			frappe.after_ajax(() => {
				setTimeout(async () => {
					const reloading = await ensureCustomerConfirmationSetup(frm, doctype);
					if (reloading) return;
					setupDocumentWhatsAppButtons(frm, doctype);
					setupConfirmationButton(frm, doctype);
				}, 300);
			});
		},
		after_save(frm) {
			frappe.after_ajax(() => {
				setTimeout(() => {
					setupDocumentWhatsAppButtons(frm, doctype);
					setupConfirmationButton(frm, doctype);
				}, 300);
			});
		},
		on_submit(frm) {
			frappe.after_ajax(() => {
				setTimeout(() => {
					setupDocumentWhatsAppButtons(frm, doctype);
					setupConfirmationButton(frm, doctype);
				}, 300);
			});
		},
	});
}

bindDocumentWhatsApp("Quotation");
bindDocumentWhatsApp("Sales Invoice");
