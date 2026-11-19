frappe.ui.form.on("SNRG WhatsApp Campaign", {
    setup(frm) {
        frm.set_query("template", () => ({
            filters: { status: "APPROVED", category: ["in", ["UTILITY", "MARKETING"]] },
        }));
    },
    refresh(frm) {
        if (frm.is_new()) return;
        const { status, snapshot, sender_inbox, schedule_timezone } = frm.doc;
        const call = async (method, args = {}) => {
            if (frm.is_dirty()) {
                frappe.msgprint(__("Save your changes before continuing."));
                return;
            }
            const result = await frappe.call({
                method: "snrg_whatsapp.campaigns." + method,
                args: { name: frm.doc.name, ...args },
                freeze: true,
            });
            await frm.reload_doc();
            return result.message;
        };
        const schedule = () => {
            const timezone = schedule_timezone || frappe.boot.time_zone?.system || __("site timezone");
            frappe.prompt([{
                fieldname: "scheduled_at",
                fieldtype: "Data",
                label: __("Date and time in {0}", [timezone]),
                description: __("Enter YYYY-MM-DD HH:MM using the ERPNext site timezone."),
                reqd: 1,
            }], (values) => call("launch", values), __("Schedule WhatsApp Campaign"), __("Schedule"));
        };

        if (status === "Draft") {
            frm.add_custom_button(__("Preview Recipients"), async () => {
                const counts = await call("preview");
                if (counts) frappe.msgprint(__("{0} ready, {1} skipped", [counts.ready, counts.skipped]));
            });
            if (snapshot) {
                frm.add_custom_button(__("Send Test"), async () => {
                    const result = await call("send_test");
                    if (result) frappe.msgprint(result.detail || __("Test message status: {0}", [result.status]));
                });
                frm.add_custom_button(__("Send Now"), () => {
                    const ready = frm.doc.recipients.filter((row) => row.status === "Ready").length;
                    frappe.confirm(__("Queue WhatsApp messages for {0} recipients via inbox {1}?", [
                        ready, sender_inbox,
                    ]), () => call("launch"));
                });
                frm.add_custom_button(__("Schedule Send"), schedule);
            }
            return;
        }

        frm.disable_save();
        for (const field of ["campaign_name", "template", "campaign_image", "variable_values", "recipients"]) {
            frm.set_df_property(field, "read_only", 1);
        }
        const actions = {
            Scheduled: [["Reschedule", schedule], ["Cancel Send", "cancel"]],
            Queued: [["Pause", "pause"], ["Cancel Send", "cancel"]],
            Sending: [["Pause", "pause"]],
            Paused: [["Resume", "resume"], ["Cancel Unsent Messages", "cancel"]],
        };
        for (const [label, action] of actions[status] || []) {
            frm.add_custom_button(__(label), typeof action === "function" ? action : () => {
                frappe.confirm(__(label) + "?", () => call("change_campaign_status", { action }));
            });
        }
        if (frm.doc.recipients.some((row) => row.message_id)) {
            frm.add_custom_button(__("Refresh Delivery Status"), () => call("refresh_delivery"));
        }
    },
});
