/**
 * Sharing a file through the system's share sheet (Web Share API Level 2).
 *
 * Phones and Safari on macOS can share files; elsewhere there is no share button
 * at all (no fallback: download and e-mail are on the page anyway).
 */

/** The part of ``navigator`` that shares; missing members mean "cannot share". */
export interface ShareTarget {
  readonly canShare?: (data?: ShareData) => boolean;
  readonly share?: (data: ShareData) => Promise<void>;
}

const PDF = "application/pdf";

function defaultTarget(): ShareTarget | undefined {
  return typeof navigator === "undefined" ? undefined : navigator;
}

/** A PDF as a file to share, with its name. */
export function pdfFile(blob: Blob, name: string): File {
  return new File([blob], name, { type: PDF });
}

/** Whether this browser can share PDF files (asked with an empty one). */
export function canSharePdf(target: ShareTarget | undefined = defaultTarget()): boolean {
  if (target?.canShare === undefined || target.share === undefined) return false;
  try {
    return target.canShare({ files: [pdfFile(new Blob([]), "probe.pdf")] });
  } catch {
    return false;
  }
}

/**
 * Open the share sheet with the file. Closing the sheet is no error: it gives
 * "cancelled"; any other failure is thrown.
 */
export async function shareFile(
  file: File,
  title: string,
  target: ShareTarget | undefined = defaultTarget(),
): Promise<"shared" | "cancelled"> {
  if (target?.share === undefined) throw new Error("sharing is not supported");
  try {
    await target.share({ files: [file], title });
  } catch (caught) {
    if (caught instanceof DOMException && caught.name === "AbortError") return "cancelled";
    throw caught;
  }
  return "shared";
}
