import { CircleAlertIcon } from "lucide-react";
import { cloneElement, useId, type ReactElement } from "react";

import { Label } from "@/components/ui/label";
import { cn } from "@/lib/cn";

interface ControlProps {
  readonly id?: string | undefined;
  readonly "aria-describedby"?: string | undefined;
  readonly "aria-invalid"?: boolean | undefined;
}

interface FieldProps {
  readonly label: string;
  readonly children: ReactElement<ControlProps>;
  readonly description?: string | undefined;
  readonly error?: string | undefined;
  readonly optionalLabel?: string | undefined;
  readonly className?: string | undefined;
}

/**
 * Label above the control, help text below; an error replaces the help text
 * and is announced through aria-describedby (see principles.md 4.4).
 */
export function Field({
  label,
  children,
  description,
  error,
  optionalLabel,
  className,
}: FieldProps) {
  const generated = useId();
  const id = children.props.id ?? generated;
  const messageId = `${id}-message`;
  const message = error ?? description;
  const control = cloneElement(children, {
    id,
    "aria-invalid": error === undefined ? undefined : true,
    "aria-describedby": message === undefined ? undefined : messageId,
  });
  return (
    <div className={cn("flex flex-col gap-1.5", className)} data-slot="field">
      <Label htmlFor={id} data-field-label={label}>
        {label}
        {optionalLabel === undefined ? null : (
          <span className="ml-1 font-normal text-muted-foreground">{optionalLabel}</span>
        )}
      </Label>
      {control}
      {message === undefined ? null : (
        <p
          id={messageId}
          className={cn(
            "flex items-start gap-1.5 text-sm",
            error === undefined ? "text-muted-foreground" : "text-destructive",
          )}
        >
          {error === undefined ? null : (
            <CircleAlertIcon className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          )}
          {message}
        </p>
      )}
    </div>
  );
}
