// Copyright (c) 2026, Aman Kumar and contributors
// For license information, please see license.txt

frappe.ui.form.on("Game Entry", {
	// Intentionally empty — Pattern A (Payment Request intermediary) means payment
	// finalization is event-driven via Easebuzz → PR → on_payment_authorized.
	// Manual reconciliation is no longer needed.
});
