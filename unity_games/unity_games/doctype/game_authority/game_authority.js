// Copyright (c) 2026, Aman Kumar and contributors
// For license information, please see license.txt

frappe.ui.form.on("Game Authority", {
	refresh(frm) {
		render_gallery_status(frm);
		set_class_query(frm);
	},

	onload(frm) {
		set_class_query(frm);
	},

	branch(frm) {
		// Selected branch changes which classes are valid → reset Classes.
		if ((frm.doc.classes || []).length) {
			frm.clear_table("classes");
			frm.refresh_field("classes");
			frappe.show_alert(
				__("Classes cleared — they now follow the selected branch.")
			);
		}
		set_class_query(frm);
	},

	upload_images_btn(frm) {
		if (frm.is_new()) {
			frappe.msgprint(__("Save the Game Authority before uploading images."));
			return;
		}
		// Mirrors edu_quality.public.js.event upload pattern.
		new frappe.ui.FileUploader({
			doctype: frm.doctype,
			docname: frm.docname,
			frm: frm,
			restrictions: { allowed_file_types: ["image/*"] },
			multiple: true,
			make_private: false,
			on_success(file_docs) {
				const files = Array.isArray(file_docs) ? file_docs : [file_docs];
				const urls = files.map((f) => f && f.file_url).filter(Boolean);
				if (!urls.length) return;
				frappe.show_alert({
					message: __("Processing images, please wait..."),
					indicator: "blue",
				});
				frappe.call({
					method: "unity_games.utils.gallery_api.add_gallery_images",
					args: {
						game_authority: frm.doc.name,
						file_urls: JSON.stringify(urls),
					},
					callback(r) {
						if (r.message && r.message.status === "SUCCESS") {
							frappe.show_alert({
								message: __("{0} image(s) added", [r.message.added]),
								indicator: "green",
							});
							frm.reload_doc();
							setTimeout(() => render_gallery_status(frm), 800);
						} else {
							frappe.show_alert({
								message: __("Failed to add images to gallery"),
								indicator: "red",
							});
						}
					},
				});
			},
		});
	},

	sync_with_google_calendar(frm) {
		if (!frm.doc.sync_with_google_calendar) {
			frm.set_value("add_video_conferencing", 0);
		}
	},
});

function set_class_query(frm) {
	// Filter the Classes grid's `class` (Program) by the selected branch (School).
	frm.set_query("class", "classes", () => {
		return frm.doc.branch ? { filters: { school: frm.doc.branch } } : {};
	});
}

function render_gallery_status(frm) {
	const wrapper = frm.get_field("gallery_status");
	if (!wrapper || frm.is_new()) {
		wrapper && wrapper.html("");
		return;
	}
	frappe.call({
		method: "unity_games.utils.gallery_api.get_gallery_images",
		args: { game_authority: frm.doc.name },
		callback(r) {
			const m = r.message || { total: 0, published: 0 };
			wrapper.html(
				`<div class="text-muted small">${__("Gallery")}: ` +
				`<b>${m.total}</b> ${__("image(s)")}, ` +
				`<b>${m.published}</b> ${__("published")}</div>`
			);
		},
	});
}
