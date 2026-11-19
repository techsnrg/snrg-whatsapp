import frappe
from frappe.model.document import Document


class SNRGWhatsAppTemplate(Document):
    def validate(self):
        if self.flags.from_meta:
            return
        previous = self.get_doc_before_save()
        if previous and previous.status != "Draft":
            frappe.throw("This template is managed by Meta. Create a new draft to make changes.")
        self.status = "Draft"
        for field in (
            "meta_id", "waba_id", "last_sync", "status_details", "components", "parameter_format",
        ):
            self.set(field, None)
