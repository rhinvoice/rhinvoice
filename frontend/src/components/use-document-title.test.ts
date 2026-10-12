import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useDocumentTitle } from "@/components/use-document-title";

describe("useDocumentTitle", () => {
  it("sets and updates the title", () => {
    const { rerender } = renderHook(
      ({ title }) => {
        useDocumentTitle(title);
      },
      { initialProps: { title: "Kunden · Rhinvoice" } },
    );
    expect(document.title).toBe("Kunden · Rhinvoice");
    rerender({ title: "Artikel · Rhinvoice" });
    expect(document.title).toBe("Artikel · Rhinvoice");
  });
});
