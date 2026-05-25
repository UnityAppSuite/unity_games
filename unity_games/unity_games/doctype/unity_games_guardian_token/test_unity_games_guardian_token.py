# Copyright (c) 2026, Aman Kumar and Contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


def _make_guardian(name_suffix):
	gname = f"Test Guardian {name_suffix}"
	existing = frappe.db.get_value("Guardian", {"guardian_name": gname}, "name")
	if existing:
		return existing
		g = frappe.get_doc(
		{"doctype": "Guardian", "guardian_name": gname}
		).insert(ignore_permissions=True)
		return g.name


class TestUnityGamesGuardianToken(FrappeTestCase):
	def test_get_or_create_is_idempotent(self):
		guardian = _make_guardian("TOK1")
		from unity_games.unity_games.doctype.unity_games_guardian_token.unity_games_guardian_token import (
		UnityGamesGuardianToken,
		)

		t1 = UnityGamesGuardianToken.get_or_create(guardian)
		t2 = UnityGamesGuardianToken.get_or_create(guardian)
		self.assertEqual(t1, t2)
		self.assertEqual(len(t1), 20)

	def test_resolve_guardian(self):
		guardian = _make_guardian("TOK2")
		from unity_games.unity_games.doctype.unity_games_guardian_token.unity_games_guardian_token import (
		UnityGamesGuardianToken,
		)

		token = UnityGamesGuardianToken.get_or_create(guardian)
		self.assertEqual(UnityGamesGuardianToken.resolve_guardian(token), guardian)
		self.assertIsNone(UnityGamesGuardianToken.resolve_guardian("bad-token"))

	def test_disabled_token_does_not_resolve(self):
		guardian = _make_guardian("TOK3")
		from unity_games.unity_games.doctype.unity_games_guardian_token.unity_games_guardian_token import (
		UnityGamesGuardianToken,
		)

		token = UnityGamesGuardianToken.get_or_create(guardian)
		name = frappe.db.get_value(
		"Unity Games Guardian Token", {"guardian": guardian}, "name"
		)
		frappe.db.set_value("Unity Games Guardian Token", name, "enabled", 0)
		self.assertIsNone(UnityGamesGuardianToken.resolve_guardian(token))
