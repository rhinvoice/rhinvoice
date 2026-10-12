/** Geometry of a simple bar chart with a zero line, as fractions of the plot height. */
export interface Bar {
  /** Distance of the bar's top edge from the top of the plot. */
  readonly top: number;
  readonly height: number;
  readonly negative: boolean;
}

export interface BarLayout {
  /** Position of the zero line from the top of the plot. */
  readonly zero: number;
  readonly bars: readonly Bar[];
}

/**
 * Lay out bars for decimal strings (amounts from the API). Positive values grow
 * up from the zero line, negative ones (e.g. a month with more cancellations
 * than invoices) grow down. Only used for drawing, never for money arithmetic.
 */
export function barLayout(values: readonly string[]): BarLayout {
  const numbers = values.map(Number);
  const max = Math.max(0, ...numbers);
  const min = Math.min(0, ...numbers);
  const range = max - min;
  if (range === 0) {
    return { zero: 1, bars: numbers.map(() => ({ top: 1, height: 0, negative: false })) };
  }
  const zero = max / range;
  return {
    zero,
    bars: numbers.map((value) => {
      const height = Math.abs(value) / range;
      return value < 0
        ? { top: zero, height, negative: true }
        : { top: zero - height, height, negative: false };
    }),
  };
}

export interface Scale {
  /** The top of the axis: a round number at or above the largest value. */
  readonly max: number;
  /** The grid lines from 0 to ``max``. */
  readonly ticks: readonly number[];
}

/**
 * A value axis from 0 with about ``count`` round steps (1, 2, 2.5 or 5 times a
 * power of ten), so grid labels read like 0 · 5'000 · 10'000.
 */
export function niceScale(largest: number, count = 4): Scale {
  if (!(largest > 0)) {
    return { max: 1, ticks: [0, 1] };
  }
  const rough = largest / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  // rough / power lies in [1, 10): the next of 1, 2, 2.5, 5 or 10 gives the step.
  const normalized = rough / power;
  const factor =
    normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 2.5 ? 2.5 : normalized <= 5 ? 5 : 10;
  const step = factor * power;
  const steps = Math.ceil(largest / step - 1e-9);
  return {
    max: steps * step,
    ticks: Array.from({ length: steps + 1 }, (_, index) => index * step),
  };
}

export interface Sparkline {
  /** SVG path of the line. */
  readonly line: string;
  /** SVG path of the area below the line, closed at the bottom. */
  readonly area: string;
  /** The last point, emphasised. */
  readonly end: readonly [number, number];
}

/** A small trend line over ``width`` × ``height``, scaled between its lowest and highest value. */
export function sparkline(values: readonly number[], width: number, height: number): Sparkline {
  const padding = 3;
  const min = Math.min(...values);
  const range = Math.max(...values) - min;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  const points = values.map((value, index): [number, number] => [
    round(index * step),
    round(height - padding - (range === 0 ? 0.5 : (value - min) / range) * (height - 2 * padding)),
  ]);
  const line = points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"}${String(x)},${String(y)}`)
    .join("");
  const last = points.at(-1) ?? [0, height];
  return {
    line,
    area: `${line}L${String(last[0])},${String(height)}L0,${String(height)}Z`,
    end: last,
  };
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
