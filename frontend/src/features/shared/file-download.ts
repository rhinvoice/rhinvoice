import { toApiError } from "@/lib/api-error";

/** The file name from a Content-Disposition header (filename* wins), or the fallback. */
export function fileNameFromDisposition(header: string | null, fallback: string): string {
  if (header === null) return fallback;
  const extended = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (extended?.[1] !== undefined) {
    try {
      return decodeURIComponent(extended[1]);
    } catch {
      // A malformed name falls through to the plain one.
    }
  }
  const plain = /filename="([^"]*)"/i.exec(header);
  return plain?.[1] ?? fallback;
}

export interface DownloadedFile {
  readonly blob: Blob;
  readonly name: string;
}

/** Load a file (PDF, XML) from the API; failures become ApiErrors with a translated code. */
export async function fetchFile(url: string, fallbackName: string): Promise<DownloadedFile> {
  let response: Response;
  try {
    response = await fetch(url, { credentials: "same-origin" });
  } catch {
    throw toApiError(0, undefined);
  }
  if (!response.ok) {
    throw toApiError(response.status, await response.json().catch(() => undefined));
  }
  return {
    blob: await response.blob(),
    name: fileNameFromDisposition(response.headers.get("content-disposition"), fallbackName),
  };
}

/** Save a loaded file in the browser's downloads. */
export function saveFile(file: DownloadedFile): void {
  const url = URL.createObjectURL(file.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = file.name;
  link.click();
  URL.revokeObjectURL(url);
}
