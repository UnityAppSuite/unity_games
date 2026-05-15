# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GameEntryDetails(Document):
	"""Child of Game Entry.

	On the web form it is the multi-game selection cart (parent adds N rows).
	After the on_submit fan-out, each spawned Game Entry carries a single
	read-only row representing that one game (the snapshot).
	"""

	pass
