import frappe
from frappe.model.document import Document


class SNRGWhatsAppCampaign(Document):
    def validate(self):
        previous = self.get_doc_before_save()
        if previous and previous.status != "Draft":
            frappe.throw("Only draft WhatsApp campaigns can be edited.")
        self.status = "Draft"
        for field in (
            "snapshot", "media_url", "scheduled_at", "schedule_timezone", "launched_by",
            "started_at", "sender_inbox", "status_detail",
        ):
            self.set(field, None)
        for row in self.recipients:
            for field in (
                "phone", "status", "message_preview", "detail", "parameters",
                "attempted_at", "conversation_id", "message_id",
            ):
                row.set(field, None)
