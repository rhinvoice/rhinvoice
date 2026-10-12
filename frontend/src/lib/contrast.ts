/**
 * WCAG 2 contrast for OKLCH colours (OKLCH → OKLab → linear sRGB → luminance).
 * Matrices by Björn Ottosson, https://bottosson.github.io/posts/oklab/
 */

export interface Oklch {
  readonly l: number;
  readonly c: number;
  readonly h: number;
}

const OKLCH = /^oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*(?:\/\s*[\d.]+\s*)?\)$/;

/** Parse "oklch(L C H)" after substituting var(--name) references from ``variables``. */
export function parseOklch(value: string, variables: Readonly<Record<string, string>>): Oklch {
  const resolved = value.replace(/var\(--([\w-]+)\)/g, (_match, name: string) => {
    const replacement = variables[name];
    if (replacement === undefined) {
      throw new Error(`unknown variable --${name}`);
    }
    return replacement;
  });
  const match = OKLCH.exec(resolved.trim());
  if (match === null) {
    throw new Error(`not an oklch colour: ${value}`);
  }
  return { l: Number(match[1]), c: Number(match[2]), h: Number(match[3]) };
}

function clamp(value: number): number {
  return Math.min(1, Math.max(0, value));
}

/** Linear sRGB channels, clipped to the gamut. */
export function oklchToLinearSrgb({ l, c, h }: Oklch): [number, number, number] {
  const radians = (h * Math.PI) / 180;
  const a = c * Math.cos(radians);
  const b = c * Math.sin(radians);
  const lp = (l + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const mp = (l - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const sp = (l - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    clamp(4.0767416621 * lp - 3.3077115913 * mp + 0.2309699292 * sp),
    clamp(-1.2684380046 * lp + 2.6097574011 * mp - 0.3413193965 * sp),
    clamp(-0.0041960863 * lp - 0.7034186147 * mp + 1.707614701 * sp),
  ];
}

export function relativeLuminance(colour: Oklch): number {
  const [r, g, b] = oklchToLinearSrgb(colour);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrastRatio(first: Oklch, second: Oklch): number {
  const a = relativeLuminance(first);
  const b = relativeLuminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

/** Extract "--name: value;" declarations of one CSS block (e.g. ":root" or ".dark"). */
export function readCustomProperties(css: string, selector: string): Record<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start === -1) {
    throw new Error(`selector ${selector} not found`);
  }
  const end = css.indexOf("\n}", start);
  const block = css.slice(start, end);
  const result: Record<string, string> = {};
  for (const match of block.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    // Both groups always participate in a match.
    result[String(match[1])] = String(match[2]).trim();
  }
  return result;
}
