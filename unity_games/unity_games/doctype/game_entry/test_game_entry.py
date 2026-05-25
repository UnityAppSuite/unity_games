# Copyright (c) 2026, Aman Kumar and Contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, add_years, today


def _ensure(doctype, name, **extra):
	if name and frappe.db.exists(doctype, name):
		return name
	doc = frappe.get_doc({"doctype": doctype, **extra})
	doc.insert(ignore_permissions=True)
	return doc.name


def _scenario():
	"""Build a full registration scenario and return key names."""
	_ensure("Game Organiser", "CBSE", name_of_organiser="CBSE")
	_ensure("Age", "Under 19", age="Under 19")
	_ensure("Age", "Under 14", age="Under 14")
	_ensure("Game Events", "Basketball", game_event="Basketball")
	_ensure("Game Events", "Chess", game_event="Chess")

	for g, ev in (("Basketball", "Basketball"), ("Chess", "Chess")):
		if not frappe.db.exists("Games", f"CBSE-{g}"):
			frappe.get_doc(
				{
					"doctype": "Games",
					"game_organiser": "CBSE",
					"name_of_game": g,
					"age_groups": [{"age": "Under 19"}],
					"events": [{"game_event": ev}],
				}
			).insert(ignore_permissions=True)

	ay = "2026-27"
	if not frappe.db.exists("Academic Year", ay):
		frappe.get_doc(
			{
				"doctype": "Academic Year",
				"academic_year_name": ay,
				"year_start_date": "2026-04-01",
				"year_end_date": "2027-03-31",
			}
		).insert(ignore_permissions=True)

	program = _ensure("Program", "Std 8", program_name="Std 8")

	student_email = "ge_test_student@example.com"
	student = frappe.db.get_value(
		"Student", {"student_email_id": student_email}, "name"
	)
	if not student:
		st = frappe.get_doc(
			{
				"doctype": "Student",
				"first_name": "Aryan",
				"last_name": "Sharma",
				"student_email_id": student_email,
				"date_of_birth": add_years(today(), -14),
			}
		)
		st.insert(ignore_permissions=True)
		student = st.name

	if not frappe.db.exists(
		"Program Enrollment",
		{"student": student, "academic_year": ay, "docstatus": 1},
	):
		pe = frappe.get_doc(
			{
				"doctype": "Program Enrollment",
				"student": student,
				"program": program,
				"academic_year": ay,
				"enrollment_date": today(),
			}
		)
		pe.insert(ignore_permissions=True)
		pe.submit()

	ga = "CBSE Cluster Test"
	if not frappe.db.exists("Game Authority", ga):
		gad = frappe.get_doc(
			{
				"doctype": "Game Authority",
				"organiser": "CBSE",
				"title": ga,
				"start_date": add_days(today(), -1),
				"end_date": add_days(today(), 30),
				"status": "Draft",
				"enabled": 1,
				"games": [
					{"game": "CBSE-Basketball"},
					{"game": "CBSE-Chess"},
				],
			}
		)
		gad.insert(ignore_permissions=True)
		gad.status = "Published"
		gad.save(ignore_permissions=True)
		gad.submit()

	return frappe._dict(student=student, ay=ay, ga=ga)


class TestGameEntry(FrappeTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.s = _scenario()

	def _entry(self, **over):
		base = {
			"doctype": "Game Entry",
			"student": self.s.student,
			"academic_year": self.s.ay,
			"game_authority": self.s.ga,
			"name_of_game": "CBSE-Basketball",
			"age_group": "Under 19",
			"events": "Basketball",
		}
		base.update(over)
		return frappe.get_doc(base)

	def test_autoname_and_snapshot(self):
		e = self._entry()
		e.insert(ignore_permissions=True)
		self.assertIn("CBSE-Basketball", e.name)
		self.assertTrue(e.name.startswith(self.s.student))
		self.assertIn(self.s.ay, e.name)
		self.assertEqual(e.student_registration_no, self.s.student)
		self.assertEqual(len(e.get("game_entry_details") or []), 0)
		self.assertEqual(e.payment_status, "Not Applicable")

	def test_invalid_game_rejected(self):
		_ensure("Game Events", "Hockey", game_event="Hockey")
		if not frappe.db.exists("Games", "CBSE-Hockey"):
			frappe.get_doc(
				{
					"doctype": "Games",
					"game_organiser": "CBSE",
					"name_of_game": "Hockey",
					"age_groups": [{"age": "Under 19"}],
					"events": [{"game_event": "Hockey"}],
				}
			).insert(ignore_permissions=True)
		e = self._entry(name_of_game="CBSE-Hockey", events="Hockey")
		self.assertRaises(
			frappe.ValidationError, e.insert, ignore_permissions=True
		)

	def test_age_band_strict_reject(self):
		e = self._entry(age_group="Under 14")
		self.assertRaises(
			frappe.ValidationError, e.insert, ignore_permissions=True
		)

	def test_duplicate_rejected(self):
		e1 = self._entry(name_of_game="CBSE-Basketball")
		try:
			e1.insert(ignore_permissions=True)
		except Exception:
			pass
		e2 = self._entry(name_of_game="CBSE-Basketball")
		self.assertRaises(
			frappe.ValidationError, e2.insert, ignore_permissions=True
		)

	def test_multi_game_fan_out(self):
		e = self._entry(name_of_game=None, age_group=None, events=None)
		e.append(
			"game_entry_details",
			{
				"name_of_game": "CBSE-Basketball",
				"age_group": "Under 19",
				"events": "Basketball",
			},
		)
		e.append(
			"game_entry_details",
			{
				"name_of_game": "CBSE-Chess",
				"age_group": "Under 19",
				"events": "Chess",
			},
		)
		e.insert(ignore_permissions=True)
		records = frappe.get_all(
			"Game Entry",
			filters={"student": self.s.student},
			pluck="name_of_game",
		)
		self.assertIn("CBSE-Basketball", records)
		self.assertIn("CBSE-Chess", records)

	def _set_fee_on_game(self, game, ev_fee=0, age_fee=0):
		g = frappe.get_doc("Games", game)
		for r in g.events:
			r.fees = ev_fee
		for r in g.age_groups:
			r.fees = age_fee
		g.save(ignore_permissions=True)

	def test_payment_authorized_marks_paid(self):
		self._set_fee_on_game("CBSE-Chess", ev_fee=100)
		e = self._entry(name_of_game="CBSE-Chess", events="Chess")
		e.insert(ignore_permissions=True)
		self.assertEqual(e.registration_fees, 100)
		self.assertEqual(e.total, 100)
		self.assertEqual(e.payment_status, "Pending")
		e.on_payment_authorized(status="completed")
		self.assertEqual(
			frappe.db.get_value("Game Entry", e.name, "payment_status"), "Paid"
		)

	def test_payment_failed_status(self):
		self._set_fee_on_game("CBSE-Basketball", ev_fee=50)
		e = self._entry(name_of_game="CBSE-Basketball")
		e.insert(ignore_permissions=True)
		res = e.on_payment_authorized(status="failed")
		self.assertEqual(res["status"], "failed")
