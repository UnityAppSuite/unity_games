# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

import frappe


def get_context(context):
	"""Web form context."""
	context.no_cache = 1
	context.parents = []
	return context
