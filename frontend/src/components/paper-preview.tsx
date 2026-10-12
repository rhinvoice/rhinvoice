import { useEffect, useRef, useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";

/** Width of an A4 page in CSS pixels (210 mm at 96 dpi). */
const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

/** Highlighting for clickable lines, only in the editor. */
const CLICKABLE_LINES = `
tr[data-index] { cursor: pointer; }
tr[data-index]:hover td { background: #eef3fb; }
`;

interface PaperPreviewProps {
  /** The page from the print template; undefined while it is loading. */
  readonly html: string | undefined;
  readonly title: string;
  /** Called with the index of the line clicked in the page (editor only). */
  readonly onLineClick?: (index: number) => void;
  readonly busy?: boolean;
  /** Shown instead of the page while there is nothing to show yet. */
  readonly placeholder?: string | undefined;
  readonly className?: string;
}

/**
 * The document as paper: the HTML of the print template in an isolated frame,
 * scaled to the available width. The frame runs no scripts (sandbox).
 */
export function PaperPreview({
  html,
  title,
  onLineClick,
  busy = false,
  placeholder,
  className,
}: PaperPreviewProps) {
  const { t } = useI18n();
  const box = useRef<HTMLDivElement>(null);
  const frame = useRef<HTMLIFrameElement>(null);
  const [width, setWidth] = useState(PAGE_WIDTH);
  const [height, setHeight] = useState(PAGE_HEIGHT);
  const clickRef = useRef(onLineClick);
  useEffect(() => {
    clickRef.current = onLineClick;
  }, [onLineClick]);

  useEffect(() => {
    const element = box.current;
    if (element === null) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry !== undefined) setWidth(entry.contentRect.width);
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  const onLoad = () => {
    const page = frame.current?.contentDocument;
    if (page === null || page === undefined) return;
    setHeight(Math.max(PAGE_HEIGHT, page.documentElement.scrollHeight));
    if (clickRef.current === undefined) return;
    const style = page.createElement("style");
    style.textContent = CLICKABLE_LINES;
    page.head.append(style);
    page.addEventListener("click", (event) => {
      const row = (event.target as Element | null)?.closest("tr[data-index]");
      const index = Number(row?.getAttribute("data-index"));
      if (row !== null && row !== undefined && Number.isInteger(index)) clickRef.current?.(index);
    });
  };

  const scale = Math.min(1, width / PAGE_WIDTH);
  return (
    <div ref={box} className={cn("w-full", className)}>
      {html === undefined && placeholder !== undefined ? (
        <div
          className="grid place-items-center rounded-sm border border-dashed bg-card/60 p-8 text-center text-sm text-muted-foreground"
          style={{ aspectRatio: `${String(PAGE_WIDTH)} / ${String(PAGE_HEIGHT)}` }}
        >
          {placeholder}
        </div>
      ) : html === undefined ? (
        <Skeleton
          className="w-full"
          style={{ aspectRatio: `${String(PAGE_WIDTH)} / ${String(PAGE_HEIGHT)}` }}
        />
      ) : (
        <div
          className={cn(
            "relative overflow-hidden rounded-sm bg-white shadow-lg ring-1 ring-black/5 transition-opacity",
            busy && "opacity-70",
          )}
          style={{ height: height * scale }}
          aria-busy={busy}
        >
          <iframe
            ref={frame}
            title={title}
            srcDoc={html}
            sandbox="allow-same-origin"
            data-paper
            onLoad={onLoad}
            className="absolute top-0 left-0 origin-top-left border-0"
            style={{ width: PAGE_WIDTH, height, transform: `scale(${String(scale)})` }}
          />
        </div>
      )}
      <span className="sr-only">{t("documents.previewHint")}</span>
    </div>
  );
}
