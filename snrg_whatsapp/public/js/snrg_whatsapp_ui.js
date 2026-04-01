frappe.provide("snrg_whatsapp");

(function () {
	const GROUP_LABEL = __("Send WhatsApp");
	const REPORT_NAMES = ["Customer Ledger Report", "Customer AR Report"];

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

	async function sendReport(reportName, report, recipient) {
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
				},
				freeze: true,
				freeze_message: __("Sending WhatsApp…"),
			});
			alertSuccess(getMessage(response, __("{0} sent to {1}", [reportName, label])));
		} catch (error) {
			console.error("Failed to send report on WhatsApp", error);
			alertError(__("Could not send WhatsApp report."));
		}
	}

	snrg_whatsapp.setup_document_buttons = async function (frm, doctype) {
		clearFormButtons(frm);
		if (frm.is_new() || frm.doc.docstatus !== 1) return;

		try {
			const recipients = await fetchRecipients({ doctype, docname: frm.doc.name });
			if (!recipients.length) return;

			frm.__snrg_whatsapp_labels = [];
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

	snrg_whatsapp.bindReportButtons = function (report, reportName) {
		if (!report || report.__snrg_whatsapp_bound) return;
		report.__snrg_whatsapp_bound = true;
		report.__snrg_whatsapp_labels = [];

		const rebuild = async () => {
			clearReportButtons(report);

			const customer = report.get_filter_value("customer");
			if (!customer) return;

			try {
				const recipients = await fetchRecipients({ customer });
				if (!recipients.length) return;

				report.__snrg_whatsapp_labels = [];
				recipients.forEach((recipient) => {
					const label = normalizeRecipientLabel(recipient);
					report.page.add_inner_button(label, () => sendReport(reportName, report, recipient), GROUP_LABEL);
					report.__snrg_whatsapp_labels.push(label);
				});
			} catch (error) {
				console.error("Failed to build report WhatsApp buttons", error);
				alertError(__("Could not load WhatsApp recipients."));
			}
		};

		report.__snrg_whatsapp_rebuild = rebuild;

		const customerFilter = report.get_filter && report.get_filter("customer");
		if (customerFilter && !customerFilter.__snrg_whatsapp_bound) {
			customerFilter.__snrg_whatsapp_bound = true;
			const originalOnChange = customerFilter.df.onchange;
			customerFilter.df.onchange = function () {
				if (originalOnChange) {
					originalOnChange.apply(this, arguments);
				}
				frappe.after_ajax(() => rebuild());
			};
		}

		setTimeout(rebuild, 300);
	};

	function patchReport(reportName) {
		const reportConfig = frappe.query_reports && frappe.query_reports[reportName];
		if (!reportConfig || reportConfig.__snrg_whatsapp_patched) return !!reportConfig;

		const originalOnload = reportConfig.onload;
		reportConfig.onload = function (report) {
			if (originalOnload) {
				originalOnload(report);
			}
			snrg_whatsapp.bindReportButtons(report, reportName);
		};
		reportConfig.__snrg_whatsapp_patched = true;
		return true;
	}

	function patchReportsWithRetry(attempt) {
		const patched = REPORT_NAMES.map((name) => patchReport(name));
		if (patched.every(Boolean) || attempt > 20) return;
		setTimeout(() => patchReportsWithRetry(attempt + 1), 400);
	}

	patchReportsWithRetry(0);
	if (frappe.router && frappe.router.on) {
		frappe.router.on("change", () => patchReportsWithRetry(0));
	}
})();
