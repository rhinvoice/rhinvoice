import { describe, expect, it } from "vitest";

import {
  serverProblems,
  toRequest,
  toValues,
  withSecurity,
  type ServerValues,
} from "@/features/mail/mail-settings-model";
import type { MailServer } from "@/features/shared/mail-api";

const EMPTY: MailServer = {
  configured: false,
  host: "",
  port: 587,
  security: "starttls",
  sender: "",
  sender_name: "",
  username: "",
  password_set: false,
  reply_to: "",
  copy_to_sender: true,
};

const VALID: ServerValues = {
  host: "smtp.example.com",
  port: "587",
  security: "starttls",
  username: "rechnung",
  password: "",
  sender: "rechnung@example.com",
  senderName: "Muster GmbH",
  replyTo: "",
  copyToSender: true,
};

describe("mail server settings", () => {
  it("starts with the company name as sender name", () => {
    expect(toValues(EMPTY, "Muster GmbH")).toEqual({
      ...VALID,
      host: "",
      username: "",
      sender: "",
    });
    const stored = { ...EMPTY, configured: true, sender_name: "", password_set: true };
    expect(toValues(stored, "Muster GmbH").senderName).toBe("");
  });

  it("moves the port with the encryption unless it was set by hand", () => {
    expect(withSecurity(VALID, "tls").port).toBe("465");
    expect(withSecurity({ ...VALID, port: "" }, "none").port).toBe("25");
    expect(withSecurity({ ...VALID, port: "2525" }, "tls")).toEqual({
      ...VALID,
      port: "2525",
      security: "tls",
    });
  });

  it("names what is missing or wrong", () => {
    expect(serverProblems(VALID).size).toBe(0);
    expect(
      Object.fromEntries(
        serverProblems({
          ...VALID,
          host: " ",
          port: "70000",
          sender: "",
          replyTo: "info",
          username: "",
          password: "x",
        }),
      ),
    ).toEqual({
      host: "required",
      port: "port",
      sender: "required",
      replyTo: "email",
      password: "passwordWithoutUser",
    });
    expect(serverProblems({ ...VALID, port: "0", sender: "x" }).get("port")).toBe("port");
    expect(serverProblems({ ...VALID, port: "5a" }).get("port")).toBe("port");
    expect(serverProblems({ ...VALID, sender: "x" }).get("sender")).toBe("email");
    expect(serverProblems({ ...VALID, replyTo: "info@example.com" }).size).toBe(0);
  });

  it("keeps the stored password when the field stays empty", () => {
    expect(toRequest({ ...VALID, host: " smtp.example.com ", senderName: " M " })).toEqual({
      host: "smtp.example.com",
      port: 587,
      security: "starttls",
      username: "rechnung",
      password: null,
      sender: "rechnung@example.com",
      sender_name: "M",
      reply_to: "",
      copy_to_sender: true,
    });
    expect(toRequest({ ...VALID, password: " geheim " }).password).toBe(" geheim ");
  });
});
