import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type MailServer = components["schemas"]["MailServerResponse"];
export type MailServerRequest = components["schemas"]["MailServerRequest"];
export type MailSecurity = MailServer["security"];
export type MailTemplate = components["schemas"]["MailTemplateResponse"];
export type MailKind = MailTemplate["kind"];
export type MailDraft = components["schemas"]["MailDraftResponse"];
export type SendMailRequest = components["schemas"]["SendMailRequest"];

/** Mail settings and templates: managed in the settings, used by the send dialog. */
export const mailKeys = {
  server: ["mail", "server"] as const,
  templates: ["mail", "templates"] as const,
  document: (id: string) => ["mail", "document", id] as const,
  reminder: (id: string) => ["mail", "reminder", id] as const,
};

export const mailServerQuery = queryOptions({
  queryKey: mailKeys.server,
  queryFn: () => unwrap(api.GET("/api/mail/server")),
});

export const mailTemplatesQuery = queryOptions({
  queryKey: mailKeys.templates,
  queryFn: () => unwrap(api.GET("/api/mail/templates")),
});

/** What is sent: a document to its customer, or a reminder of an invoice. */
export type MailSubject =
  | { readonly kind: "document"; readonly id: string }
  | { readonly kind: "reminder"; readonly id: string };

export function mailDraftQuery(subject: MailSubject) {
  return queryOptions({
    queryKey:
      subject.kind === "document" ? mailKeys.document(subject.id) : mailKeys.reminder(subject.id),
    queryFn: () =>
      subject.kind === "document"
        ? unwrap(
            api.GET("/api/documents/{document_id}/mail", {
              params: { path: { document_id: subject.id } },
            }),
          )
        : unwrap(
            api.GET("/api/reminders/{reminder_id}/mail", {
              params: { path: { reminder_id: subject.id } },
            }),
          ),
    // Prepared anew each time: the customer's address or the templates may have changed.
    staleTime: 0,
    gcTime: 0,
  });
}

export function useSendMail(subject: MailSubject) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SendMailRequest) =>
      subject.kind === "document"
        ? unwrap(
            api.POST("/api/documents/{document_id}/mail", {
              params: { path: { document_id: subject.id } },
              body,
            }),
          )
        : unwrap(
            api.POST("/api/reminders/{reminder_id}/mail", {
              params: { path: { reminder_id: subject.id } },
              body,
            }),
          ),
    onSuccess: (document) => {
      // The document's history notes the mail.
      client.setQueryData(["documents", "detail", document.id], document);
      void client.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useSaveMailServer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: MailServerRequest) => unwrap(api.PUT("/api/mail/server", { body })),
    onSuccess: (server) => {
      client.setQueryData(mailKeys.server, server);
    },
  });
}

export function useSendTestMail() {
  return useMutation({
    mutationFn: (to: string) => unwrap(api.POST("/api/mail/test", { body: { to } })),
  });
}

export function useSaveMailTemplate() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: {
      kind: MailKind;
      language: MailTemplate["language"];
      subject: string;
      body: string;
    }) =>
      unwrap(
        api.PUT("/api/mail/templates/{kind}/{language}", {
          params: { path: { kind: request.kind, language: request.language } },
          body: { subject: request.subject, body: request.body },
        }),
      ),
    onSuccess: () => client.invalidateQueries({ queryKey: mailKeys.templates }),
  });
}
