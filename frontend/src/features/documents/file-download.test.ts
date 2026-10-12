import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchFile, fileNameFromDisposition, saveFile } from "@/features/documents/file-download";
import { ApiError } from "@/lib/api-error";

describe("fileNameFromDisposition", () => {
  it.each([
    [null, "fallback.pdf"],
    ['inline; filename="Rechnung R1.pdf"', "Rechnung R1.pdf"],
    [
      "attachment; filename=\"Rechnung (Entwurf).pdf\"; filename*=UTF-8''Rechnung%20%28Entwurf%29.pdf",
      "Rechnung (Entwurf).pdf",
    ],
    ["inline; filename*=UTF-8''Gr%C3%BCsse.pdf", "Grüsse.pdf"],
    ["inline; filename*=UTF-8''%E0%A4%A.pdf; filename=\"plain.pdf\"", "plain.pdf"],
    ["inline", "fallback.pdf"],
  ])("%s", (header, expected) => {
    expect(fileNameFromDisposition(header, "fallback.pdf")).toBe(expected);
  });
});

describe("fetchFile", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns the file and its name", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("%PDF-1.7", {
        status: 200,
        headers: { "content-disposition": 'inline; filename="R1.pdf"' },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const file = await fetchFile("/api/documents/1/pdf", "x.pdf");
    expect(file.name).toBe("R1.pdf");
    expect(await file.blob.text()).toBe("%PDF-1.7");
    expect(fetchMock).toHaveBeenCalledWith("/api/documents/1/pdf", { credentials: "same-origin" });
  });

  it("turns API errors and network failures into ApiErrors", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json(
            { error: { code: "unavailable", message: "no", details: {} } },
            { status: 503 },
          ),
        ),
    );
    await expect(fetchFile("/x", "x.pdf")).rejects.toMatchObject({
      status: 503,
      code: "unavailable",
    });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("oops", { status: 502 })));
    await expect(fetchFile("/x", "x.pdf")).rejects.toBeInstanceOf(ApiError);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    await expect(fetchFile("/x", "x.pdf")).rejects.toMatchObject({ code: "network" });
  });
});

describe("saveFile", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("downloads the file under its name", () => {
    const blob = new Blob(["<xml/>"]);
    const create = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:file");
    const revoke = vi.spyOn(URL, "revokeObjectURL").mockReturnValue(undefined);
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockReturnValue(undefined);
    saveFile({ blob, name: "XRechnung R1.xml" });
    expect(create).toHaveBeenCalledWith(blob);
    const link = click.mock.contexts[0] as HTMLAnchorElement;
    expect(link.download).toBe("XRechnung R1.xml");
    expect(link.href).toBe("blob:file");
    expect(revoke).toHaveBeenCalledWith("blob:file");
  });
});
