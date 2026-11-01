import type { BankAccount } from "@/features/shared/company-api";
import type { T } from "@/lib/i18n";

type Account = Pick<
  BankAccount,
  "id" | "currency" | "bank_name" | "holder" | "iban_formatted" | "is_default" | "third_party"
>;

/** The accounts a document in ``currency`` can be paid to; the default first. */
export function accountsFor<A extends Account>(accounts: readonly A[], currency: string): A[] {
  return accounts
    .filter((account) => account.currency === currency)
    .sort((a, b) => Number(b.is_default) - Number(a.is_default));
}

/** Whether the editor offers a choice: only with several accounts in the currency. */
export function offersAccountChoice(accounts: readonly Account[], currency: string): boolean {
  return accountsFor(accounts, currency).length > 1;
}

/** "DE89 3704 …": the first two groups of the IBAN, enough to tell accounts apart. */
export function shortIban(formatted: string): string {
  const groups = formatted.split(" ");
  return groups.length > 2 ? `${groups.slice(0, 2).join(" ")} …` : formatted;
}

/** "Inkasso AG · CH58 0079 … (Drittkonto)": a third party by its name, own accounts by bank. */
export function accountLabel(account: Account, t: T): string {
  const name = account.third_party ? account.holder : account.bank_name;
  const suffixes = [
    account.third_party ? t("documents.bankAccountThirdParty") : null,
    account.is_default ? t("documents.bankAccountDefault") : null,
  ].filter((suffix) => suffix !== null);
  return [`${name} · ${shortIban(account.iban_formatted)}`, ...suffixes].join(" ");
}

/**
 * The choice that still holds: "" (the default) once the account is gone or the
 * document's currency changed. Before the accounts are known the choice stays.
 */
export function validAccountChoice(
  chosen: string,
  accounts: readonly Account[] | undefined,
  currency: string,
): string {
  if (chosen === "" || accounts === undefined) return chosen;
  return accountsFor(accounts, currency).some((account) => account.id === chosen) ? chosen : "";
}
