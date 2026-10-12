import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

/** A setting that is on or off, with a label and a hint. */
export function SwitchRow({
  id,
  label,
  hint,
  checked,
  onChange,
}: {
  readonly id: string;
  readonly label: string;
  readonly hint: string;
  readonly checked: boolean;
  readonly onChange: (value: boolean) => void;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div className="flex flex-col gap-1">
        <Label htmlFor={id}>{label}</Label>
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      </div>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        aria-describedby={`${id}-hint`}
      />
    </div>
  );
}
