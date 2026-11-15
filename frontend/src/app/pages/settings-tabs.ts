export const SETTINGS_TABS = [
  "company",
  "bank-accounts",
  "tax-rates",
  "units",
  "numbering",
  "texts",
  "mail",
  "print",
  "dunning",
  "backup",
  "security",
  "interaction",
] as const;
export type SettingsTab = (typeof SETTINGS_TABS)[number];
