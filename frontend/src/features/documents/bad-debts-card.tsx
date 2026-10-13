import { useQuery } from "@tanstack/react-query";

import { useI18n } from "@/components/i18n/use-i18n";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { badDebtsQuery } from "@/features/documents/api";
import { companyQuery } from "@/features/shared/company-api";
import { termsFor } from "@/features/shared/country-profile-model";
import { formatMoney } from "@/lib/format";

/**
 * What was written off per year and currency, with the tax contained in it. The
 * country names it (CH/LI "Debitorenverluste", DE/AT "Forderungsausfälle").
 */
export function BadDebtsCard({ year }: { readonly year: number | "all" }) {
  const { t, locale } = useI18n();
  const all = useQuery(badDebtsQuery()).data;
  const profile = useQuery(companyQuery).data?.profile;
  // Like the list above it: one year, or all of them.
  const years = year === "all" ? all : all?.filter((entry) => entry.year === year);
  if (years === undefined || years.length === 0 || profile === undefined) return null;
  const terms = termsFor(profile, locale);
  return (
    <Card aria-labelledby="bad-debts">
      <CardHeader>
        <CardTitle id="bad-debts">{terms.bad_debts}</CardTitle>
        <p className="text-sm text-muted-foreground">{t("badDebts.description")}</p>
      </CardHeader>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("badDebts.year")}</TableHead>
            <TableHead className="hidden text-right sm:table-cell">
              {t("badDebts.writtenOff")}
            </TableHead>
            <TableHead className="hidden text-right sm:table-cell">
              {t("badDebts.recovered")}
            </TableHead>
            <TableHead className="text-right">{t("badDebts.loss")}</TableHead>
            <TableHead className="hidden text-right md:table-cell">{t("badDebts.net")}</TableHead>
            <TableHead className="text-right">{terms.tax_name}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {years.map((entry) => {
            const money = (amount: string) => formatMoney(amount, entry.currency, locale);
            return (
              <TableRow key={`${String(entry.year)}-${entry.currency}`}>
                <TableCell className="tabular-nums">{entry.year}</TableCell>
                <TableCell className="hidden text-right tabular-nums sm:table-cell">
                  {money(entry.written_off)}
                </TableCell>
                <TableCell className="hidden text-right tabular-nums sm:table-cell">
                  {money(entry.recovered)}
                </TableCell>
                <TableCell className="text-right font-medium tabular-nums">
                  {money(entry.loss)}
                </TableCell>
                <TableCell className="hidden text-right tabular-nums md:table-cell">
                  {money(entry.net)}
                </TableCell>
                <TableCell className="text-right tabular-nums">{money(entry.tax)}</TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Card>
  );
}
