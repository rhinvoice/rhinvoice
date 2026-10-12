import { describe, expect, it, vi } from "vitest";

import { applyServerErrors } from "@/features/shared/server-errors";
import { ApiError } from "@/lib/api-error";
import { translatorFor } from "@/lib/i18n";

const t = translatorFor("de-CH");

describe("applyServerErrors", () => {
  it("attaches validation messages and focuses the first field", () => {
    const setError = vi.fn();
    const error = new ApiError(422, "validation_error", "x", {
      iban: "IBAN check digits are wrong",
      other: "y",
    });
    const attached = applyServerErrors(error, setError, t, (field) =>
      field === "iban" ? "iban" : null,
    );
    expect(attached).toBe(true);
    expect(setError).toHaveBeenCalledWith(
      "iban",
      { type: "server", message: "Bitte prüfen Sie diese Angabe (IBAN check digits are wrong)." },
      { shouldFocus: true },
    );
  });

  it("translates number conflicts", () => {
    const setError = vi.fn();
    const error = new ApiError(409, "conflict", "taken", {
      number: "customer number 1 is already taken",
    });
    expect(applyServerErrors(error, setError, t, () => "number")).toBe(true);
    expect(setError).toHaveBeenCalledWith(
      "number",
      { type: "server", message: "Diese Nummer ist bereits vergeben." },
      { shouldFocus: true },
    );
  });

  it("translates business rules with a known code", () => {
    const setError = vi.fn();
    const error = new ApiError(422, "payment_exceeds_open_amount", "x", {
      amount: "the payment exceeds the open amount of CHF 10.00",
    });
    expect(applyServerErrors(error, setError, t, () => "amount")).toBe(true);
    expect(setError).toHaveBeenCalledWith(
      "amount",
      { type: "server", message: "Der Betrag ist höher als der offene Betrag." },
      { shouldFocus: true },
    );
  });

  it("ignores other errors", () => {
    const setError = vi.fn();
    expect(
      applyServerErrors(new ApiError(500, "http_error", "x", { a: "b" }), setError, t, () => "a"),
    ).toBe(false);
    expect(applyServerErrors(new Error("x"), setError, t, () => "a")).toBe(false);
    expect(
      applyServerErrors(
        new ApiError(422, "validation_error", "x", { a: "b" }),
        setError,
        t,
        () => null,
      ),
    ).toBe(false);
    expect(setError).not.toHaveBeenCalled();
  });
});
