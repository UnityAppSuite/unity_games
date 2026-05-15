# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GameAuthorityClass(Document):
	"""Child of Game Authority (Rules & Limitations tab).

	One eligible class (Link -> Program) with its school and divisions.
	Mirrors edu_quality's ``Event Class``; owned by unity_games to keep the
	app standalone. When the parent's ``all_classes`` flag is set, this
	table is auto-populated server-side (later pass).
	"""

	pass
