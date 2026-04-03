from frappe import _


def get_data():
    return [
        {
            "module_name": "SNRG WhatsApp",
            "category": "Modules",
            "label": _("SNRG WhatsApp"),
            "color": "blue",
            "icon": "octicon octicon-comment-discussion",
            "type": "module",
            "description": _("Manage WhatsApp automation settings for ERPNext documents."),
        }
    ]

