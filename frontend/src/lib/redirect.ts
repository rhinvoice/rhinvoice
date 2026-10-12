/**
 * Only same-origin paths are accepted as redirect targets (no open redirects).
 * Backslashes and control characters are rejected because URL parsing turns
 * "/\evil.example" into "//evil.example".
 */
export function safeRedirect(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//")) {
    return "/";
  }
  // eslint-disable-next-line no-control-regex -- control characters are exactly what we reject
  if (/[\\\u0000-\u001f\u007f]/.test(value)) {
    return "/";
  }
  return value;
}
