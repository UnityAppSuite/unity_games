# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GameAuthorityImage(Document):
	"""Child of Game Authority. One gallery image.

	Modelled on edu_quality's ``Event Gallery Image``. Rows are appended by
	the "Upload Images" button on the Game Authority form.
	"""

	pass
