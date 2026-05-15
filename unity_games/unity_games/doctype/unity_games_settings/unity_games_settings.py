# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class UnityGamesSettings(Document):
	"""App-wide configuration (Single).

	Holds global config consumed by the implementation pass: default
	Google Calendar, reminder policy, consent text, RPA credentials
	(PRD Q6), and the deferred late-fee config (PRD Q4). Schema only.
	"""

	pass
