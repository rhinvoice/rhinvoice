# Test fixtures

`customers.xls` is an old-format Excel file (BIFF8, as older invoicing programs export it) with
made-up data. It was created with [xlwt](https://pypi.org/project/xlwt/), which is not a
dependency of Rhinvoice:

```bash
uvx --with xlwt python - <<'PY'
import datetime
from pathlib import Path

import xlwt

book = xlwt.Workbook(encoding="utf-8")
sheet = book.add_sheet("Kunden")
date_style = xlwt.easyxf(num_format_str="DD.MM.YYYY")
rows = [
    ["Kundennummer", "Firma", "Straße", "PLZ", "Ort", "Rabatt", "Kunde seit"],
    [
        10001,
        "Bergbahnen Müster AG",
        "Dorfstrasse 1",
        9470,
        "Buchs SG",
        2.5,
        datetime.date(2014, 3, 1),
    ],
    [10002, "Beispiel Treuhand AG", "Städtle 3", 9490, "Vaduz", 0, datetime.date(2019, 11, 30)],
]
for row_index, row in enumerate(rows):
    for column, value in enumerate(row):
        if isinstance(value, datetime.date):
            sheet.write(row_index, column, value, date_style)
        else:
            sheet.write(row_index, column, value)
book.save(str(Path("tests/fixtures/customers.xls")))
PY
```
