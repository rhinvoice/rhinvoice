"""Legal notices printed on documents depending on the tax treatment.

The built-in wording comes from the country profile of the company
(:mod:`rhinvoice.domain.country`), with its legal sources; the company can replace it
per treatment and language in the settings. The notice in force when a document is
issued is frozen with the document.

Not tax advice; the wording can be adjusted in the settings.
"""

from __future__ import annotations

MAX_NOTICE = 500
