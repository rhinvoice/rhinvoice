import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useI18n } from "@/components/i18n/use-i18n";
import { Autocomplete } from "@/components/ui/autocomplete";
import { useDebouncedValue } from "@/components/use-debounced-value";
import {
  customerOptionQuery,
  customerOptionsQuery,
  type CustomerOption,
} from "@/features/documents/api";

interface CustomerPickerProps {
  readonly value: string;
  readonly onChange: (customer: CustomerOption) => void;
  readonly id?: string;
  readonly placeholder?: string;
  readonly "aria-describedby"?: string | undefined;
  readonly "aria-invalid"?: boolean | undefined;
}

/** Search customers by name, number or city; the chosen customer's name stays in the input. */
export function CustomerPicker({ value, onChange, id, placeholder, ...aria }: CustomerPickerProps) {
  const { t } = useI18n();
  const client = useQueryClient();
  const selected = useQuery({ ...customerOptionQuery(value), enabled: value !== "" });
  const selectedName = value === "" ? "" : (selected.data?.display_name ?? "");
  // null: not typing, the input shows the chosen customer.
  const [draft, setDraft] = useState<string | null>(null);
  const text = draft ?? selectedName;
  const term = useDebouncedValue(text, 200);
  const searching = draft !== null;
  const options = useQuery({ ...customerOptionsQuery(term), enabled: searching });

  return (
    <Autocomplete
      {...(id === undefined ? {} : { id })}
      {...aria}
      value={text}
      onValueChange={setDraft}
      options={searching ? (options.data?.items ?? []) : []}
      optionKey={(customer) => customer.id}
      listLabel={t("nav.customers")}
      countLabel={(count) => t("common.results", { count })}
      emptyText={options.isFetching ? t("app.loading") : t("documents.noCustomerFound")}
      placeholder={placeholder ?? t("documents.customerPlaceholder")}
      onSelect={(customer) => {
        // Known already: show the name at once instead of refetching it.
        client.setQueryData(customerOptionQuery(customer.id).queryKey, customer);
        setDraft(null);
        onChange(customer);
      }}
      onBlur={() => {
        // Free text is not a customer: show the chosen one again.
        setDraft(null);
      }}
      renderOption={(customer) => (
        <>
          <span className="font-medium">{customer.display_name}</span>
          <span className="text-xs text-muted-foreground">
            {customer.number} · {customer.address.postal_code} {customer.address.city}
          </span>
        </>
      )}
    />
  );
}
