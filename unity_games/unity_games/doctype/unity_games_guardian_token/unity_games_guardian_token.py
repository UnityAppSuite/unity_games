# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class UnityGamesGuardianToken(Document):
	"""Per-guardian auto-login token for the Unity Games web form."""

	def before_insert(self):
		if not self.token:
			self.token = frappe.generate_hash(self.guardian, length=20)

	@staticmethod
	def get_or_create(guardian: str) -> str:
		"""Return the (enabled) token for a guardian, creating it if needed."""
		name = frappe.db.get_value(
			"Unity Games Guardian Token", {"guardian": guardian}, "name"
		)
		if name:
			doc = frappe.get_doc("Unity Games Guardian Token", name)
			if not doc.enabled:
				doc.enabled = 1
				doc.save(ignore_permissions=True)
			return doc.token
		doc = frappe.get_doc(
			{"doctype": "Unity Games Guardian Token", "guardian": guardian}
		)
		doc.insert(ignore_permissions=True)
		return doc.token

	@staticmethod
	def resolve_guardian(token: str):
		"""Return the guardian name for a valid, enabled token, else None."""
		if not token:
			return None
		return frappe.db.get_value(
			"Unity Games Guardian Token",
			{"token": token, "enabled": 1},
			"guardian",
		)
