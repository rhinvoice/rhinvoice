import type { TaxRate } from "@/features/shared/tax-rates-api";

function rate(overrides: Partial<TaxRate> & Pick<TaxRate, "id" | "name">): TaxRate {
  return {
    category: "S",
    values: [],
    exemption_reason: "",
    notice: "",
    preset: null,
    hidden: false,
    in_use: false,
    ...overrides,
  };
}

/** The rates of a Swiss company as the API sends them (GET /api/tax-rates). */
export const SWISS_RATES: readonly TaxRate[] = [
  rate({
    id: "rate-standard",
    name: "Normalsatz",
    preset: "standard",
    in_use: true,
    values: [
      { valid_from: "2018-01-01", percent: "7.7" },
      { valid_from: "2024-01-01", percent: "8.1" },
    ],
  }),
  rate({
    id: "rate-reduced",
    name: "Reduzierter Satz",
    preset: "reduced",
    values: [
      { valid_from: "2018-01-01", percent: "2.5" },
      { valid_from: "2024-01-01", percent: "2.6" },
    ],
  }),
  rate({
    id: "rate-zero",
    name: "0 % (steuerbar)",
    category: "Z",
    preset: "zero",
    values: [{ valid_from: "2018-01-01", percent: "0" }],
  }),
  rate({
    id: "rate-exempt",
    name: "Von der Steuer ausgenommen",
    category: "E",
    preset: "exempt",
    exemption_reason: "Steuerbefreite Leistung",
    values: [{ valid_from: "2018-01-01", percent: "0" }],
  }),
  rate({
    id: "rate-old",
    name: "Alter Satz",
    hidden: true,
    in_use: true,
    values: [{ valid_from: "2018-01-01", percent: "8.1" }],
  }),
  rate({
    id: "rate-wine",
    name: "Weinbau",
    notice: "Eigener Hinweis",
    values: [{ valid_from: "2030-01-01", percent: "5" }],
  }),
];

export { rate as taxRate };
