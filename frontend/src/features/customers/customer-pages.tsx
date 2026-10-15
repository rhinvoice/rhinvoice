import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { ArchiveIcon, ArchiveRestoreIcon } from "lucide-react";
import type { ReactNode } from "react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentTitle } from "@/components/use-document-title";
import {
  customerQuery,
  useArchiveCustomer,
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
import { BackLink } from "@/features/shared/back-link";
import { FormAlert } from "@/features/shared/form-alert";
import { showUndoToast } from "@/features/shared/undo";
import { useErrorMessage } from "@/features/shared/use-error-message";
import { formatDate } from "@/lib/format";

export function NewCustomerPage({ defaultCountry }: { readonly defaultCountry: CountryCode }) {
  const { t, locale } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("customers.new") }));
  const navigate = useNavigate();
  const create = useCreateCustomer();
  return (
    <>
      <BackLink to="/customers" label={t("customers.title")} />
      <PageHeader title={t("customers.new")} />
      <CustomerForm
        defaultValues={emptyCustomer(defaultCountry)}
        onSubmit={async (values) => {
          const customer = await create.mutateAsync(formToRequest(values, locale));
          toast.success(t("customers.created", { name: customer.display_name }));
          await navigate({ to: "/customers/$customerId", params: { customerId: customer.id } });
        }}
      />
    </>
  );
}

interface CustomerPageProps {
  readonly customerId: string;
  /** The customer's documents; provided by the app, since features stay independent. */
  readonly documents: ReactNode;
}

export function CustomerPage({ customerId, documents }: CustomerPageProps) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const query = useQuery(customerQuery(customerId));
  useDocumentTitle(t("app.pageTitle", { title: query.data?.display_name ?? t("customers.edit") }));
  if (query.isError) {
    return (
      <>
        <BackLink to="/customers" label={t("customers.title")} />
        <FormAlert message={errorMessage(query.error)} />
      </>
    );
  }
  if (query.data === undefined) {
    return (
      <div className="flex max-w-2xl flex-col gap-4" aria-busy="true" aria-label={t("app.loading")}>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }
  return <CustomerEditor customer={query.data} documents={documents} />;
}

function CustomerEditor({
  customer,
  documents,
}: {
  readonly customer: Customer;
  readonly documents: ReactNode;
}) {
  const { t, locale } = useI18n();
  const update = useUpdateCustomer(customer.id);
  const archive = useArchiveCustomer();
  const errorMessage = useErrorMessage();

  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };

  const setArchived = (archived: boolean) => {
    archive.mutate(
      { id: customer.id, archived },
      {
        onSuccess: (changed) => {
          const message = archived ? "customers.archivedToast" : "customers.restoredToast";
          showUndoToast(t(message, { name: changed.display_name }), t("common.undo"), () => {
            archive.mutate({ id: changed.id, archived: !archived }, { onError: fail });
          });
        },
        onError: fail,
      },
    );
  };

  return (
    <>
      <BackLink to="/customers" label={t("customers.title")} />
      <PageHeader
        title={customer.display_name}
        description={t("customers.numberAndSince", {
          number: customer.number,
          since: formatDate(customer.created_at.slice(0, 10), locale),
        })}
        actions={
          customer.archived ? (
            <Button
              variant="outline"
              onClick={() => {
                setArchived(false);
              }}
            >
              <ArchiveRestoreIcon aria-hidden="true" />
              {t("common.restore")}
            </Button>
          ) : (
            <Button
              variant="outline"
              onClick={() => {
                setArchived(true);
              }}
            >
              <ArchiveIcon aria-hidden="true" />
              {t("common.archive")}
            </Button>
          )
        }
      />
      {customer.archived ? (
        <p className="flex items-center gap-2 text-sm">
          <Badge>
            <ArchiveIcon aria-hidden="true" />
            {t("common.archived")}
          </Badge>
          {t("customers.archivedNotice")}
        </p>
      ) : null}
      <div className="grid gap-8 xl:grid-cols-[minmax(0,42rem)_1fr]">
        <CustomerForm
          key={customer.id}
          defaultValues={customerToForm(customer, locale)}
          onSubmit={async (values) => {
            await update.mutateAsync(formToRequest(values, locale));
            toast.success(t("common.saved"));
          }}
        />
        {documents}
      </div>
    </>
  );
}
