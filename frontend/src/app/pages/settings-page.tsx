import { useQuery } from "@tanstack/react-query";

import { InteractionSettings } from "@/app/pages/interaction-settings";
import { useI18n } from "@/components/i18n/use-i18n";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDocumentTitle } from "@/components/use-document-title";
import type { User } from "@/features/auth/api";
import { PasswordCard, TotpCard } from "@/features/auth/security-settings";
import { BackupSettings } from "@/features/backup/backup-settings";
import { companyQuery } from "@/features/company/api";
import { BankAccountsSettings } from "@/features/company/bank-accounts-settings";
import { CompanySettings } from "@/features/company/company-settings";
import { PrintLayoutSettings } from "@/features/company/print-layout-settings";
import { DunningSettings } from "@/features/dunning/dunning-settings";
import { MailSettings } from "@/features/mail/mail-settings";
import { NumberingSettings } from "@/features/numbering/numbering-settings";
import { TextsSettings } from "@/features/texts/texts-settings";

import { SETTINGS_TABS, type SettingsTab } from "@/app/pages/settings-tabs";
import { NotInDemo } from "@/features/shared/not-in-demo";

interface SettingsPageProps {
  readonly user: User;
  readonly tab: SettingsTab;
  readonly onTabChange: (tab: SettingsTab) => void;
}

export function SettingsPage({ user, tab, onTabChange }: SettingsPageProps) {
  const { t } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("settings.title") }));
  const company = useQuery(companyQuery);
  const labels: Record<SettingsTab, string> = {
    company: t("settings.tabCompany"),
    "bank-accounts": t("settings.tabBankAccounts"),
    numbering: t("settings.tabNumbering"),
    texts: t("settings.tabTexts"),
    mail: t("settings.tabMail"),
    print: t("settings.tabPrint"),
    dunning: t("settings.tabDunning"),
    backup: t("settings.tabBackup"),
    security: t("settings.tabSecurity"),
    interaction: t("settings.tabInteraction"),
  };
  return (
    <>
      <PageHeader title={t("settings.title")} />
      <Tabs
        value={tab}
        onValueChange={(value) => {
          const next = SETTINGS_TABS.find((candidate) => candidate === value);
          if (next !== undefined) onTabChange(next);
        }}
      >
        <TabsList aria-label={t("settings.title")}>
          {SETTINGS_TABS.map((value) => (
            <TabsTrigger key={value} value={value}>
              {labels[value]}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="company">
          {company.isPending ? (
            <Skeleton className="h-96 max-w-2xl" />
          ) : (
            <CompanySettings company={company.data ?? null} />
          )}
        </TabsContent>
        <TabsContent value="bank-accounts">
          <BankAccountsSettings
            defaultHolder={company.data?.name ?? ""}
            defaultCurrency={company.data?.default_currency ?? "CHF"}
            profile={company.data?.profile}
          />
        </TabsContent>
        <TabsContent value="numbering">
          <NumberingSettings />
        </TabsContent>
        <TabsContent value="texts">
          <TextsSettings />
        </TabsContent>
        <TabsContent value="mail">
          <MailSettings />
        </TabsContent>
        <TabsContent value="print">
          <PrintLayoutSettings />
        </TabsContent>
        <TabsContent value="dunning">
          <DunningSettings />
        </TabsContent>
        <TabsContent value="backup">
          <BackupSettings />
        </TabsContent>
        <TabsContent value="security" className="flex max-w-2xl flex-col gap-4">
          <NotInDemo title={t("settings.changePassword")}>
            <PasswordCard />
          </NotInDemo>
          <NotInDemo title={t("settings.totpTitle")}>
            <TotpCard user={user} />
          </NotInDemo>
        </TabsContent>
        <TabsContent value="interaction" className="max-w-2xl">
          <InteractionSettings />
        </TabsContent>
      </Tabs>
    </>
  );
}
