// Copyright (c) 2026, Aman Kumar and contributors
// For license information, please see license.txt
//
// Unity Games registration web form.
// On picking a student its existing registrations are pre-filled (read-only);
// new games are added below via the cascading Game / Age / Events selects.
// Consent is captured via a 4-digit OTP to the parent (email + SMS).
// The server (Game Entry) re-validates everything, skips already-registered
// games, and fans the cart out into one immutable record per game.

frappe.ready(function () {
	const wf = frappe.web_form;

	// --- module state ---------------------------------------------------
	let studentGender = "";
	let feeSchedule = [];
	let priorPaid = false;
	let lastSentTo = null;       // { email_masked, mobile_masked }
	let verifiedOtp = "";        // JS mirror — set_value on a read_only Data field is unreliable.
	const existingGames = new Set();
	const OTP_AREA_ID = "unity_consent_otp";

	// Scope all v1 CSS to body.ug-form so nothing leaks to other pages.
	document.body.classList.add("ug-form");

	// ====================================================================
	// Select helpers
	// ====================================================================
	function setSelect(fieldname, values, keep) {
		const f = wf.fields_dict && wf.fields_dict[fieldname];
		if (!f) return;
		f.df.options = [""].concat(values || []).join("\n");
		if (f.refresh) f.refresh();
		const cur = wf.get_value(fieldname);
		if (!keep || !values || values.indexOf(cur) === -1) {
			wf.set_value(fieldname, "");
		}
	}

	// `frappe.web_form.on(fieldname, …)` does NOT reliably fire for Select
	// controls in web forms — bind via event delegation on the static field
	// wrapper so it survives the inner <select> being re-rendered.
	function onSelectChange(fieldname, cb) {
		const f = wf.fields_dict && wf.fields_dict[fieldname];
		if (!f || !f.$wrapper) return;
		const ns = "change.unity_" + fieldname;
		f.$wrapper.off(ns).on(ns, "select, input", function () {
			cb(this.value);
		});
	}

	// ====================================================================
	// Cart grid (no `frm` in web forms => grid reads field.df.data)
	// ====================================================================
	function cartField() {
		return wf.fields_dict && wf.fields_dict["game_entry_details"];
	}

	function cartData() {
		const f = cartField();
		if (!f) return [];
		if (!Array.isArray(f.df.data)) f.df.data = [];
		return f.df.data;
	}

	function lockCartGrid() {
		const f = cartField();
		if (!f || !f.grid) return;
		const grid = f.grid;
		grid.cannot_add_rows = true;
		if (grid.df) grid.df.cannot_add_rows = true;
		(grid.docfields || []).forEach((df) => (df.read_only = 1));
		grid.refresh();
		if (grid.wrapper) {
			grid.wrapper.find(".grid-add-row, .grid-add-multiple-rows").hide();
		}
	}

	function refreshCart() {
		const f = cartField();
		if (f && f.grid) {
			f.grid.df.data = f.df.data;
			f.grid.refresh();
		}
		lockCartGrid();
		paintCartRows();
		renderTotalToPay();
	}

	// Tag each BODY grid row (not the heading) as locked/new for CSS to colour.
	function paintCartRows() {
		const f = cartField();
		if (!f || !f.grid || !f.grid.wrapper) return;
		const data = cartData();
		f.grid.wrapper
			.find(".grid-row")
			.not(".grid-heading-row")
			.each(function () {
				const idx = parseInt($(this).attr("data-idx"), 10);
				const row = data[idx - 1];
				const game = row && row.name_of_game;
				const locked = game && existingGames.has(game) ? "1" : "0";
				$(this).attr("data-ug-locked", locked);
			});
	}

	// MutationObserver: re-paint whenever Frappe re-renders the grid body.
	function startCartObserver() {
		const f = cartField();
		if (!f || !f.grid || !f.grid.wrapper) {
			setTimeout(startCartObserver, 500);
			return;
		}
		const target = f.grid.wrapper.get(0);
		if (!target || target._ugObs) return;
		const obs = new MutationObserver(() => paintCartRows());
		obs.observe(target, { childList: true, subtree: true });
		target._ugObs = obs;

		// Block delete/check on locked rows; capture phase beats Frappe's handler.
		target.addEventListener(
			"click",
			function (ev) {
				const row = ev.target.closest(".grid-row");
				if (!row || row.getAttribute("data-ug-locked") !== "1") return;
				if (ev.target.closest(".grid-delete-row, .row-check")) {
					ev.preventDefault();
					ev.stopPropagation();
					frappe.msgprint(
						__("This game is already registered and paid for. Cancel the registration from the desk if needed.")
					);
				}
			},
			true
		);
	}

	// ====================================================================
	// Fee / total renderers
	// ====================================================================
	// Sum of fees on NEW (non-locked) cart rows + GA base/late if no prior
	// paid carrier exists.
	function renderTotalToPay() {
		const host = document.getElementById("ug-total-to-pay");
		if (!host) return;
		const newRows = (cartData() || []).filter((r) => !existingGames.has(r.name_of_game));
		const eventsSum = newRows.reduce((s, r) => s + (Number(r.fees) || 0), 0);
		if (!newRows.length || (eventsSum <= 0 && !feeSchedule.length)) {
			host.innerHTML = "";
			return;
		}
		// Approximate base/late from the published fee schedule (best-effort UI hint).
		let base = 0;
		let late = 0;
		const today = new Date();
		(feeSchedule || []).forEach((r) => {
			const f = r["from"] ? new Date(r["from"]) : null;
			const t = r["to"] ? new Date(r["to"]) : null;
			if (f && t && f <= today && today <= t) {
				if (r.is_late) late = Number(r.amount) || 0;
				else base = Number(r.amount) || 0;
			}
		});
		// If guardian already paid base for this season, server skips it; UI mirrors via priorPaid.
		const total = eventsSum + (priorPaid ? 0 : base) + late;
		if (total <= 0) {
			host.innerHTML = "";
			return;
		}
		host.innerHTML =
			"<div style='background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;padding:10px 14px;margin:8px 0;font-size:14px;color:#1e3a8a'>" +
			"<b>" + __("Total payable") + ":</b> ₹" + total.toFixed(2) +
			"<span class='text-muted small' style='margin-left:8px'>" +
			__("(charged at the next step)") + "</span></div>";
	}

	// Late-fee tier list shown above the cart (hidden when empty).
	function renderLateFeeNotice(rows) {
		feeSchedule = rows || [];
		renderTotalToPay();
		const host = document.getElementById("ug-late-notice");
		if (!host) return;
		if (!rows || !rows.length) {
			host.innerHTML = "";
			host.style.display = "none";
			return;
		}
		const fmtDate = (s) => (s ? String(s).slice(0, 10) : "");
		const items = rows
			.map(
				(r) =>
					`<li>${r.is_late ? __("Late") : __("Base")} · ${__("From")} ${fmtDate(r["from"])} ${__("to")} ${fmtDate(r["to"])}: <b>₹${Number(r.amount || 0).toFixed(0)}/-</b> ${__("per student per game")}</li>`
			)
			.join("");
		host.style.display = "";
		host.innerHTML = `<h6>${__("Fee schedule")}</h6><ul>${items}</ul>`;
	}

	// ====================================================================
	// Student snapshot + existing registrations
	// ====================================================================
	function loadStudentSnapshot(value) {
		existingGames.clear();
		priorPaid = false;
		const data = cartData();
		data.length = 0;
		refreshCart();

		// Student change invalidates any prior OTP.
		setConsent("");
		lastSentTo = null;
		renderConsentArea("init");

		if (!value) {
			studentGender = "";
			["student_registration_no", "student_name", "date_of_birth", "student_age"].forEach(
				(f) => wf.set_value(f, "")
			);
			return;
		}

		frappe.call({
			method: "unity_games.utils.api.get_student_snapshot",
			args: { student: value },
			callback: (r) => {
				const s = r.message || {};
				studentGender = s.gender || "";
				wf.set_value("student_registration_no", s.registration_no || "");
				wf.set_value("student_name", s.student_name || "");
				wf.set_value("date_of_birth", s.date_of_birth || "");
				wf.set_value("student_age", s.student_age || "");
			},
		});

		frappe.call({
			method: "unity_games.utils.api.get_existing_registrations",
			args: { student: value },
			callback: (r) => {
				const rows = r.message || [];
				const d = cartData();
				d.length = 0;
				priorPaid = rows.some((x) => x.payment_status === "Paid");
				rows.forEach((x, i) => {
					existingGames.add(x.name_of_game);
					d.push({
						doctype: "Game Entry Details",
						name: "existing-" + i + "-" + frappe.utils.get_random(6),
						__islocal: 1,
						__existing: 1,
						name_of_game: x.name_of_game,
						age_group: x.age_group,
						events: x.events,
						fees: x.event_fee || 0,
						idx: d.length + 1,
					});
				});
				refreshCart();
			},
		});
	}

	// ====================================================================
	// Game Authority + cascade
	// ====================================================================
	function onAuthorityChanged(v) {
		setSelect("name_of_game", []);
		setSelect("age_group", []);
		setSelect("events", []);

		// Authority change invalidates any prior OTP too.
		setConsent("");
		lastSentTo = null;
		renderConsentArea("init");
		renderLateFeeNotice([]);
		if (!v) return;

		frappe.call({
			method: "unity_games.utils.api.get_authority_games",
			args: { game_authority: v },
			callback: (r) => setSelect("name_of_game", r.message || []),
		});
		frappe.call({
			method: "unity_games.utils.api.get_authority_fee_schedule",
			args: { game_authority: v },
			callback: (r) => renderLateFeeNotice(r.message || []),
		});
	}

	function onGameChanged(v) {
		setSelect("age_group", []);
		setSelect("events", []);
		if (!v) return;
		frappe.call({
			method: "unity_games.utils.api.get_game_options",
			args: {
				game: v,
				gender: studentGender,
				student: wf.get_value("student"),
				game_authority: wf.get_value("game_authority"),
			},
			callback: (r) => {
				const o = r.message || { ages: [], events: [] };
				setSelect("age_group", o.ages);
				setSelect("events", o.events);
				if (!(o.ages || []).length) {
					frappe.show_alert({
						message: __("No age band is valid for this student in the selected game."),
						indicator: "orange",
					});
				}
			},
		});
	}

	// ====================================================================
	// Add-to-cart
	// ====================================================================
	function addGameToCart() {
		const game = wf.get_value("name_of_game");
		const age = wf.get_value("age_group");
		const ev = wf.get_value("events");
		if (!game || !age || !ev) {
			frappe.msgprint(__("Pick Name of Game, Age Group and Events first."));
			return;
		}
		if (existingGames.has(game)) {
			frappe.msgprint(__("{0} is already registered for this student.", [game]));
			return;
		}
		const data = cartData();
		if (data.some((d) => d.name_of_game === game)) {
			frappe.msgprint(__("{0} is already in the list.", [game]));
			return;
		}
		frappe.call({
			method: "unity_games.utils.api.get_entry_details_fees",
			args: { game: game, age_group: age, event: ev },
			callback: (r) => {
				data.push({
					doctype: "Game Entry Details",
					name: "new-" + frappe.utils.get_random(8),
					__islocal: 1,
					name_of_game: game,
					age_group: age,
					events: ev,
					fees: r.message || 0,
					idx: data.length + 1,
				});
				refreshCart();
				wf.set_value("name_of_game", "");
				wf.set_value("age_group", "");
				wf.set_value("events", "");
				frappe.show_alert({ message: __("Added to list"), indicator: "green" });
			},
		});
	}

	function mountAddButton() {
		const f = wf.fields_dict && wf.fields_dict["events"];
		if (!f || !f.$wrapper || f.$wrapper.find(".unity-add-game").length) return;
		$(
			'<button type="button" class="btn btn-primary btn-sm unity-add-game" ' +
				'style="margin-top:8px">' +
				__("Add Game to List") +
				"</button>"
		)
			.appendTo(f.$wrapper)
			.on("click", addGameToCart);
	}

	// ====================================================================
	// Parent consent via OTP (mirrors edu_quality refund_form)
	// ====================================================================
	function setConsent(otp) {
		verifiedOtp = otp || "";
		wf.set_value("consent_otp", verifiedOtp);
		// Belt-and-braces: poke the doc directly because set_value on a
		// read_only Data field doesn't always persist.
		if (frappe.web_form.doc) frappe.web_form.doc.consent_otp = verifiedOtp;
	}

	function renderConsentArea(stage, msg) {
		// stage: 'init' | 'sent' | 'verified' | 'failed'
		const f = wf.fields_dict && wf.fields_dict["consent_otp_area"];
		if (!f || !f.$wrapper) return;

		let html;
		if (stage === "verified") {
			html =
				"<div class='alert alert-success' style='margin:0'>" +
				"✓ " + __("OTP is verified from the parent and willing to participate.") +
				"</div>";
		} else if (stage === "sent" || stage === "failed") {
			let sentLine = "";
			if (lastSentTo) {
				const parts = [];
				if (lastSentTo.email_masked) parts.push(lastSentTo.email_masked);
				if (lastSentTo.mobile_masked) parts.push(lastSentTo.mobile_masked);
				sentLine = parts.length
					? "<div class='text-muted small' style='margin-top:6px'>" +
					  __("OTP sent to") + " <b>" + parts.join("</b> and <b>") +
					  "</b>. " + __("Valid for 10 minutes.") + "</div>"
					: "";
			}
			const errLine =
				stage === "failed"
					? "<div class='text-danger small' style='margin-top:6px'>" +
					  __("OTP verification failed. Try again.") +
					  "</div>"
					: sentLine;
			html =
				"<div class='form-inline' style='gap:8px;display:flex;align-items:center;flex-wrap:wrap'>" +
				"<input type='text' class='form-control' id='ug-otp-input' maxlength='6' " +
				"placeholder='" + __("Enter OTP") + "' style='max-width:160px'>" +
				"<button type='button' class='btn btn-primary btn-sm' id='ug-otp-verify'>" +
				__("Verify OTP") + "</button>" +
				"<button type='button' class='btn btn-link btn-sm' id='ug-otp-resend'>" +
				__("Resend") + "</button>" +
				"</div>" + errLine;
		} else {
			html =
				"<div class='text-muted small' style='margin-bottom:6px'>" +
				__("A 4-digit OTP will be sent to your email and phone for consent.") +
				"</div>" +
				"<button type='button' class='btn btn-primary btn-sm' id='ug-otp-send'>" +
				__("Send OTP") + "</button>";
		}

		f.$wrapper.html("<div id='" + OTP_AREA_ID + "'>" + html + "</div>");
		f.$wrapper.find("#ug-otp-send").on("click", sendOtp);
		f.$wrapper.find("#ug-otp-resend").on("click", sendOtp);
		f.$wrapper.find("#ug-otp-verify").on("click", verifyOtp);
		if (msg) frappe.show_alert({ message: msg, indicator: "green" });
	}

	function sendOtp() {
		const student = wf.get_value("student");
		const ga = wf.get_value("game_authority");
		if (!student || !ga) {
			frappe.msgprint(__("Pick the Student and Game Authority first."));
			return;
		}
		setConsent("");
		frappe.call({
			method: "unity_games.utils.api.send_consent_otp",
			args: { student: student, game_authority: ga },
			freeze: true,
			freeze_message: __("Sending OTP..."),
			callback: (r) => {
				if (!r.message) return;
				lastSentTo = r.message.sent_to || null;
				if (r.message.dev_otp) {
					console.log("dev_otp:", r.message.dev_otp);
					frappe.show_alert({
						message: "dev_otp: " + r.message.dev_otp,
						indicator: "orange",
					});
				}
				renderConsentArea("sent", __("OTP sent."));
			},
		});
	}

	function verifyOtp() {
		const student = wf.get_value("student");
		const ga = wf.get_value("game_authority");
		const otp = ($("#ug-otp-input").val() || "").trim();
		if (!otp) {
			frappe.msgprint(__("Enter the OTP."));
			return;
		}
		frappe.call({
			method: "unity_games.utils.api.verify_consent_otp",
			args: { student: student, game_authority: ga, otp: otp },
			callback: (r) => {
				if (r.message === true) {
					setConsent(otp);
					renderConsentArea("verified");
				} else {
					setConsent("");
					renderConsentArea("failed");
				}
			},
		});
	}

	// ====================================================================
	// Submit guard
	// ====================================================================
	frappe.web_form.validate = () => {
		const data = cartData();
		const newRows = data.filter((d) => !existingGames.has(d.name_of_game));
		if (!newRows.length) {
			frappe.msgprint(
				__("Add at least one new game (listed ones are already registered).")
			);
			return false;
		}
		// Prefer the JS-side flag; fall back to the doc/control.
		if (
			!verifiedOtp &&
			!wf.get_value("consent_otp") &&
			!(frappe.web_form.doc && frappe.web_form.doc.consent_otp)
		) {
			frappe.msgprint(__("Please verify the OTP before submitting."));
			return false;
		}
		// Final paranoia: make sure the payload carries it.
		if (frappe.web_form.doc) {
			frappe.web_form.doc.consent_otp =
				verifiedOtp ||
				wf.get_value("consent_otp") ||
				frappe.web_form.doc.consent_otp;
		}
		return true;
	};

	// ====================================================================
	// Boot
	// ====================================================================
	frappe.call("unity_games.utils.api.get_my_students").then((r) => {
		const students = r.message || [];
		setSelect("student", students.map((s) => s.name), true);
		if (students.length === 1) {
			wf.set_value("student", students[0].name);
			loadStudentSnapshot(students[0].name);
		}
	});
	frappe.web_form.on("student", (f, v) => loadStudentSnapshot(v));
	onSelectChange("student", (v) => loadStudentSnapshot(v));

	frappe.call("unity_games.utils.api.get_published_authorities").then((r) => {
		setSelect("game_authority", r.message || [], true);
	});
	frappe.web_form.on("game_authority", (f, v) => onAuthorityChanged(v));
	onSelectChange("game_authority", onAuthorityChanged);

	frappe.web_form.on("name_of_game", (f, v) => onGameChanged(v));
	onSelectChange("name_of_game", onGameChanged);

	setTimeout(startCartObserver, 800);
	setTimeout(lockCartGrid, 700);
	setTimeout(mountAddButton, 600);
	setTimeout(() => renderConsentArea("init"), 700);
});
