# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

"""Server API for the Game Authority 'Upload Images' button."""

import json

import frappe
from frappe import _


@frappe.whitelist()
def add_gallery_images(game_authority, file_urls):
	if not game_authority or not file_urls:
		frappe.throw(_("game_authority and file_urls are required."))
	if isinstance(file_urls, str):
		file_urls = json.loads(file_urls)
	doc = frappe.get_doc("Game Authority", game_authority)
	doc.check_permission("write")
	added = 0
	for url in file_urls:
		if url:
			doc.append("images", {"image": url, "publish": 0})
			added += 1
	doc.save()
	frappe.db.commit()
	return {"status": "SUCCESS", "added": added, "total": len(doc.images or [])}


def prune_gallery_row_on_file_trash(doc, method=None):
	"""When a File attached to a Game Authority is deleted, drop the matching Gallery Images row.

	Uses a direct child-table delete (not parent.save()) so we don't fire Game Authority
	on_update — that would re-trigger the Google Calendar sync mid-File-deletion and
	any failure there would roll back the File deletion itself.
	"""
	if doc.attached_to_doctype != "Game Authority" or not doc.attached_to_name or not doc.file_url:
		return
	frappe.db.delete(
		"Game Authority Image",
		{
			"parent": doc.attached_to_name,
			"parenttype": "Game Authority",
			"image": doc.file_url,
		},
	)


@frappe.whitelist()
def get_gallery_images(game_authority):
	if not game_authority:
		frappe.throw(_("game_authority is required."))
	rows = frappe.get_all(
		"Game Authority Image",
		filters={"parent": game_authority, "parenttype": "Game Authority"},
		fields=["name", "image", "image_caption", "publish", "publish_date"],
		order_by="idx asc",
	)
	return {
		"images": rows,
		"total": len(rows),
		"published": sum(1 for r in rows if r.publish),
	}
