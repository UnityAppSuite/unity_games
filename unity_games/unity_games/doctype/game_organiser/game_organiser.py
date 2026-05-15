# Copyright (c) 2026, Aman Kumar and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GameOrganiser(Document):
	"""Tournament body (CBSE, ZP Pune, Subroto Cup, Walnut Internal).

	Layer 1 master. Naming field: ``name_of_organiser``. Not submittable.
	"""

	pass
