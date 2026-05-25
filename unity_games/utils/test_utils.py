# Copyright (c) 2026, Aman Kumar and Contributors
# For license information, please see license.txt

"""Consolidated test suite for the unity_games.utils package."""

import datetime

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, getdate, today

from unity_games.utils import api, gallery_api
from unity_games.utils import google_calendar as gc
from unity_games.utils import helpers as utils
from unity_games.utils import tasks
from unity_games.utils.permissions import get_permission_query_conditions


# Tests for: unity_games/utils/helpers.py
class TestHelpers(FrappeTestCase):
	def test_slug(self):
		self.assertEqual(utils.slug("CBSE Cluster 2026!"), "CBSE-Cluster-2026")
		self.assertEqual(utils.slug("  a--b  "), "a-b")
		self.assertEqual(utils.slug(None), "")

	def test_age_years_on(self):
		dob = datetime.date(2010, 6, 3)
		self.assertEqual(utils.age_years_on(dob, datetime.date(2026, 6, 2)), 15)
		self.assertEqual(utils.age_years_on(dob, datetime.date(2026, 6, 3)), 16)

	def test_age_on_string(self):
		dob = datetime.date(2010, 1, 1)
		s = utils.age_on(dob, datetime.date(2026, 1, 1))
		self.assertEqual(s, "16 Year 0 Months 0 Days")

	def test_cbse_reference_date(self):
		self.assertEqual(
		utils.cbse_age_reference_date(2026), datetime.date(2026, 12, 31)
		)

	def test_age_on_empty(self):
		self.assertEqual(utils.age_on(None), "")


		# Tests for: unity_games/utils/api.py
class TestApi(FrappeTestCase):
	def test_invalid_token_rejected(self):
		with self.assertRaises(frappe.AuthenticationError):
			api.login_as_guardian(h="definitely-not-a-token")

	def test_get_my_students_no_guardian(self):
		frappe.set_user("Administrator")
		# Administrator is not a guardian -> empty.
		self.assertEqual(api.get_my_students(), [])

	def test_get_game_options_unknown(self):
		self.assertEqual(
		api.get_game_options("Nope-Nope"), {"ages": [], "events": []}
		)

	def test_get_authority_games_unknown(self):
		self.assertEqual(api.get_authority_games(None), [])


		# Tests for: unity_games/utils/permissions.py
class TestPermissions(FrappeTestCase):
	def test_privileged_unrestricted(self):
		frappe.set_user("Administrator")
		self.assertEqual(get_permission_query_conditions("Administrator"), "")

	def test_unlinked_user_sees_nothing(self):
		# A fresh user with no Guardian link must be fully scoped out.
		self.assertEqual(get_permission_query_conditions("Guest"), "1=0")


		# Tests for: unity_games/utils/google_calendar.py
class _Doc(dict):
	def get(self, k, default=None):
		return dict.get(self, k, default)


class TestGoogleCalendarGuards(FrappeTestCase):
	def test_should_not_sync_without_flag(self):
		doc = _Doc(sync_with_google_calendar=0, google_calendar="X")
		self.assertFalse(gc._should_sync(doc))

	def test_should_not_sync_when_pulled(self):
		doc = _Doc(
		sync_with_google_calendar=1,
		pulled_from_google_calendar=1,
		google_calendar="X",
		)
		self.assertFalse(gc._should_sync(doc))

	def test_should_not_sync_without_calendar(self):
		doc = _Doc(sync_with_google_calendar=1, google_calendar=None)
		self.assertFalse(gc._should_sync(doc))


		# Tests for: unity_games/utils/tasks.py
class TestReminderTask(FrappeTestCase):
	def test_relevant_filters_by_phase(self):
		# Build a Published season opening today.
		if not frappe.db.exists("Game Organiser", "CBSE"):
			frappe.get_doc(
			{"doctype": "Game Organiser", "name_of_organiser": "CBSE"}
			).insert(ignore_permissions=True)
			if not frappe.db.exists("Age", "Under 19"):
				frappe.get_doc({"doctype": "Age", "age": "Under 19"}).insert(
				ignore_permissions=True
				)
				if not frappe.db.exists("Game Events", "Basketball"):
					frappe.get_doc(
					{"doctype": "Game Events", "game_event": "Basketball"}
					).insert(ignore_permissions=True)
					if not frappe.db.exists("Games", "CBSE-Basketball"):
						frappe.get_doc(
						{
						"doctype": "Games",
						"game_organiser": "CBSE",
						"name_of_game": "Basketball",
						"age_groups": [{"age": "Under 19"}],
						"events": [{"game_event": "Basketball"}],
						}
						).insert(ignore_permissions=True)
						title = "Reminder Phase Season"
						if not frappe.db.exists("Game Authority", title):
							ga = frappe.get_doc(
							{
							"doctype": "Game Authority",
							"organiser": "CBSE",
							"title": title,
							"start_date": today(),
							"end_date": add_days(today(), 10),
							"status": "Draft",
							"enabled": 1,
							"send_reminder": 1,
							"games": [{"game": "CBSE-Basketball"}],
							}
							)
							ga.insert(ignore_permissions=True)
							ga.status = "Published"
							ga.save(ignore_permissions=True)
							ga.submit()

							rel = tasks._relevant(getdate(today()), 1)
							titles = {r.title: r.phase for r in rel}
							self.assertIn(title, titles)
							self.assertEqual(titles[title], "opens today")

	def test_disabled_setting_short_circuits(self):
		s = frappe.get_single("Unity Games Settings")
		s.enable_morning_reminder = 0
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Unity Games Settings")
		# Should simply return without error.
		self.assertIsNone(tasks.send_game_authority_reminders())
		s.enable_morning_reminder = 1
		s.save(ignore_permissions=True)
		frappe.clear_cache(doctype="Unity Games Settings")


		# Tests for: unity_games/utils/gallery_api.py
def _gallery_season(title):
	for dt, kw in (
	("Game Organiser", {"name_of_organiser": "CBSE"}),
	("Age", {"age": "Under 19"}),
	("Game Events", {"game_event": "Basketball"}),
	):
		key = list(kw.values())[0]
		if not frappe.db.exists(dt, key):
			frappe.get_doc({"doctype": dt, **kw}).insert(ignore_permissions=True)
			if not frappe.db.exists("Games", "CBSE-Basketball"):
				frappe.get_doc(
				{
				"doctype": "Games",
				"game_organiser": "CBSE",
				"name_of_game": "Basketball",
				"age_groups": [{"age": "Under 19"}],
				"events": [{"game_event": "Basketball"}],
				}
				).insert(ignore_permissions=True)
				if not frappe.db.exists("Game Authority", title):
					frappe.get_doc(
					{
					"doctype": "Game Authority",
					"organiser": "CBSE",
					"title": title,
					"start_date": today(),
					"end_date": add_days(today(), 10),
					"status": "Draft",
					"games": [{"game": "CBSE-Basketball"}],
					}
					).insert(ignore_permissions=True)
					return title


class TestGalleryApi(FrappeTestCase):
	def test_add_and_get_gallery_images(self):
		frappe.set_user("Administrator")
		ga = _gallery_season("Gallery API Season")
		res = gallery_api.add_gallery_images(ga, ["/files/a.png", "/files/b.png"])
		self.assertEqual(res["status"], "SUCCESS")
		self.assertEqual(res["added"], 2)
		listing = gallery_api.get_gallery_images(ga)
		self.assertEqual(listing["total"], 2)
		self.assertEqual(listing["published"], 0)

	def test_requires_args(self):
		self.assertRaises(
		frappe.ValidationError, gallery_api.add_gallery_images, None, None
		)
