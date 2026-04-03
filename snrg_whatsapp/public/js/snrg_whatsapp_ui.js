frappe.provide("snrg_whatsapp");

(function () {
	const GROUP_LABEL = __("Send WhatsApp");
	const REPORT_NAMES = ["Customer Ledger Report", "Customer AR Report"];
	const REPORT_SEND_OPTIONS = {
		"Customer Ledger Report": [
			{ label: __("Send Ledger"), include_ar: 0, include_ledger: 1 },
			{ label: __("Send Ledger + AR"), include_ar: 1, include_ledger: 1 },
		],
		"Customer AR Report": [
			{ label: __("Send AR"), include_ar: 1, include_ledger: 0 },
			{ label: __("Send Ledger + AR"), include_ar: 1, include_ledger: 1 },
		],
	};

	function alertSuccess(message) {
		frappe.show_alert({ message, indicator: "green" });
	}

	function alertError(message) {
		frappe.show_alert({ message, indicator: "red" });
	}

	function getMessage(response, fallback) {
		return (response && response.message && response.message.message) || fallback;
	}

	function normalizeRecipientLabel(recipient) {
		return recipient.button_label || recipient.label || recipient.mobile;
	}

	function clearFormButtons(frm) {
		if (!frm.__snrg_whatsapp_labels) return;
		frm.__snrg_whatsapp_labels.forEach((label) => frm.remove_custom_button(label, GROUP_LABEL));
		frm.__snrg_whatsapp_labels = [];
	}

	function clearReportButtons(report) {
		if (!report.__snrg_whatsapp_labels) return;
		report.__snrg_whatsapp_labels.forEach((label) => report.page.remove_inner_button(label, GROUP_LABEL));
		report.__snrg_whatsapp_labels = [];
	}

	async function fetchRecipients(args) {
		const response = await frappe.call({
			method: "snrg_whatsapp.api.get_manual_whatsapp_recipients",
			args,
		});
		return (response && response.message && response.message.recipients) || [];
	}

	async function sendDocument(doctype, docname, recipient) {
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
				freeze_message: __("Sending WhatsApp…"),
			});
			alertSuccess(getMessage(response, __("{0} sent to {1}", [doctype, label])));
		} catch (error) {
			console.error("Failed to send document on WhatsApp", error);
			alertError(__("Could not send WhatsApp message."));
		}
	}

	async function sendReport(reportName, report, recipient, option) {
		const filters = report.get_filter_values();
		if (!filters || !filters.customer) {
			frappe.msgprint(__("Please select a Customer before sending this report on WhatsApp."));
			return;
		}
		const label = normalizeRecipientLabel(recipient);
		try {
			const response = await frappe.call({
				method: "snrg_whatsapp.api.send_customer_report_whatsapp",
				args: {
					report_name: reportName,
					recipient_mobile: recipient.mobile,
					recipient_label: label,
					filters: JSON.stringify(filters),
					include_ar: option.include_ar,
					include_ledger: option.include_ledger,
				},
				freeze: true,
				freeze_message: __("Sending WhatsApp…"),
			});
			alertSuccess(getMessage(response, __("{0} sent to {1}", [option.label, label])));
		} catch (error) {
			console.error("Failed to send report on WhatsApp", error);
			alertError(__("Could not send WhatsApp report."));
		}
	}

	snrg_whatsapp.setup_document_buttons = async function (frm, doctype) {
		if (frm.is_new() || frm.doc.docstatus !== 1) return;

		// Prevent flicker: if button already exists in DOM, do not re-add
		if (frm.page.wrapper.find(`button:contains("${GROUP_LABEL}")`).length > 0) {
			return;
		}

		try {
			if (!frm.__whatsapp_recipients) {
				frm.__whatsapp_recipients = await fetchRecipients({ doctype, docname: frm.doc.name });
			}
			const recipients = frm.__whatsapp_recipients;

			frm.__snrg_whatsapp_labels = [];
			if (!recipients.length) {
				const label = __("No Sales Person Attached");
				frm.add_custom_button(
					label,
					() => frappe.msgprint(__("No Sales Person is attached to this customer.")),
					GROUP_LABEL
				);
				frm.__snrg_whatsapp_labels.push(label);
				return;
			}

			recipients.forEach((recipient) => {
				const label = normalizeRecipientLabel(recipient);
				frm.add_custom_button(label, () => sendDocument(doctype, frm.doc.name, recipient), GROUP_LABEL);
				frm.__snrg_whatsapp_labels.push(label);
			});
		} catch (error) {
			console.error("Failed to load WhatsApp recipients", error);
			alertError(__("Could not load WhatsApp recipients."));
		}
	};

	snrg_whatsapp.loadReportButtons = async function (report, reportName) {
		if (!report || !report.page) return;
		const customer = report.get_filter_value("customer");

		clearReportButtons(report);

		if (!customer) return;

		report.__whatsapp_last_customer = customer;

		const placeholder = __("Evaluating...");
		report.page.add_inner_button(placeholder, () => {}, GROUP_LABEL);
		report.__snrg_whatsapp_labels = [placeholder];

		let recipients = [];
		try { recipients = await fetchRecipients({ customer }); }
		catch (error) { console.error(error); }

		// Filter changed mid-flight check
		if (report.__whatsapp_last_customer !== customer) return;

		clearReportButtons(report);

		if (!recipients.length) {
			const label = __("No WhatsApp recipients");
			report.page.add_inner_button(label, () => {
				frappe.msgprint(__("No WhatsApp recipients are configured for this customer."));
			}, GROUP_LABEL);
			report.__snrg_whatsapp_labels.push(label);
			return;
		}

		const options = REPORT_SEND_OPTIONS[reportName] || [
			{ label: __("Send Report"), include_ar: 0, include_ledger: 1 },
		];

		recipients.forEach((recipient) => {
			options.forEach((option) => {
				const label = `${normalizeRecipientLabel(recipient)} - ${option.label}`;
				report.page.add_inner_button(label, () => {
					if (!recipient.mobile) {
						frappe.msgprint(__("No mobile number available. Please update the contact."));
						return;
					}
					sendReport(reportName, report, recipient, option);
				}, GROUP_LABEL);
				report.__snrg_whatsapp_labels.push(label);
			});
		});
	};
})();
