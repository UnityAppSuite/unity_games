# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GameEntry(Document):
	"""Parent's registration (Layer 4). Submittable, Web Form host.

	Schema only — autoname/resolve_pe/validate/fan-out logic deferred to
	the implementation pass.
	"""

	pass
