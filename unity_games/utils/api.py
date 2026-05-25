# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

"""Public API for the Unity Games web form."""

import frappe
from frappe import _

from unity_games.unity_games.doctype.unity_games_guardian_token.unity_games_guardian_token import (
	UnityGamesGuardianToken,
)
from unity_games.utils.helpers import (
	age_on,
	get_guardian_for_user,
	get_guardian_student_names,
)


@frappe.whitelist(allow_guest=True)
def login_as_guardian(h=None, redirect_to="unity-games"):
	"""Validate the token, log the guardian's User in, 302 to the form."""
	guardian = UnityGamesGuardianToken.resolve_guardian(h)
	if not guardian:
		frappe.throw(_("Invalid or expired link."), frappe.AuthenticationError)
	user = frappe.db.get_value("Guardian", guardian, "user")
	if not user:
		frappe.throw(
			_("No user is linked to this guardian. Contact the school."),
			frappe.AuthenticationError,
		)
	frappe.local.login_manager.login_as(user)
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = "/" + (redirect_to or "unity-games")


@frappe.whitelist()
def get_guardian_link(guardian):
	"""Coordinator helper: get-or-create a guardian's auto-login URL."""
	token = UnityGamesGuardianToken.get_or_create(guardian)
	return (
		f"{frappe.utils.get_url()}/api/method/"
		f"unity_games.utils.api.login_as_guardian?h={token}&redirect_to=unity-games"
	)


@frappe.whitelist()
def get_my_students():
	"""Children of the logged-in guardian."""
	guardian = get_guardian_for_user(frappe.session.user)
	if not guardian:
		return []
	names = get_guardian_student_names(guardian)
	if not names:
		return []
	return frappe.get_all(
		"Student",
		filters={"name": ["in", names]},
		fields=["name", "student_name"],
		order_by="student_name asc",
	)


def _assert_own_student(student):
	"""A guardian may only act on their own children."""
	if "System Manager" in frappe.get_roles(frappe.session.user):
		return
	guardian = get_guardian_for_user(frappe.session.user)
	if not guardian or student not in get_guardian_student_names(guardian):
		frappe.throw(_("Not permitted for this student."), frappe.PermissionError)


@frappe.whitelist()
def get_student_snapshot(student):
	"""Read-only grid prefill for the form."""
	_assert_own_student(student)
	st = frappe.get_cached_doc("Student", student)
	father = None
	for row in st.get("guardians") or []:
		if (row.get("relation") or "").lower() == "father":
			father = row.get("guardian_name")
			break
	return {
		"student": st.name,
		"registration_no": st.name,
		"student_name": st.student_name,
		"father_name": father,
		"date_of_birth": st.date_of_birth,
		"student_age": age_on(st.date_of_birth),
		"gender": st.get("gender"),
		"image": st.get("image"),
	}


def _now():
	from frappe.utils import now_datetime
	return now_datetime()


def _game_is_open(game_doc_or_name):
	"""Games.last_day_to_register guard (None / future => open)."""
	from frappe.utils import get_datetime
	g = (
		game_doc_or_name
		if hasattr(game_doc_or_name, "get")
		else frappe.get_cached_doc("Games", game_doc_or_name)
	)
	d = g.get("last_day_to_register")
	return (not d) or get_datetime(d) >= _now()


@frappe.whitelist()
def get_authority_games(game_authority):
	"""Game names offered in a (Published, enabled) season."""
	if not game_authority:
		return []
	ga = frappe.get_cached_doc("Game Authority", game_authority)
	if ga.status != "Published" or not ga.enabled:
		return []
	return [r.game for r in ga.games if _game_is_open(r.game)]


@frappe.whitelist()
def get_game_options(game, gender=None, student=None, game_authority=None):
	"""Allowed age groups + events for a game."""
	import datetime
	import re
	from frappe.utils import getdate
	from unity_games.utils.helpers import age_years_on

	if not game or not frappe.db.exists("Games", game):
		return {"ages": [], "events": []}
	g = frappe.get_cached_doc("Games", game)
	if not _game_is_open(g):
		return {"ages": [], "events": []}

	def eligible(age_band):
		if not (student and game_authority):
			return True
		dob = frappe.db.get_value("Student", student, "date_of_birth")
		sd = frappe.db.get_value("Game Authority", game_authority, "start_date")
		m = re.search(r"(\d+)", age_band or "")
		if not (dob and sd and m):
			return True
		ref = datetime.date(getdate(sd).year, 12, 31)
		return age_years_on(dob, ref) < int(m.group(1))

	return {
		"ages": [r.age for r in g.age_groups if eligible(r.age)],
		"events": g.allowed_events(gender or None),
	}


@frappe.whitelist()
def get_entry_details_fees(game, age_group, event):
	"""Fee for a (game, age, event) selection on the cart row."""
	from frappe.utils import flt
	if not game or not frappe.db.exists("Games", game):
		return 0
	g = frappe.get_cached_doc("Games", game)
	age_fee = next((flt(r.get("fees")) for r in g.age_groups if r.age == age_group), 0.0)
	ev_fee = next((flt(r.get("fees")) for r in g.events if r.game_event == event), 0.0)
	return age_fee + ev_fee


@frappe.whitelist()
def get_authority_fee_schedule(game_authority):
	"""Base + late-fee tiers for a Game Authority."""
	if not game_authority or not frappe.db.exists("Game Authority", game_authority):
		return []
	ga = frappe.get_cached_doc("Game Authority", game_authority)
	return [
		{
			"is_late": int(r.get("is_late") or 0),
			"amount": float(r.get("amount") or 0),
			"from": r.get("from"),
			"to": r.get("to"),
		}
		for r in (ga.get("registration_fees_details") or [])
		if r.get("from") and r.get("to")
	]


@frappe.whitelist()
def get_published_authorities():
	"""Published + enabled Game Authorities whose window currently includes now()."""
	from frappe.utils import now_datetime
	now = now_datetime()
	return frappe.get_all(
		"Game Authority",
		filters={
			"status": "Published",
			"enabled": 1,
			"docstatus": ["<", 2],   # TODO(prod): set to ["=", 1]
			"start_date": ["<=", now],
			"end_date": [">=", now],
		},
		pluck="name",
		order_by="start_date desc",
	)


@frappe.whitelist()
def get_existing_registrations(student, academic_year=None):
	"""Games the student is already registered for."""
	if not student:
		return []
	filters = {"student": student, "docstatus": ["<", 2]}
	if academic_year:
		filters["academic_year"] = academic_year
	return frappe.get_all(
		"Game Entry",
		filters=filters,
		fields=[
			"name",
			"name_of_game",
			"age_group",
			"events",
			"event_fee",
			"game_authority",
			"academic_year",
			"selection_status",
			"payment_status",
			"docstatus",
		],
		order_by="creation desc",
	)


# ---- Consent OTP --------------------------------------------------------

def _otp_cache_key(student, game_authority, user=None):
	return "unity-games:otp:{u}:{s}:{g}".format(
		u=user or frappe.session.user, s=student, g=game_authority
	)


@frappe.whitelist(methods=["POST"])
def send_consent_otp(student, game_authority):
	"""Send a 4-digit consent OTP to the logged-in guardian; cached 10 min, idempotent."""
	import random
	from edu_quality.common.utils.otp import sms_otp as _eq_sms_otp
	from unity_games.utils.helpers import (
		_row_contact_for,
		get_logged_in_guardian_contact,
		mask_email,
		mask_mobile,
	)

	if not student or not game_authority:
		frappe.throw(frappe._("student and game_authority are required."))
	_assert_own_student(student)
	if not frappe.db.exists("Game Authority", game_authority):
		frappe.throw(frappe._("Unknown Game Authority."))

	contact = get_logged_in_guardian_contact(student)
	if not contact and "System Manager" in frappe.get_roles(frappe.session.user):
		# Admin testing fallback: pick the first guardian on the student.
		rows = frappe.get_all(
			"Student Guardian",
			filters={"parent": student, "parenttype": "Student"},
			pluck="guardian",
		)
		if rows:
			g = rows[0]
			gd = frappe.db.get_value(
				"Guardian", g, ["email_address", "mobile_number"], as_dict=True
			) or {}
			re_, rm_ = _row_contact_for(student, g)
			contact = {
				"guardian": g,
				"email": gd.get("email_address") or re_,
				"mobile": gd.get("mobile_number") or rm_,
			}
	if not contact:
		frappe.throw(frappe._("You are not a registered guardian for this student."))

	email = contact.get("email")
	mobile = contact.get("mobile")
	if not email and not mobile:
		frappe.throw(frappe._(
			"No email or mobile on file for the guardian — please contact the school admin."
		))

	key = _otp_cache_key(student, game_authority)
	cache = frappe.cache()
	otp = cache.get_value(key)
	reused = bool(otp)
	if not otp:
		otp = "".join(str(random.randint(1, 9)) for _ in range(4))
		# Two-step: set + expire — `set_value(..., expires_in_sec=…)` silently drops on this Frappe build.
		cache.set_value(key, otp)
		cache.expire(key, 600)

	if email:
		try:
			frappe.sendmail(
				recipients=[email],
				subject=frappe._("Unity Games — Consent OTP"),
				message=(
					"<p>Your consent OTP for the Unity Games registration is "
					f"<b>{otp}</b>.</p>"
					"<p>This OTP is valid for 10 minutes.</p>"
				),
				now=True,
			)
		except Exception:
			frappe.log_error(title="Unity Games OTP email failed")
	if mobile:
		_eq_sms_otp(mobile, otp)

	resp = {
		"status": "reused" if reused else "sent",
		"guardian": contact.get("guardian"),
		"sent_to": {
			"email": email,
			"email_masked": mask_email(email) if email else "",
			"mobile": mobile,
			"mobile_masked": mask_mobile(mobile) if mobile else "",
		},
	}
	if frappe.conf.get("developer_mode"):
		resp["dev_otp"] = otp
	return resp


@frappe.whitelist(methods=["POST"])
def verify_consent_otp(student, game_authority, otp):
	"""Compare OTP against the cached value (mirrors refund_request.verify_refund_otp)."""
	if not (student and game_authority and otp):
		return False
	return frappe.cache().get_value(
		_otp_cache_key(student, game_authority)
	) == str(otp).strip()
