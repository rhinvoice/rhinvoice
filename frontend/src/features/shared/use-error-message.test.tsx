import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useErrorMessage } from "@/features/shared/use-error-message";
import { ApiError } from "@/lib/api-error";

describe("useErrorMessage", () => {
  const { result } = renderHook(() => useErrorMessage());
  const message = result.current;

  it("returns null without an error", () => {
    expect(message(null)).toBeNull();
    expect(message(undefined)).toBeNull();
  });

  it("translates known API error codes", () => {
    expect(message(new ApiError(401, "account_locked", "locked"))).toBe(
      "Zu viele Fehlversuche. Das Konto ist für 15 Minuten gesperrt.",
    );
    expect(message(new ApiError(0, "network", "HTTP 0"))).toBe(
      "Keine Verbindung zum Server. Bitte prüfen Sie Ihre Verbindung.",
    );
  });

  it("shows the server message for unknown validation errors", () => {
    expect(message(new ApiError(422, "validation_error", "IBAN is invalid"))).toBe(
      "IBAN is invalid",
    );
  });

  it("adds what a mail server answered", () => {
    expect(
      message(new ApiError(502, "mail_auth_failed", "refused", { server: "535 5.7.8 invalid" })),
    ).toBe(
      "Der Mailserver hat Benutzername oder Passwort abgelehnt. Antwort des Servers: «535 5.7.8 invalid»",
    );
  });

  it("names the refused recipients", () => {
    expect(
      message(new ApiError(502, "mail_partly_refused", "partly", { refused: "b@example.com" })),
    ).toBe(
      "Der Mailserver hat einen Teil der Empfänger abgelehnt; die übrigen haben die E-Mail erhalten (im Verlauf vermerkt). Abgelehnt: b@example.com.",
    );
  });

  it("falls back to a generic message", () => {
    const generic = "Etwas ist schiefgelaufen. Bitte versuchen Sie es erneut.";
    expect(message(new ApiError(500, "http_error", "HTTP 500"))).toBe(generic);
    expect(message(new Error("boom"))).toBe(generic);
  });
});
