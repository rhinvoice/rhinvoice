/**
 * Shared look of text-like form fields (style "Weich", see principles.md 4.4):
 * a soft fill without a full outline, plus a bottom stroke in --input that keeps
 * the field boundary at >= 3:1 (WCAG 1.4.11). Focus shows a 2px ring.
 */
export const fieldClasses = [
  "w-full min-w-0 rounded-md rounded-b-[5px] border border-transparent border-b-input bg-field text-base",
  "transition-[background-color,border-color,box-shadow] duration-150",
  "placeholder:text-muted-foreground hover:bg-field-hover",
  "focus-visible:border-transparent focus-visible:bg-card focus-visible:ring-offset-0",
  "disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
  "aria-invalid:border-destructive aria-invalid:border-b-destructive",
].join(" ");
