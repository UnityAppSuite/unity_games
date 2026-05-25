# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

STATUS_TRANSITIONS = {
	"Draft": {"Draft", "Published", "Cancelled"},
	"Published": {"Published", "Closed", "Cancelled"},
	"Closed": {"Closed"},
	"Cancelled": {"Cancelled"},
}


class GameAuthority(Document):
	"""Running tournament/season. Submittable."""

	def validate(self):
		self.validate_dates()
		self.validate_status_transition()
		self.validate_google_calendar()
		self.apply_settings_defaults()
		self.validate_registration_fees()
		self.validate_unique_games()
		self.append_classes()
		self.validate_classes_branch()
		self.stamp_gallery_publish_dates()

	def validate_unique_games(self):
		seen = {}
		for i, r in enumerate(self.get("games") or [], 1):
			g = r.get("game")
			if not g:
				continue
			if g in seen:
				frappe.throw(_("Game {0} is listed more than once (rows #{1} and #{2}).").format(g, seen[g], i))
			seen[g] = i

	def validate_registration_fees(self):
		"""Disallow overlapping date ranges within each kind (is_late=0 base, is_late=1 late)."""
		from frappe.utils import get_datetime
		rows = self.get("registration_fees_details") or []
		clean = []
		for i, r in enumerate(rows, 1):
			if not (r.get("from") and r.get("to")):
				frappe.throw(
					_("Registration Fees row #{0}: From and To are required.").format(i)
				)
			f, t = get_datetime(r.get("from")), get_datetime(r.get("to"))
			if f > t:
				frappe.throw(
					_("Registration Fees row #{0}: From must be <= To.").format(i)
				)
			clean.append((i, f, t, 1 if r.get("is_late") else 0))
		for kind, label in ((0, "base"), (1, "late")):
			same = [(i, f, t) for (i, f, t, k) in clean if k == kind]
			same.sort(key=lambda x: x[1])
			for a, b in zip(same, same[1:]):
				if a[2] >= b[1]:
					frappe.throw(
						_("Overlapping {0} fee windows in rows #{1} and #{2}.").format(
							label, a[0], b[0]
						)
					)

	def validate_dates(self):
		if self.start_date and self.end_date and getdate(self.start_date) > getdate(self.end_date):
			frappe.throw(_("End Date cannot be before Start Date."))

	def validate_status_transition(self):
		if self.is_new():
			return
		before = self.get_doc_before_save()
		if not before or before.status == self.status:
			return
		if self.status not in STATUS_TRANSITIONS.get(before.status, set()):
			frappe.throw(
				_("Invalid status transition: {0} -> {1}.").format(
					before.status, self.status
				)
			)

	def validate_google_calendar(self):
		if self.sync_with_google_calendar and not self.google_calendar:
			frappe.throw(_("Select a Google Calendar to sync with."))
		if not self.sync_with_google_calendar:
			self.add_video_conferencing = 0

	def apply_settings_defaults(self):
		if self.sync_with_google_calendar and not self.google_calendar:
			default_cal = frappe.db.get_single_value(
				"Unity Games Settings", "default_google_calendar"
			)
			if default_cal:
				self.google_calendar = default_cal

	def append_classes(self):
		"""When all_classes is ticked, fill Classes with the branch's Programs."""
		if not self.all_classes:
			return
		filters = {"school": self.branch} if self.branch else {}
		existing = {r.get("class") for r in self.classes}
		for p in frappe.get_all("Program", filters=filters, fields=["name", "school"]):
			if p.name not in existing:
				self.append(
					"classes",
					{"class": p.name, "school": p.school, "all_divisions": 1},
				)

	def validate_classes_branch(self):
		"""If a branch is set, every selected class must belong to it."""
		if not self.branch:
			return
		for row in self.classes or []:
			if not row.get("class"):
				continue
			school = row.school or frappe.db.get_value(
				"Program", row.get("class"), "school"
			)
			if school and school != self.branch:
				frappe.throw(
					_("Class {0} does not belong to branch {1}.").format(
						row.get("class"), self.branch
					)
				)

	def stamp_gallery_publish_dates(self):
		for row in self.images or []:
			if row.publish and not row.publish_date:
				row.publish_date = now_datetime()
			elif not row.publish:
				row.publish_date = None

	def game_names(self):
		"""Names of Games in scope this season."""
		return [r.game for r in self.games]
