frappe.ui.form.on("SNRG WhatsApp Template", {
    refresh(frm) {
        if (frm.is_new()) return;
        if (frm.doc.status !== "Draft") {
            frm.disable_save();
            return;
        }
        frm.add_custom_button(__("Submit to Meta"), () => {
            if (frm.is_dirty()) {
                frappe.msgprint(__("Save your changes before submitting to Meta."));
                return;
            }
            frappe.confirm(__("Submit this template to Meta for review?"), async () => {
                try {
                    await frappe.call({
                        method: "snrg_whatsapp.templates.submit_template",
                        args: { name: frm.doc.name },
                        freeze: true,
                    });
                } finally {
                    await frm.reload_doc();
                }
            });
        });
    },
});
