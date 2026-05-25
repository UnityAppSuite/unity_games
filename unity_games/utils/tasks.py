# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

"""Scheduled tasks."""

import frappe
from frappe.utils import add_days, get_url, getdate

from unity_games.unity_games.doctype.unity_games_guardian_token.unity_games_guardian_token import (
	UnityGamesGuardianToken,
)


def _settings():
	return frappe.get_cached_doc("Unity Games Settings")


def _relevant(today, days_before):
	rows = frappe.get_all(
		"Game Authority",
		filters={
			"send_reminder": 1,
			"status": "Published",
			"enabled": 1,
			"holiday": 0,
			"docstatus": 1,
		},
		fields=["name", "title", "start_date", "end_date"],
	)
	out = []
	for r in rows:
		start, end = getdate(r.start_date), getdate(r.end_date)
		if today == start:
			r["phase"] = "opens today"
		elif today == end:
			r["phase"] = "closes today"
		elif today == add_days(end, -abs(days_before or 1)):
			r["phase"] = f"closes in {abs(days_before or 1)} day(s)"
		else:
			continue
		out.append(r)
	return out


def _coordinator_emails(roles):
	emails = set()
	for role in roles:
		try:
			for u in frappe.get_users_with_role(role):
				if u not in ("Administrator", "Guest"):
					emails.add(u)
		except Exception:
			frappe.log_error(
				f"unity_games reminder: role {role}", "Game Authority Reminder"
			)
	return sorted(emails)


def _notify_coordinators(settings, authorities):
	if not settings.notify_coordinators:
		return
	recipients = _coordinator_emails(settings.coordinator_role_list())
	if not recipients:
		return
	items = "".join(
		f"<li><b>{a.title}</b> — {a.phase} "
		f"({a.start_date} → {a.end_date})</li>"
		for a in authorities
	)
	frappe.sendmail(
		recipients=recipients,
		sender=settings.reminder_sender or None,
		subject=frappe._("Unity Games — registration windows today"),
		message=f"<p>Seasons needing attention:</p><ul>{items}</ul>",
		header=[frappe._("Unity Games Reminder"), "blue"],
	)


def _notify_guardians(settings, authorities):
	if not settings.notify_guardians:
		return
	site = get_url()
	guardians = frappe.get_all(
		"Guardian",
		filters={"user": ["is", "set"], "email_address": ["is", "set"]},
		fields=["name", "email_address"],
	)
	for a in authorities:
		for g in guardians:
			token = UnityGamesGuardianToken.get_or_create(g.name)
			link = (
				f"{site}/api/method/unity_games.utils.api.login_as_guardian"
				f"?h={token}&redirect_to=unity-games"
			)
			frappe.sendmail(
				recipients=[g.email_address],
				sender=settings.reminder_sender or None,
				subject=frappe._("Unity Games — {0} registration").format(a.title),
				message=frappe._(
					"<p>Registration for <b>{0}</b> {1} "
					"({2} to {3}).</p>"
					'<p><a href="{4}">Register your child now</a></p>'
				).format(a.title, a.phase, a.start_date, a.end_date, link),
				header=[frappe._("Unity Games"), "green"],
			)


def send_game_authority_reminders():
	"""Daily entrypoint wired via hooks.py scheduler_events."""
	settings = _settings()
	if not settings.enable_morning_reminder:
		return
	today = getdate()
	authorities = _relevant(today, settings.reminder_days_before_close)
	if not authorities:
		return
	_notify_coordinators(settings, authorities)
	_notify_guardians(settings, authorities)
