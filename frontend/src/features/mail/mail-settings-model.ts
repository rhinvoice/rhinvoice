import { z } from "zod";

import type { MailSecurity, MailServer, MailServerRequest } from "@/features/shared/mail-api";

export const SECURITIES = ["starttls", "tls", "none"] as const satisfies readonly MailSecurity[];
export const DEFAULT_PORTS: Readonly<Record<MailSecurity, number>> = {
  starttls: 587,
  tls: 465,
  none: 25,
};

export interface ServerValues {
  readonly host: string;
  readonly port: string;
  readonly security: MailSecurity;
  readonly username: string;
  readonly password: string;
  readonly sender: string;
  readonly senderName: string;
  readonly replyTo: string;
  readonly copyToSender: boolean;
}

export type ServerField = "host" | "port" | "sender" | "replyTo" | "password";
export type ServerProblem = "required" | "port" | "email" | "passwordWithoutUser";

export function toValues(server: MailServer, companyName: string): ServerValues {
  return {
    host: server.host,
    port: String(server.port),
    security: server.security,
    username: server.username,
    password: "",
    sender: server.sender,
    senderName: server.configured ? server.sender_name : companyName,
    replyTo: server.reply_to,
    copyToSender: server.copy_to_sender,
  };
}

/** Changing the encryption moves the port along, unless it was set by hand. */
export function withSecurity(values: ServerValues, security: MailSecurity): ServerValues {
  const standard = values.port === String(DEFAULT_PORTS[values.security]) || values.port === "";
  return { ...values, security, port: standard ? String(DEFAULT_PORTS[security]) : values.port };
}

const isEmail = (value: string) => z.email().safeParse(value.trim()).success;

export function serverProblems(values: ServerValues): Map<ServerField, ServerProblem> {
  const found = new Map<ServerField, ServerProblem>();
  if (values.host.trim() === "") found.set("host", "required");
  const port = Number(values.port);
  if (!/^\d+$/.test(values.port.trim()) || port < 1 || port > 65_535) found.set("port", "port");
  if (values.sender.trim() === "") found.set("sender", "required");
  else if (!isEmail(values.sender)) found.set("sender", "email");
  if (values.replyTo.trim() !== "" && !isEmail(values.replyTo)) found.set("replyTo", "email");
  if (values.password !== "" && values.username.trim() === "") {
    found.set("password", "passwordWithoutUser");
  }
  return found;
}

/** An empty password field keeps the stored one. */
export function toRequest(values: ServerValues): MailServerRequest {
  return {
    host: values.host.trim(),
    port: Number(values.port),
    security: values.security,
    username: values.username.trim(),
    password: values.password === "" ? null : values.password,
    sender: values.sender.trim(),
    sender_name: values.senderName.trim(),
    reply_to: values.replyTo.trim(),
    copy_to_sender: values.copyToSender,
  };
}
