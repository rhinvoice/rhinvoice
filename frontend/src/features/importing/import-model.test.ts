import { describe, expect, it } from "vitest";

import {
  MAX_UPLOAD_BYTES,
  MAX_UPLOAD_FILES,
  fieldLabelKey,
  invoiceFiles,
  uploadName,
  uploadProblem,
  fieldOfColumn,
  filterRows,
  importableCount,
  mappingFromTemplate,
  normalizeName,
  problemKey,
  reportCsv,
  templateColumns,
  withColumn,
  type ImportRow,
} from "@/features/importing/import-model";

function row(overrides: Partial<ImportRow>): ImportRow {
  return {
    row: 2,
    status: "new",
    number: "1001",
    name: "Muster AG",
    detail: "3000 Bern",
    problem: null,
    file: null,
    attachments: 0,
    new_customer: false,
    ...overrides,
  };
}

describe("normalizeName", () => {
  it.each([
    ["Kunden-Nr.", "kundennr"],
    [" Straße ", "strasse"],
    ["Ländercode", "laendercode"],
    ["Café", "cafe"],
    ["PLZ/Ort", "plzort"],
  ])("compares %s as %s", (text, expected) => {
    expect(normalizeName(text)).toBe(expected);
  });
});

describe("templates", () => {
  it("map the columns a file has", () => {
    const template = { columns: { number: "Kunden-Nr.", city: "Ort", email: "Mail" } };
    expect(mappingFromTemplate(template, ["kunden nr", "Firma", "ORT"])).toEqual({
      number: 0,
      city: 2,
    });
  });

  it("are saved with the column names", () => {
    expect(templateColumns({ number: 0, city: 2, lost: 9 }, ["KdNr", "Firma", "Ort"])).toEqual({
      number: "KdNr",
      city: "Ort",
    });
  });
});

describe("withColumn", () => {
  it("gives a column a field and takes it from other columns", () => {
    const mapping = { number: 0, city: 1 };
    expect(withColumn(mapping, 2, "city")).toEqual({ number: 0, city: 2 });
    expect(withColumn(mapping, 1, "postal_code")).toEqual({ number: 0, postal_code: 1 });
    expect(withColumn(mapping, 0, null)).toEqual({ city: 1 });
  });

  it("finds the field of a column", () => {
    expect(fieldOfColumn({ number: 0, city: 1 }, 1)).toBe("city");
    expect(fieldOfColumn({ number: 0 }, 3)).toBeNull();
  });
});

describe("rows", () => {
  const rows = [row({}), row({ row: 3, status: "error" }), row({ row: 4, status: "skipped" })];

  it("are filtered by status", () => {
    expect(filterRows(rows, "all")).toBe(rows);
    expect(filterRows(rows, "error").map((r) => r.row)).toEqual([3]);
  });

  it("count what the import saves", () => {
    expect(importableCount({ counts: { new: 2, updated: 3, skipped: 4, error: 5 } })).toBe(5);
  });

  it("never write formulas into the report", () => {
    const csv = reportCsv(
      [
        row({ name: '=HYPERLINK("http://example.com")' }),
        row({ name: "-5" }),
        row({ name: "@SUM(A1)" }),
      ],
      ["Name"],
      (item) => [item.name],
    );
    expect(csv).toBe(
      '\uFEFFName\r\n"\'=HYPERLINK(""http://example.com"")"\r\n\'-5\r\n\'@SUM(A1)\r\n',
    );
  });

  it("are written as CSV for Excel", () => {
    const csv = reportCsv(
      [row({ name: 'Muster; "Bau" AG' }), row({ row: 3, name: "Zeile\nzwei" })],
      ["Zeile", "Name"],
      (item) => [String(item.row), item.name],
    );
    expect(csv).toBe('﻿Zeile;Name\r\n2;"Muster; ""Bau"" AG"\r\n3;"Zeile\nzwei"\r\n');
  });
});

describe("labels", () => {
  it("name import fields, also the domain's price fields", () => {
    expect(fieldLabelKey("postal_code")).toBe("import.field.postal_code");
    expect(fieldLabelKey("prices.EUR")).toBe("import.field.price_eur");
    expect(fieldLabelKey("kind")).toBeNull();
  });

  it("name known problems", () => {
    expect(problemKey("required")).toBe("import.problem.required");
    expect(problemKey("validation_error")).toBeNull();
  });
});

describe("invoice files", () => {
  const file = (path: string, size = 1) => {
    const name = path.split("/").at(-1) ?? path;
    return { name, webkitRelativePath: path.includes("/") ? path : "", size };
  };

  it("sends a file with its folders", () => {
    expect(uploadName(file("IN/2016 CH/Rechnung R1.pdf"))).toBe("IN/2016 CH/Rechnung R1.pdf");
    expect(uploadName(file("Rechnung R1.pdf"))).toBe("Rechnung R1.pdf");
  });

  it("takes PDF and ZIP files only", () => {
    const chosen = [
      file("IN/2016/R1.pdf"),
      file("IN/2016/R2.PDF"),
      file("Archiv.zip"),
      file("IN/2026/zeit/zeit-05-26.png"),
      file("IN/.DS_Store"),
      file("IN/.hidden/R3.pdf"),
      file("__MACOSX/IN/._R4.pdf"),
      file("IN/Liste.xlsx"),
    ];
    expect(invoiceFiles(chosen).map(uploadName)).toEqual([
      "IN/2016/R1.pdf",
      "IN/2016/R2.PDF",
      "Archiv.zip",
    ]);
  });

  it("names what the server would refuse", () => {
    expect(uploadProblem([file("a.pdf", 10)])).toBeNull();
    expect(uploadProblem(Array.from({ length: MAX_UPLOAD_FILES + 1 }, () => file("a.pdf")))).toBe(
      "tooMany",
    );
    expect(uploadProblem([file("a.pdf", MAX_UPLOAD_BYTES), file("b.pdf", 1)])).toBe("tooLarge");
  });

  it("names the fields and problems of invoices", () => {
    expect(fieldLabelKey("total")).toBe("import.field.total_amount");
    expect(fieldLabelKey("net")).toBe("import.field.net_amount");
    expect(fieldLabelKey("customer_name")).toBe("import.field.customer_name");
    expect(problemKey("non_positive_total")).toBe("import.problem.non_positive_total");
  });
});
