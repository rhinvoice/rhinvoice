import { useI18n } from "@/components/i18n/use-i18n";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useSingleKeyShortcuts } from "@/components/use-single-key-shortcuts";
import { modifierLabel } from "@/lib/shortcuts";

export function InteractionSettings() {
  const { t } = useI18n();
  const [enabled, setEnabled] = useSingleKeyShortcuts();
  return (
    <Card aria-labelledby="interaction-title">
      <CardHeader>
        <CardTitle id="interaction-title">{t("settings.interaction")}</CardTitle>
      </CardHeader>
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <Label htmlFor="single-key-shortcuts">{t("settings.singleKeyShortcuts")}</Label>
          <CardDescription id="single-key-shortcuts-hint">
            {t("settings.singleKeyShortcutsHint", { mod: modifierLabel(navigator.platform) })}
          </CardDescription>
        </div>
        <Switch
          id="single-key-shortcuts"
          checked={enabled}
          onCheckedChange={setEnabled}
          aria-describedby="single-key-shortcuts-hint"
        />
      </div>
    </Card>
  );
}
