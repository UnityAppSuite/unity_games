# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

"""Push-only Google Calendar sync for Game Authority."""

import frappe
from frappe import _
from frappe.utils import get_datetime

DOCTYPE = "Game Authority"


def _helpers():
	from frappe.integrations.doctype.google_calendar.google_calendar import (
		format_date_according_to_google_calendar,
		get_conference_data,
		get_google_calendar_object,
	)
	return (
		get_google_calendar_object,
		format_date_according_to_google_calendar,
		get_conference_data,
	)


def _should_sync(doc):
	return bool(
		doc.get("sync_with_google_calendar")
		and not doc.get("pulled_from_google_calendar")
		and doc.get("google_calendar")
		and frappe.db.exists("Google Calendar", {"name": doc.google_calendar})
	)


def _body(doc, fmt):
	event = {
		"summary": doc.title,
		"description": doc.description or "",
		"google_calendar_event": 1,
	}
	event.update(
		fmt(
			doc.all_day,
			get_datetime(doc.start_date),
			get_datetime(doc.end_date) if doc.end_date else None,
		)
	)
	return event


def insert_event_in_google_calendar(doc, method=None):
	if not _should_sync(doc):
		return
	from googleapiclient.errors import HttpError
	get_obj, fmt, conf = _helpers()
	cal, account = get_obj(doc.google_calendar)
	if not account.push_to_google_calendar:
		return
	event = _body(doc, fmt)
	cdv = 0
	if doc.add_video_conferencing:
		event["conferenceData"] = conf(doc)
		cdv = 1
	try:
		created = (
			cal.events()
			.insert(
				calendarId=doc.google_calendar_id,
				body=event,
				conferenceDataVersion=cdv,
				sendUpdates="all",
			)
			.execute()
		)
		frappe.db.set_value(
			DOCTYPE,
			doc.name,
			{
				"google_calendar_event_id": created.get("id"),
				"google_meet_link": created.get("hangoutLink"),
			},
			update_modified=False,
		)
		frappe.msgprint(_("Game Authority synced with Google Calendar."))
	except HttpError as err:
		frappe.throw(
			_("Google Calendar - could not insert event ({0}).").format(err.resp.status)
		)


def update_event_in_google_calendar(doc, method=None):
	if not _should_sync(doc) or doc.modified == doc.creation:
		return
	if not doc.google_calendar_event_id:
		return insert_event_in_google_calendar(doc)
	from googleapiclient.errors import HttpError
	get_obj, fmt, conf = _helpers()
	cal, account = get_obj(doc.google_calendar)
	if not account.push_to_google_calendar:
		return
	try:
		event = (
			cal.events()
			.get(
				calendarId=doc.google_calendar_id,
				eventId=doc.google_calendar_event_id,
			)
			.execute()
		)
		event["summary"] = doc.title
		event["description"] = doc.description or ""
		event["status"] = (
			"cancelled"
			if doc.status in ("Cancelled", "Closed")
			else event.get("status")
		)
		event.update(
			fmt(
				doc.all_day,
				get_datetime(doc.start_date),
				get_datetime(doc.end_date) if doc.end_date else None,
			)
		)
		cdv = 0
		if doc.add_video_conferencing:
			event["conferenceData"] = conf(doc)
			cdv = 1
		updated = (
			cal.events()
			.update(
				calendarId=doc.google_calendar_id,
				eventId=doc.google_calendar_event_id,
				body=event,
				conferenceDataVersion=cdv,
				sendUpdates="all",
			)
			.execute()
		)
		frappe.db.set_value(
			DOCTYPE,
			doc.name,
			{"google_meet_link": updated.get("hangoutLink")},
			update_modified=False,
		)
	except HttpError as err:
		frappe.throw(
			_("Google Calendar - could not update event {0} ({1}).").format(
				doc.name, err.resp.status
			)
		)


def delete_event_from_google_calendar(doc, method=None):
	if not doc.get("google_calendar") or not doc.get("google_calendar_event_id"):
		return
	if not frappe.db.exists(
		"Google Calendar", {"name": doc.google_calendar, "push_to_google_calendar": 1}
	):
		return
	from googleapiclient.errors import HttpError
	get_obj, _fmt, _conf = _helpers()
	cal, _account = get_obj(doc.google_calendar)
	try:
		event = (
			cal.events()
			.get(
				calendarId=doc.google_calendar_id,
				eventId=doc.google_calendar_event_id,
			)
			.execute()
		)
		event["recurrence"] = None
		event["status"] = "cancelled"
		cal.events().update(
			calendarId=doc.google_calendar_id,
			eventId=doc.google_calendar_event_id,
			body=event,
		).execute()
	except HttpError as err:
		frappe.msgprint(
			_("Google Calendar - could not delete event {0} ({1}).").format(
				doc.name, err.resp.status
			)
		)
