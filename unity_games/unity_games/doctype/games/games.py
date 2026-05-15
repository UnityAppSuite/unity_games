# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Games(Document):
	"""Composite catalogue (Layer 2): one row per (organiser, game).

	Document name = ``{game_organiser}-{name_of_game}`` (e.g. CBSE-Basketball).
	Holds the game's allowed age groups and events as child tables, which
	drive the cascading filters on the Game Entry web form.
	"""

	pass
