# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

import datetime
import json
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_datetime, getdate, now_datetime, today

from unity_games.utils.helpers import age_on, age_years_on, slug

SUCCESS_STATUSES = {"completed", "success", "authorized", "paid"}


class GameEntry(Document):
	"""One record per (student, game, academic year)."""

	# ============================================================
	# Lifecycle
	# ============================================================
	def before_insert(self):
		if self.flags.get("_is_fanned_child"):
			self.resolve_pe()
			self.compute_fees()
			return
		self._acquire_submit_lock()
		self._verify_consent_otp()
		self.resolve_pe()
		self.prepare_cart()
		self._apply_idempotency()
		self.compute_fees()

	def autoname(self):
		self.name = "-".join([slug(self.student), slug(self.name_of_game), slug(self.academic_year)])

	def validate(self):
		# Payment finalize bypasses re-validation — the user already paid; window/selection
		# changes after that point must not block the doc from being marked Paid + submitted.
		if self.flags.get("_payment_finalize"):
			return
		self.validate_authority_window()
		for sel in self.flags.get("_cart") or [{
			"name_of_game": self.name_of_game,
			"age_group": self.age_group,
			"events": self.events,
		}]:
			self.validate_selection(sel["name_of_game"], sel["age_group"], sel["events"])
		self.validate_unique()

	def after_insert(self):
		if self.flags.get("_is_fanned_child"):
			return
		try:
			carrier_name = self.payment_parent or self.name
			already = self.existing_games()
			for row in (self.flags.get("_cart") or [])[1:]:
				if row["name_of_game"] in already:
					continue
				child = frappe.new_doc("Game Entry")
				child.update({
					"student": self.student,
					"game_authority": self.game_authority,
					"name_of_game": row["name_of_game"],
					"age_group": row["age_group"],
					"events": row["events"],
					"selection_status": "Applied",
					"payment_parent": carrier_name,
					"is_paid_via_parent": 1,
					"payment_status": "Not Applicable",
				})
				child.flags._cart = [row]
				child.flags._is_fanned_child = True
				child.insert(ignore_permissions=True)
				already.add(row["name_of_game"])
			if self.flags.get("_is_free_rider") or not flt(self.total):
				self.flags.ignore_permissions = True
				self.submit()
				for cname in frappe.get_all(
					"Game Entry",
					filters={"payment_parent": carrier_name, "docstatus": 0, "name": ["!=", self.name]},
					pluck="name",
				):
					ch = frappe.get_doc("Game Entry", cname)
					ch.flags.ignore_permissions = True
					ch.submit()
		finally:
			self._release_submit_lock()

	def before_cancel(self):
		for cname in frappe.get_all(
			"Game Entry",
			filters={"payment_parent": self.name, "docstatus": 1},
			pluck="name",
		):
			frappe.get_doc("Game Entry", cname).cancel()

	# ============================================================
	# Cart
	# ============================================================
	def _raw_cart(self):
		if self.flags.get("_cart") is not None:
			return self.flags._cart
		rows = [
			{"name_of_game": r.name_of_game, "age_group": r.age_group, "events": r.events}
			for r in (self.get("game_entry_details") or []) if r.name_of_game
		]
		if rows:
			return rows
		if self.cart_json:
			try:
				rows = json.loads(self.cart_json) or []
			except (ValueError, TypeError):
				rows = []
			if rows:
				return rows
		if self.name_of_game:
			return [{"name_of_game": self.name_of_game, "age_group": self.age_group, "events": self.events}]
		return []

	def prepare_cart(self):
		seen, cart = set(), []
		for r in self._raw_cart():
			g = r.get("name_of_game")
			if not g or g in seen:
				continue
			seen.add(g)
			cart.append(r)
		already = self.existing_games()
		new_cart = [r for r in cart if r["name_of_game"] not in already]
		if not new_cart:
			frappe.throw(_("All selected games are already registered for {0}.").format(
				self.student_name or self.student
			))
		self.flags._cart = new_cart
		self.cart_json = json.dumps(new_cart)
		first = new_cart[0]
		self.name_of_game = first["name_of_game"]
		self.age_group = first["age_group"]
		self.events = first["events"]
		# Saved record holds no cart rows; remaining rows fan out as siblings.
		self.set("game_entry_details", [])

	def existing_games(self):
		if not self.student or not self.academic_year:
			return set()
		return set(frappe.get_all(
			"Game Entry",
			filters={
				"student": self.student,
				"academic_year": self.academic_year,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
			pluck="name_of_game",
		))

	# ============================================================
	# Program Enrollment + student snapshot
	# ============================================================
	def _target_date(self):
		if self.game_authority:
			sd = frappe.db.get_value("Game Authority", self.game_authority, "start_date")
			if sd:
				return getdate(sd)
		return getdate(today())

	def _academic_year_for(self, ref_date):
		rows = frappe.get_all(
			"Academic Year",
			filters={"year_start_date": ["<=", ref_date], "year_end_date": [">=", ref_date]},
			pluck="name",
			order_by="year_start_date desc",
		)
		return rows[0] if rows else None

	def resolve_pe(self):
		if not self.student:
			return
		ref = self._target_date()
		ay = (
			self.academic_year
			or self._academic_year_for(ref)
			or frappe.defaults.get_global_default("academic_year")
		)
		pe = None
		if ay:
			rows = frappe.get_all(
				"Program Enrollment",
				filters={"student": self.student, "academic_year": ay, "docstatus": 1},
				pluck="name",
			)
			if rows:
				pe = frappe.get_cached_doc("Program Enrollment", rows[0])
		if not pe:
			subs = frappe.get_all(
				"Program Enrollment",
				filters={"student": self.student, "docstatus": 1},
				fields=["name", "academic_year"],
			)
			if len(subs) == 1:
				pe = frappe.get_cached_doc("Program Enrollment", subs[0].name)
			elif len(subs) > 1:
				m = [s for s in subs if s.academic_year == ay]
				if m:
					pe = frappe.get_cached_doc("Program Enrollment", m[0].name)
		if not pe:
			frappe.throw(_(
				"No active Program Enrollment for {0} in {1}. Contact the school admin."
			).format(self.student, ay or _("the current academic year")))

		self.program_enrollment = pe.name
		self.academic_year = pe.academic_year
		self.student_class = pe.program
		# student_division is Link → Student Group; resolve via Student Group Student membership
		# filtered by this PE's program + academic year.
		member_groups = frappe.get_all(
			"Student Group Student",
			filters={"student": self.student, "parenttype": "Student Group"},
			pluck="parent",
		)
		self.student_division = None
		if member_groups:
			sg = frappe.get_all(
				"Student Group",
				filters={
					"name": ["in", member_groups],
					"academic_year": pe.academic_year,
					"program": pe.program,
				},
				pluck="name",
				limit=1,
			)
			self.student_division = sg[0] if sg else None
		# School drives the payment-gateway destination account.
		school = pe.get("school") or frappe.db.get_value("Program", pe.program, "school")
		if not school and self.game_authority:
			school = frappe.db.get_value("Game Authority", self.game_authority, "branch")
		self.school = school or None

		st = frappe.get_cached_doc("Student", self.student)
		self.student_registration_no = st.name
		self.student_name = st.student_name
		self.date_of_birth = st.date_of_birth
		self.student_age = age_on(st.date_of_birth)
		self.branch = st.get("branch") or pe.get("branch") or self.branch or None

	# ============================================================
	# Fees
	# ============================================================
	def _per_game_fee(self):
		if not (self.name_of_game and self.age_group and self.events):
			return 0.0
		g = frappe.get_cached_doc("Games", self.name_of_game)
		age = next((flt(r.get("fees")) for r in g.age_groups if r.age == self.age_group), 0.0)
		ev = next((flt(r.get("fees")) for r in g.events if r.game_event == self.events), 0.0)
		return age + ev

	def _per_game_fee_for(self, row):
		g = frappe.get_cached_doc("Games", row["name_of_game"])
		age = next((flt(r.get("fees")) for r in g.age_groups if r.age == row["age_group"]), 0.0)
		ev = next((flt(r.get("fees")) for r in g.events if r.game_event == row["events"]), 0.0)
		return age + ev

	def _authority_fees(self):
		if not self.game_authority:
			return 0.0, 0.0
		now = now_datetime()
		base = late = 0.0
		for r in self.authority().get("registration_fees_details") or []:
			if not (r.get("from") and r.get("to")):
				continue
			if get_datetime(r.get("from")) <= now <= get_datetime(r.get("to")):
				if r.get("is_late"):
					late = flt(r.get("amount"))
				else:
					base = flt(r.get("amount"))
		return base, late

	def compute_fees(self):
		self.event_fee = self._per_game_fee()
		# Children + free-riders carry no gateway-billed amount; carrier holds the full bill.
		if self.flags.get("_is_fanned_child") or self.flags.get("_is_free_rider"):
			self.registration_fees = 0
			self.late_fee = 0
			self.total = 0
			return
		base, late = self._authority_fees()
		cart = self.flags.get("_cart") or []
		cart_event_total = sum(self._per_game_fee_for(r) for r in cart) if cart else flt(self.event_fee)
		if self.flags.get("_incremental_only"):
			# Re-submission with new games: bill only the new event fees + any newly-applicable late delta.
			prior = frappe.get_cached_doc("Game Entry", self.flags.get("_prior_carrier"))
			incremental_late = max(flt(late) - flt(prior.late_fee), 0)
			self.registration_fees = 0
			self.late_fee = incremental_late
			self.total = flt(cart_event_total) + incremental_late
		else:
			self.registration_fees = base
			self.late_fee = late
			self.total = flt(base) + flt(late) + flt(cart_event_total)
		if self.payment_status == "Paid":
			return
		self.payment_status = "Pending" if flt(self.total) else "Not Applicable"

	# ============================================================
	# Idempotency + locking
	# ============================================================
	_LOCK_TTL = 5

	def _lock_key(self):
		return f"ug:lock:{self.student}:{self.game_authority}"

	def _acquire_submit_lock(self):
		import time
		key = self._lock_key()
		held = frappe.cache().get_value(key)
		try:
			held_at = float(held) if held else 0
		except (TypeError, ValueError):
			held_at = 0
		if held_at and (time.time() - held_at) < self._LOCK_TTL:
			frappe.throw(_("Another guardian is submitting for this student — try again in a moment."))
		frappe.cache().set_value(key, str(time.time()))

	def _release_submit_lock(self):
		try:
			frappe.cache().delete_value(self._lock_key())
		except Exception:
			pass

	def _find_paid_carrier(self):
		name = frappe.db.get_value(
			"Game Entry",
			{
				"student": self.student,
				"game_authority": self.game_authority,
				"payment_parent": ["is", "not set"],
				"payment_status": "Paid",
				"docstatus": ["<", 2],
			},
			"name",
			order_by="creation asc",
		)
		return frappe.get_doc("Game Entry", name) if name else None

	def _apply_idempotency(self):
		prior = self._find_paid_carrier()
		if not prior:
			return
		cart = self.flags.get("_cart") or []
		incremental_late = flt(self._authority_fees()[1]) - flt(prior.late_fee)
		incremental_events = sum(self._per_game_fee_for(r) for r in cart)
		if (incremental_events + max(incremental_late, 0)) > 0:
			self.flags._incremental_only = True
			self.flags._prior_carrier = prior.name
			return
		self.flags._is_free_rider = True
		self.payment_parent = prior.name
		self.is_paid_via_parent = 1
		self.payment_status = "Not Applicable"

	# ============================================================
	# Consent OTP
	# ============================================================
	def _verify_consent_otp(self):
		if self.flags.get("_is_fanned_child"):
			if not self.consent_verified_at:
				self.consent_verified_at = now_datetime()
			return
		if "System Manager" in frappe.get_roles(frappe.session.user):
			if not self.consent_verified_at:
				self.consent_verified_at = now_datetime()
			return
		from unity_games.utils.api import _otp_cache_key
		otp = (self.get("consent_otp") or "").strip()
		key = _otp_cache_key(self.student, self.game_authority)
		if not otp or frappe.cache().get_value(key) != otp:
			frappe.throw(_("Please verify the OTP before submitting."))
		self.consent_verified_at = now_datetime()

	# ============================================================
	# Validation helpers
	# ============================================================
	def authority(self):
		return frappe.get_cached_doc("Game Authority", self.game_authority)

	def student_gender(self):
		if not self.student:
			return None
		return frappe.db.get_value("Student", self.student, "gender")

	def validate_authority_window(self):
		ga = self.authority()
		if ga.status != "Published" or not ga.enabled:
			frappe.throw(_("Registration is not open for {0}.").format(ga.name))
		now = now_datetime()
		if get_datetime(ga.start_date) > now or get_datetime(ga.end_date) < now:
			frappe.throw(_("Registration window for {0} is closed.").format(ga.name))

	def validate_selection(self, name_of_game, age_group, events):
		if not (name_of_game and age_group and events):
			frappe.throw(_("Name of Game, Age Group and Events are required."))
		ga = self.authority()
		if name_of_game not in [r.game for r in ga.games]:
			frappe.throw(_("{0} is not offered in {1}.").format(name_of_game, ga.name))
		game = frappe.get_cached_doc("Games", name_of_game)
		if game.get("last_day_to_register") and get_datetime(game.last_day_to_register) < now_datetime():
			frappe.throw(_("Registration for {0} is closed (last day passed).").format(name_of_game))
		if age_group not in [r.age for r in game.age_groups]:
			frappe.throw(_("Age Group {0} is not allowed for {1}.").format(age_group, name_of_game))
		allowed = game.allowed_events(self.student_gender())
		if events not in allowed:
			frappe.throw(_("Event {0} is not allowed for {1} ({2}).").format(
				events, name_of_game, self.student_gender() or "any gender"
			))
		self.validate_age_band(age_group)

	def validate_age_band(self, age_group):
		m = re.search(r"(\d+)", age_group or "")
		if not m or not self.date_of_birth:
			return
		limit = int(m.group(1))
		event_year = getdate(self.authority().start_date).year
		# Age computed on 31-Dec of the event year.
		ref = datetime.date(event_year, 12, 31)
		if age_years_on(self.date_of_birth, ref) >= limit:
			frappe.throw(_("Student age (as on 31-Dec-{0}) exceeds the {1} band.").format(event_year, age_group))

	def validate_unique(self):
		if not self.is_new():
			return
		if frappe.db.exists(
			"Game Entry",
			{
				"student": self.student,
				"name_of_game": self.name_of_game,
				"academic_year": self.academic_year,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
		):
			frappe.throw(_("{0} is already registered for {1} in {2}.").format(
				self.student_name or self.student, self.name_of_game, self.academic_year
			))

	# ============================================================
	# Payment
	# ============================================================
	def validate_payment(self, data=None):
		"""Mark the carrier Paid, cascade siblings to Not Applicable, create one Payment Entry."""
		if not data:
			return {"status": "pending"}
		if str(data.get("status", "")).lower() not in SUCCESS_STATUSES:
			frappe.log_error(
				title=f"Game Entry validate_payment rejected non-success: {self.name}",
				message=f"status={data.get('status')!r}\nPayload: {data}",
			)
			return {"status": "failed", "message": _("Payment not successful: {0}").format(data.get("status"))}
		if self.payment_status == "Paid" and self.docstatus == 1:
			return {"status": "success", "message": _("Already reconciled")}
		try:
			now = now_datetime()
			amount = data.get("amount") or self.total
			txnid = data.get("txnid") or self.transaction_id
			self.payment_status = "Paid"
			self.payment_completed_at = now
			if txnid:
				self.transaction_id = txnid
			self.flags._payment_finalize = True
			self.save(ignore_permissions=True)
			if self.docstatus == 0:
				self.submit()
			for cname in frappe.get_all("Game Entry", filters={"payment_parent": self.name}, pluck="name"):
				ch = frappe.get_doc("Game Entry", cname)
				ch.payment_status = "Not Applicable"
				ch.flags._payment_finalize = True
				ch.save(ignore_permissions=True)
				if ch.docstatus == 0:
					ch.submit()
			self._create_payment_entry(amount=amount, txnid=txnid)
			frappe.db.commit()
			return {"status": "success", "message": _("Payment validated")}
		except Exception:
			frappe.db.rollback()
			frappe.log_error(
				title=f"Game Entry validate_payment failed: {self.name}",
				message=frappe.get_traceback() + f"\n\nPayload: {data}",
			)
			raise

	def on_payment_authorized(self, status=None, *args, **kwargs):
		"""Frappe Payments hook — invoked by Payment Request after gateway success."""
		if status and status.lower() not in SUCCESS_STATUSES:
			return {"status": "failed", "message": _("Payment failed: {0}").format(status)}
		data = {
			"status": "success",
			"amount": kwargs.get("amount") or self.total,
			"txnid": kwargs.get("transaction_id"),
		}
		return self.validate_payment(data)

	def _create_payment_entry(self, amount, txnid):
		"""Create the Payment Entry; skips with a log if accounting config is missing."""
		try:
			from edu_quality.fees.controllers.fees import get_default_account
			school = self.school
			paid_from = frappe.db.get_value("School", school, "event_account") if school else None
			company = (
				frappe.db.get_value("Account", paid_from, "company") if paid_from else
				frappe.defaults.get_user_default("Company") or frappe.db.get_value("Company", {}, "name")
			)
			if not company:
				return
			c = frappe.db.get_value("Company", company, [
				"default_payment_gateway_account", "default_receivable_account",
				"default_cash_account", "default_bank_account",
				"default_currency", "cost_center",
			], as_dict=True) or {}
			paid_to = (
				get_default_account("Online", company)
				or c.default_payment_gateway_account
				or frappe.db.get_value(
					"Mode of Payment Account",
					{"parent": "Online", "company": company},
					"default_account",
				)
				or frappe.db.get_value(
					"Mode of Payment Account", {"parent": "Online"}, "default_account"
				)
				or c.default_cash_account
				or c.default_bank_account
			)
			if not (paid_from and paid_to):
				frappe.log_error(
					title="Unity Games Payment Entry skipped",
					message=f"Missing paid_from/paid_to for {self.name} (school={school}, company={company}, paid_from={paid_from}, paid_to={paid_to}).",
				)
				return
			pe = frappe.get_doc({
				"doctype": "Payment Entry",
				"payment_type": "Receive",
				"company": company,
				"cost_center": c.cost_center,
				"posting_date": now_datetime().date(),
				"reference_date": now_datetime().date(),
				"party_type": "Student",
				"party": self.student,
				"party_name": self.student_name,
				"paid_from": paid_from,
				"paid_to": paid_to,
				"paid_to_account_currency": c.default_currency,
				"paid_amount": flt(amount),
				"received_amount": flt(amount),
				"source_exchange_rate": 1,
				"target_exchange_rate": 1,
				"mode_of_payment": "Online",
				"reference_no": txnid or self.name,
				"reference_doctype": self.doctype,
				"reference_name": self.name,
				"remarks": f"Unity Games registration {self.name} (txn {txnid or '-'}).",
			})
			pe.insert(ignore_permissions=True)
			pe.submit()
		except Exception:
			frappe.log_error(title="Unity Games create_payment_entry failed", message=frappe.get_traceback())
