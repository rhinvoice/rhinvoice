/** Errors returned by the Rhinvoice API: {"error": {"code", "message", "details"}}. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Readonly<Record<string, string>>;

  constructor(status: number, code: string, message: string, details: Record<string, string> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }

  get isUnauthorized(): boolean {
    return this.status === 401;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringRecord(value: unknown): Record<string, string> {
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).filter(
      (entry): entry is [string, string] => typeof entry[1] === "string",
    ),
  );
}

/** Build an ApiError from any response body, tolerating unexpected shapes. */
export function toApiError(status: number, body: unknown): ApiError {
  const error = isRecord(body) ? body["error"] : undefined;
  if (isRecord(error) && typeof error["code"] === "string") {
    const message = typeof error["message"] === "string" ? error["message"] : error["code"];
    return new ApiError(status, error["code"], message, stringRecord(error["details"]));
  }
  return new ApiError(status, status === 0 ? "network" : "http_error", `HTTP ${status}`);
}
