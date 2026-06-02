# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

"""Guardian scoping for Game Entry."""

import frappe

from unity_games.utils.helpers import get_guardian_for_user, get_guardian_student_names

PRIVILEGED = {"System Manager", "Administrator"}


def _is_privileged(user):
	return bool(PRIVILEGED & set(frappe.get_roles(user)))


def get_permission_query_conditions(user=None):
	"""List-view / report scoping for Game Entry."""
	user = user or frappe.session.user
	if _is_privileged(user):
		return ""
	guardian = get_guardian_for_user(user)
	students = get_guardian_student_names(guardian) if guardian else []
	if not students:
		# No linked children -> see nothing.
		return "1=0"
	in_list = ", ".join(frappe.db.escape(s) for s in students)
	return f"`tabGame Entry`.`student` in ({in_list})"


def has_permission(doc, user=None, permission_type=None):
	"""Document-level scoping for Game Entry."""
	user = user or frappe.session.user
	if _is_privileged(user):
		return True
	guardian = get_guardian_for_user(user)
	if not guardian:
		return False
	return doc.student in get_guardian_student_names(guardian)
