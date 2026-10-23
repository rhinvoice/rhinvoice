import { useQuery, useQueryClient } from "@tanstack/react-query";
import { UserPlusIcon } from "lucide-react";
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
  /** Offered when the search finds nothing: create a customer with the typed name. */
  readonly onCreate?: ((name: string) => void) | undefined;
  readonly id?: string;
  readonly placeholder?: string;
  readonly "aria-describedby"?: string | undefined;
  readonly "aria-invalid"?: boolean | undefined;
}

/** Search customers by name, number or city; the chosen customer's name stays in the input. */
export function CustomerPicker({
  value,
  onChange,
  onCreate,
  id,
  placeholder,
  ...aria
}: CustomerPickerProps) {
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
  const found = searching ? (options.data?.items ?? []) : [];
  // Only once the search for exactly this text is done and empty.
  const nothingFound =
    searching && text.trim() !== "" && term === text && !options.isFetching && found.length === 0;

  return (
    <Autocomplete
      {...(id === undefined ? {} : { id })}
      {...aria}
      value={text}
      onValueChange={setDraft}
      options={found}
      action={
        onCreate !== undefined && nothingFound
          ? {
              label: (
                <>
                  <UserPlusIcon aria-hidden="true" />
                  {t("documents.createCustomerNamed", { name: text.trim() })}
                </>
              ),
              onSelect: () => {
                onCreate(text.trim());
              },
            }
          : undefined
      }
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
