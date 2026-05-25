# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

"""Shared helpers for unity_games."""

import re

import frappe
from frappe.utils import getdate, today


def slug(value: str) -> str:
	"""Slugify a value for the Game Entry composite name."""
	return re.sub(r"[^A-Za-z0-9]+", "-", (value or "").strip()).strip("-")


def get_settings():
	"""Cached Unity Games Settings single."""
	return frappe.get_cached_doc("Unity Games Settings")


def age_on(dob, ref_date=None):
	"""Human-readable age string like '16 Year 6 Months 28 Days'."""
	if not dob:
		return ""
	dob = getdate(dob)
	ref = getdate(ref_date) if ref_date else getdate(today())
	years = ref.year - dob.year
	months = ref.month - dob.month
	days = ref.day - dob.day
	if days < 0:
		months -= 1
		prev_month = ref.month - 1 or 12
		prev_year = ref.year if ref.month != 1 else ref.year - 1
		import calendar
		days += calendar.monthrange(prev_year, prev_month)[1]
	if months < 0:
		years -= 1
		months += 12
	return f"{years} Year {months} Months {days} Days"


def age_years_on(dob, ref_date=None) -> int:
	"""Integer age in completed years on ref_date (default today)."""
	if not dob:
		return 0
	dob = getdate(dob)
	ref = getdate(ref_date) if ref_date else getdate(today())
	return ref.year - dob.year - ((ref.month, ref.day) < (dob.month, dob.day))


def cbse_age_reference_date(event_year: int):
	"""31 December of the event year."""
	import datetime
	return datetime.date(event_year, 12, 31)


def get_active_program_enrollment(student: str, academic_year: str):
	"""Submitted Program Enrollment for (student, academic_year), or None."""
	if not student or not academic_year:
		return None
	rows = frappe.get_all(
		"Program Enrollment",
		filters={"student": student, "academic_year": academic_year, "docstatus": 1},
		fields=["name"],
	)
	if not rows:
		return None
	if len(rows) > 1:
		frappe.throw(
			frappe._(
				"Multiple active Program Enrollments for {0} in {1}. "
				"Contact the school admin."
			).format(student, academic_year)
		)
	return frappe.get_cached_doc("Program Enrollment", rows[0].name)


def default_academic_year():
	return frappe.defaults.get_global_default("academic_year")


def get_guardian_for_user(user: str):
	"""Guardian linked to a User, or None."""
	if not user or user == "Guest":
		return None
	name = frappe.db.get_value("Guardian", {"user": user}, "name")
	return name


def get_guardian_student_names(guardian: str):
	"""Student names linked to a Guardian (Student.guardians or Guardian.students)."""
	if not guardian:
		return []
	students = set(
		frappe.get_all(
			"Student Guardian",
			filters={"guardian": guardian, "parenttype": "Student"},
			pluck="parent",
		)
	)
	students.update(
		frappe.get_all(
			"Guardian Student",
			filters={"parent": guardian, "parenttype": "Guardian"},
			pluck="student",
		)
	)
	return sorted(s for s in students if s)


# ---- Consent OTP helpers ------------------------------------------------

def get_guardian_contacts(student: str):
	"""All guardian email + mobile pairs linked to a student."""
	if not student:
		return []
	out = []
	rows = frappe.get_all(
		"Student Guardian",
		filters={"parent": student, "parenttype": "Student"},
		pluck="guardian",
	)
	for g in rows:
		if not g:
			continue
		gd = frappe.db.get_value(
			"Guardian", g, ["email_address", "mobile_number"], as_dict=True
		) or {}
		out.append({
			"guardian": g,
			"email": gd.get("email_address"),
			"mobile": gd.get("mobile_number"),
		})
	return out


def _row_contact_for(student, guardian):
	"""(email, mobile) from the Student Guardian row matching this guardian on the student."""
	row = frappe.db.get_value(
		"Student Guardian",
		{"parent": student, "parenttype": "Student", "guardian": guardian},
		["email", "mobile_no"],
		as_dict=True,
	) or {}
	return row.get("email"), row.get("mobile_no")


def get_logged_in_guardian_contact(student):
	"""Contact for the logged-in guardian on a student (Guardian fields then Student Guardian row fallback)."""
	guardian = get_guardian_for_user(frappe.session.user)
	if not guardian or student not in get_guardian_student_names(guardian):
		return None
	gd = frappe.db.get_value(
		"Guardian", guardian, ["email_address", "mobile_number"], as_dict=True
	) or {}
	row_email, row_mobile = _row_contact_for(student, guardian)
	return {
		"guardian": guardian,
		"email": gd.get("email_address") or row_email or None,
		"mobile": gd.get("mobile_number") or row_mobile or None,
	}


def mask_email(e):
	if not e or "@" not in e:
		return e or ""
	local, domain = e.split("@", 1)
	local_masked = (local[:4] + "***") if len(local) > 4 else (local[0] + "***")
	return f"{local_masked}@{domain}"


def mask_mobile(m):
	if not m:
		return ""
	m = str(m)
	if len(m) <= 4:
		return m
	return "X" * (len(m) - 4) + m[-4:]
