import { BackupCard } from "@/features/backup/backup-card";
import { DashboardPage } from "@/features/dashboard/dashboard-page";
import { OnboardingChecklist } from "@/features/onboarding/onboarding-checklist";

/** The dashboard with the cards of other features (features do not import each other). */
export function OverviewPage({ userName }: { readonly userName: string }) {
  return <DashboardPage userName={userName} top={<OnboardingChecklist />} aside={<BackupCard />} />;
}
