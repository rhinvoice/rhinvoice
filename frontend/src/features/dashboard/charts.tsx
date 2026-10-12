import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
  type RefObject,
} from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { niceScale, sparkline } from "@/lib/chart";
import { cn } from "@/lib/cn";
import { formatMoney, formatMonth, formatNumber } from "@/lib/format";

/*
 * Charts of the overview. They are drawn for the eye only (aria-hidden); every
 * chart has a table of the same numbers: hidden for screen readers, or shown
 * instead of the chart (``asTable``) for everyone who prefers exact values.
 */

interface Tip {
  readonly x: number;
  readonly y: number;
  readonly content: ReactNode;
}

/** A tooltip that follows the hovered (or tapped) mark, positioned in the chart's box. */
function useTooltip() {
  const box = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  useEffect(() => {
    if (tip === null) return undefined;
    // A tap elsewhere closes it: touch screens have no "mouse leave".
    const close = (event: PointerEvent) => {
      if (!(event.target instanceof Node) || !box.current?.contains(event.target)) {
        setTip(null);
      }
    };
    document.addEventListener("pointerdown", close);
    return () => {
      document.removeEventListener("pointerdown", close);
    };
  }, [tip]);
  const show = (event: ReactPointerEvent<SVGRectElement>, content: ReactNode) => {
    const outer = box.current?.getBoundingClientRect();
    if (outer === undefined) return;
    const mark = event.currentTarget.getBoundingClientRect();
    setTip({ x: mark.left + mark.width / 2 - outer.left, y: mark.top - outer.top, content });
  };
  const tooltip =
    tip === null ? null : (
      <div
        className="pointer-events-none absolute z-10 -translate-x-1/2 -translate-y-full rounded-md bg-foreground px-2.5 py-1.5 text-xs whitespace-nowrap text-background shadow-md"
        style={{ left: tip.x, top: tip.y + 8 }}
      >
        {tip.content}
      </div>
    );
  return {
    box,
    tooltip,
    show,
    hide: () => {
      setTip(null);
    },
  };
}

/**
 * The rendered width of an element, so charts draw at their real size: text in
 * a scaled SVG would shrink on phones.
 */
function useWidth(element: RefObject<HTMLElement | null>, fallback: number): number {
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const target = element.current;
    if (target === null || typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(([entry]) => {
      if (entry !== undefined && entry.contentRect.width > 0) {
        setWidth(Math.round(entry.contentRect.width));
      }
    });
    observer.observe(target);
    return () => {
      observer.disconnect();
    };
  }, [element]);
  return width;
}

/** A small trend line with a soft area and an emphasised last point, as wide as its box. */
export function Sparkline({ values }: { readonly values: readonly number[] }) {
  const box = useRef<HTMLDivElement>(null);
  const width = useWidth(box, 240);
  const height = 32;
  const shape = sparkline(values, width, height);
  return (
    <div ref={box} className="h-8 w-full text-primary">
      <svg
        aria-hidden="true"
        viewBox={`0 0 ${String(width)} ${String(height)}`}
        className="block h-8 w-full overflow-visible"
      >
        <path d={shape.area} fill="currentColor" fillOpacity="0.12" />
        <path
          d={shape.line}
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle cx={shape.end[0]} cy={shape.end[1]} r="3" fill="currentColor" />
      </svg>
    </div>
  );
}

/** A table of a chart's numbers: hidden for screen readers or shown in its place. */
function ChartTable({
  visible,
  head,
  rows,
}: {
  readonly visible: boolean;
  readonly head: readonly string[];
  readonly rows: readonly (readonly [string, ...string[]])[];
}) {
  return (
    <div className={visible ? "overflow-x-auto" : "sr-only"}>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            {head.map((label, index) => (
              <th
                key={label}
                scope="col"
                className={cn("py-1.5 font-medium", index > 0 && "text-right")}
              >
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, ...values]) => (
            <tr key={label} className="border-b last:border-0">
              <th scope="row" className="py-1.5 text-left font-normal">
                {label}
              </th>
              {values.map((value, index) => (
                <td key={`${label}-${String(index)}`} className="py-1.5 text-right tabular-nums">
                  {value}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const PLOT = { width: 760, height: 260, left: 56, right: 8, top: 12, bottom: 26 };
/** Below this width every second month label is enough. */
const NARROW = 520;

/** Net revenue per month of this year as bars, last year as a dashed line. */
export function YearRevenueChart({
  currency,
  months,
  current,
  previous,
  thisYear,
  lastYear,
  asTable,
}: {
  readonly currency: string;
  readonly months: readonly string[];
  readonly current: readonly (number | null)[];
  readonly previous: readonly number[];
  readonly thisYear: number;
  readonly lastYear: number;
  readonly asTable: boolean;
}) {
  const { t, locale } = useI18n();
  const { box, tooltip, show, hide } = useTooltip();
  const width = useWidth(box, PLOT.width);
  const height = width < NARROW ? 200 : PLOT.height;
  const values = [...current.map((value) => value ?? 0), ...previous];
  // Months with more cancellations than invoices grow below the zero line.
  const above = niceScale(Math.max(0, ...values));
  const lowest = Math.min(0, ...values);
  const below = lowest < 0 ? niceScale(-lowest, 2) : { max: 0, ticks: [0] };
  const range = above.max + below.max;
  const innerWidth = width - PLOT.left - PLOT.right;
  const innerHeight = height - PLOT.top - PLOT.bottom;
  const step = innerWidth / months.length;
  const y = (value: number) => PLOT.top + ((above.max - value) / range) * innerHeight;
  const centre = (index: number) => PLOT.left + step * index + step / 2;
  const lastIndex = current.reduce<number>(
    (last, value, index) => (value === null ? last : index),
    -1,
  );
  const money = (value: number) => formatMoney(value.toFixed(2), currency, locale);
  const ticks = [...below.ticks.slice(1).map((tick) => -tick), ...above.ticks];
  const line = previous
    .map((value, index) => `${index === 0 ? "M" : "L"}${String(centre(index))},${String(y(value))}`)
    .join("");
  return (
    <figure className="flex flex-col gap-3">
      <figcaption className="sr-only">{t("dashboard.revenueIn", { currency })}</figcaption>
      {asTable ? null : (
        <div
          aria-hidden="true"
          className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground"
        >
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-chart-1" />
            {thisYear}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0 w-4 border-t-2 border-dashed border-chart-2" />
            {lastYear}
          </span>
        </div>
      )}
      <div ref={box} className={cn("relative", asTable && "hidden")}>
        <svg
          aria-hidden="true"
          viewBox={`0 0 ${String(width)} ${String(height)}`}
          className="block h-auto w-full overflow-visible"
        >
          {ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={PLOT.left}
                x2={width - PLOT.right}
                y1={y(tick)}
                y2={y(tick)}
                className={tick === 0 ? "stroke-input" : "stroke-border"}
                strokeWidth="1"
              />
              <text
                x={PLOT.left - 8}
                y={y(tick) + 4}
                textAnchor="end"
                className="fill-muted-foreground text-[11px] tabular-nums"
              >
                {formatNumber(String(tick), locale, 0)}
              </text>
            </g>
          ))}
          {months.map((month, index) => {
            const value = current[index] ?? null;
            const barWidth = step * 0.56;
            return (
              <g key={month}>
                {value === null || value === 0 ? null : (
                  <rect
                    x={centre(index) - barWidth / 2}
                    y={y(Math.max(value, 0))}
                    width={barWidth}
                    height={Math.abs(y(value) - y(0))}
                    rx="4"
                    className={
                      value < 0
                        ? "fill-destructive"
                        : index === lastIndex
                          ? "fill-primary"
                          : "fill-chart-1"
                    }
                  />
                )}
                {width < NARROW && index % 2 === 1 ? null : (
                  <text
                    x={centre(index)}
                    y={height - 6}
                    textAnchor="middle"
                    className="fill-muted-foreground text-[11px]"
                  >
                    {formatMonth(month, locale).replace(/\s?\d+$/, "")}
                  </text>
                )}
                <rect
                  x={PLOT.left + step * index}
                  y={PLOT.top}
                  width={step}
                  height={innerHeight}
                  fill="transparent"
                  onPointerLeave={hide}
                  onPointerEnter={(event) => {
                    show(
                      event,
                      <>
                        <strong>{formatMonth(month, locale)}</strong>
                        <br />
                        {thisYear}: {value === null ? "–" : money(value)}
                        <br />
                        {lastYear}: {money(previous[index] ?? 0)}
                      </>,
                    );
                  }}
                />
              </g>
            );
          })}
          <path
            d={line}
            fill="none"
            className="pointer-events-none stroke-chart-2"
            strokeWidth="2"
            strokeDasharray="5 4"
          />
          {previous.map((value, index) => (
            <circle
              key={months[index]}
              cx={centre(index)}
              cy={y(value)}
              r="2.5"
              className="pointer-events-none fill-chart-2"
            />
          ))}
        </svg>
        {tooltip}
      </div>
      <ChartTable
        visible={asTable}
        head={[t("dashboard.month"), String(thisYear), String(lastYear)]}
        rows={months.map((month, index) => [
          formatMonth(month, locale),
          current[index] === null ? "–" : money(current[index] ?? 0),
          money(previous[index] ?? 0),
        ])}
      />
    </figure>
  );
}

const WEEKS = { width: 340, height: 150, top: 20, bottom: 22, side: 4 };

/** Open amounts per week of their due date; the first week also holds what is overdue. */
export function ExpectedPaymentsChart({
  currency,
  weeks,
  asTable,
}: {
  readonly currency: string;
  readonly weeks: readonly { readonly label: string; readonly amount: string }[];
  readonly asTable: boolean;
}) {
  const { t, locale } = useI18n();
  const { box, tooltip, show, hide } = useTooltip();
  const width = useWidth(box, WEEKS.width);
  const values = weeks.map((week) => Number(week.amount));
  const max = Math.max(0, ...values);
  const innerHeight = WEEKS.height - WEEKS.top - WEEKS.bottom;
  const step = (width - 2 * WEEKS.side) / weeks.length;
  const money = (amount: string) => formatMoney(amount, currency, locale);
  return (
    <figure className="flex flex-col gap-2">
      <figcaption className="sr-only">{t("dashboard.expected")}</figcaption>
      <div ref={box} className={cn("relative", asTable && "hidden")}>
        <svg
          aria-hidden="true"
          viewBox={`0 0 ${String(width)} ${String(WEEKS.height)}`}
          className="block h-auto w-full overflow-visible"
        >
          <line
            x1={WEEKS.side}
            x2={width - WEEKS.side}
            y1={WEEKS.top + innerHeight}
            y2={WEEKS.top + innerHeight}
            className="stroke-input"
          />
          {weeks.map((week, index) => {
            const value = values[index] ?? 0;
            const height = max > 0 ? (value / max) * innerHeight : 0;
            const x = WEEKS.side + step * index + step * 0.18;
            const barWidth = step * 0.64;
            return (
              <g key={week.label}>
                {height > 0 ? (
                  <rect
                    x={x}
                    y={WEEKS.top + innerHeight - height}
                    width={barWidth}
                    height={height}
                    rx="4"
                    className={index === 0 ? "fill-primary" : "fill-chart-1"}
                  />
                ) : null}
                <text
                  x={x + barWidth / 2}
                  y={WEEKS.top + innerHeight - height - 5}
                  textAnchor="middle"
                  className="fill-foreground text-[11px] tabular-nums"
                >
                  {value > 0 ? formatNumber(String(Math.round(value)), locale, 0) : ""}
                </text>
                <text
                  x={x + barWidth / 2}
                  y={WEEKS.height - 5}
                  textAnchor="middle"
                  className="fill-muted-foreground text-[11px]"
                >
                  {week.label}
                </text>
                <rect
                  x={WEEKS.side + step * index}
                  y={0}
                  width={step}
                  height={WEEKS.height}
                  fill="transparent"
                  onPointerLeave={hide}
                  onPointerEnter={(event) => {
                    show(event, `${week.label}: ${money(week.amount)}`);
                  }}
                />
              </g>
            );
          })}
        </svg>
        {tooltip}
      </div>
      <ChartTable
        visible={asTable}
        head={[t("dashboard.week"), t("dashboard.amount")]}
        rows={weeks.map((week) => [week.label, money(week.amount)])}
      />
    </figure>
  );
}
