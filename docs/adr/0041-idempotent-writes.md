# 0041 – Idempotent writes

- Status: accepted
- Date: 2026-11-06

## Context
The interface runs each action once per click (#78): a button stays locked until its work is
done. It cannot help when a request reaches the server and its answer is lost, e.g. the Wi-Fi
drops or the computer sleeps. The user sees an error and tries again. Then the same intent
arrives twice, and a document, a payment or a mail would exist twice (#77).

## Decision
- **One key per intent.**
  - **Which requests:** the web client sends an `Idempotency-Key` header, a random UUID, with
    each request that creates, pays, issues, sends or uploads something
    (`useIdempotentMutation`). These are documents and their actions, payments, write-offs,
    files, customers, articles, bank accounts, recurring plans, reminders, mails, text
    templates, import runs and templates, and backup requests.
  - **What one intent is:** the mutation of one page or dialog with the same input.
    - Sent again, e.g. after its answer was lost, it keeps its key.
    - A success ends the intent, and so does other input.
    - So does an answer saying the key will not run its request again: `request_done`,
      `request_unfinished` or `idempotency_key_reused`.
  - **Several requests:** an intent of several requests, such as one per uploaded file, has
    one key per part, the same again when it is retried.
  - **How keys are made:** from `crypto.getRandomValues`, not `crypto.randomUUID()`. Browsers
    offer the latter only on HTTPS and localhost, and Rhinvoice may be reached by plain HTTP
    within a network.
- **The server remembers successful requests for 7 days.**
  - **Where:** a middleware, the innermost (`IdempotencyMiddleware`), stores per user and key
    the SHA-256 of the method, path, query and body, and the answer's status and JSON body.
  - **A request whose key is known gets:**
    - **Same request, answered:** the stored answer again, with `Idempotent-Replayed: true`.
      Nothing runs a second time.
    - **Same key, different request:** 422 `idempotency_key_reused`. This is a client error,
      never a repeat.
    - **Same key, first request still running:** 409 `request_in_progress`.
  - **Why 7 days:** a key only helps while the page holding it is open. 7 days cover a laptop
    closed over a weekend or bridge days with the page still open. 24 hours, the usual
    default, would not. Keeping keys longer would only keep copies of answers longer than
    needed (data minimisation).
- **Only successes are kept.** A 4xx or 5xx frees the key: after a validation error the user
  corrects the form and sends it with the same key, and it runs.
- **Three steps, each committed on its own.**
  1. The key is claimed as "running" before the route runs. One statement inserts it or
     returns the row stored already, so that the primary key (user, key) lets only one of
     two concurrent requests through. Expired keys are deleted in a transaction of their own
     before.
  2. The route runs in its own transaction, as before.
  3. The answer is stored, or the key released on a failure. An answer given in full counts
     although the client had gone by then; that is the case this is for.
- **Nothing is guessed.** If the program stops between steps 2 and 3, the key stays
  "running". After 10 minutes it counts as cut off: a repeat gets 409 `request_unfinished`
  ("It is unclear whether this action went through: please check before you try again"), and
  the client renews its key. A second run that might create a second invoice is worse than
  the question.
- **Scope.**
  - Requests without the header work as before, such as scripts and other API clients.
  - So do requests without a signed-in user: login, setup, password reset.
  - **Never with a key:** requests that carry passwords, codes or keys, or answer with them
    (`/api/auth/`, `/api/backup/setup`, `/api/backup/key`, `/api/mail/server`). Neither a
    fingerprint of their body, which could be guessed offline, nor their answer is stored.
  - **Body size:** bodies up to 25 MB with a declared length are fingerprinted as they arrive
    and kept for the route, beyond 1 MB in a temporary file as Starlette keeps uploads. Larger
    ones are left as they are: the invoice import of up to 200 MB skips the numbers it has
    already.
  - **Incomplete bodies:** a request whose client left before its body was whole does not run,
    as without a key.
  - Only JSON answers up to 1 MB are kept. Others, such as an HTML preview, are kept as
    "done" without their body, and a repeat gets 409 `request_done` instead of a second run.
- **Storage.**
  - Table `idempotency_keys`: user, key, fingerprint, state, start, status, body (bytes).
  - Keys older than 7 days are deleted whenever a key is claimed. No job is needed.
  - Deleting a user deletes their keys.
  - Backups leave the rows out, like `backup_runs`: they are copies, and after a restore old
    keys mean nothing.
- **Desktop setup.** The program refuses a second start of the downloaded setup
  (`setup_running`), since it runs outside the database. When the system did not start it,
  it may be tried again.

## Consequences
- A repeated intent never creates, pays, issues, sends or uploads twice, also across a lost
  answer.
- Every keyed write costs a few small statements. That is negligible next to rendering and
  mail.
- A new action that creates or sends something uses `useIdempotentMutation`, and its e2e
  test triggers it twice.
