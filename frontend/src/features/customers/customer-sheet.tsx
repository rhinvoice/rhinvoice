import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  customerQuery,
  useCreateCustomer,
  useUpdateCustomer,
  type Customer,
} from "@/features/customers/api";
import { CustomerForm } from "@/features/customers/customer-form";
import {
  customerToForm,
  emptyCustomer,
  formToRequest,
  type CountryCode,
} from "@/features/customers/customer-form-model";

interface CustomerSheetProps {
  /** The customer to edit; null creates one. */
  readonly customerId: string | null;
  /** Prefills the name of a new customer, e.g. what was typed in a search. */
  readonly name?: string;
  readonly defaultCountry: CountryCode;
  /** The saved customer, or null when closed without saving. */
  readonly onDone: (customer: Customer | null) => void;
}

/** The full customer form in a panel from the right; what is behind it stays as it was. */
export function CustomerSheet({
  customerId,
  name = "",
  defaultCountry,
  onDone,
}: CustomerSheetProps) {
  const { t } = useI18n();
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onDone(null);
      }}
    >
      <DialogContent side="right" closeLabel={t("common.close")}>
        <DialogHeader>
          <DialogTitle>
            {customerId === null ? t("customers.new") : t("customers.edit")}
          </DialogTitle>
          <DialogDescription>{t("customers.sheetHint")}</DialogDescription>
        </DialogHeader>
        {customerId === null ? (
          <NewCustomer name={name} defaultCountry={defaultCountry} onDone={onDone} />
        ) : (
          <EditCustomer customerId={customerId} onDone={onDone} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function NewCustomer({
  name,
  defaultCountry,
  onDone,
}: Required<Omit<CustomerSheetProps, "customerId">>) {
  const { t, locale } = useI18n();
  const create = useCreateCustomer();
  return (
    <CustomerForm
      defaultValues={{ ...emptyCustomer(defaultCountry), company_name: name.trim() }}
      submitLabel={t("customers.createAndChoose")}
      onSubmit={async (values) => {
        const customer = await create.mutateAsync(formToRequest(values, locale));
        toast.success(t("customers.created", { name: customer.display_name }));
        onDone(customer);
      }}
    />
  );
}

function EditCustomer({
  customerId,
  onDone,
}: {
  readonly customerId: string;
  readonly onDone: (customer: Customer | null) => void;
}) {
  const { t, locale } = useI18n();
  const query = useQuery(customerQuery(customerId));
  const update = useUpdateCustomer(customerId);
  if (query.data === undefined) {
    return <Skeleton className="h-64 w-full" aria-label={t("app.loading")} />;
  }
  return (
    <CustomerForm
      defaultValues={customerToForm(query.data, locale)}
      onSubmit={async (values) => {
        const customer = await update.mutateAsync(formToRequest(values, locale));
        toast.success(t("common.saved"));
        onDone(customer);
      }}
    />
  );
}
