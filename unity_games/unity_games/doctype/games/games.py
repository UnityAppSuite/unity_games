# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class Games(Document):
	"""Composite catalogue: one row per (organiser, game)."""

	def validate(self):
		if not self.age_groups:
			frappe.throw(_("Add at least one Age Group."))
		if not self.events:
			frappe.throw(_("Add at least one Event."))
		self._dedupe()

	def _dedupe(self):
		seen = set()
		for row in self.age_groups:
			if row.age in seen:
				frappe.throw(_("Duplicate age group: {0}").format(row.age))
			seen.add(row.age)
		seen = set()
		for row in self.events:
			key = (row.game_event, row.gender or "Any")
			if key in seen:
				frappe.throw(
					_("Duplicate event: {0} ({1})").format(
						row.game_event, row.gender or "Any"
					)
				)
			seen.add(key)

	def allowed_ages(self):
		return [r.age for r in self.age_groups]

	def allowed_events(self, gender=None):
		"""Events allowed for a gender."""
		out = []
		for r in self.events:
			g = r.gender or "Any"
			if gender is None or g == "Any" or g == gender:
				out.append(r.game_event)
		return out
