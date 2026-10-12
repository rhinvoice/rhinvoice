export const SETTINGS_TABS = [
  "company",
  "bank-accounts",
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
