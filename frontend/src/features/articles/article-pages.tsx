import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "@tanstack/react-router";
import { ArchiveIcon, ArchiveRestoreIcon, ArrowLeftIcon } from "lucide-react";
import { toast } from "sonner";

import { useI18n } from "@/components/i18n/use-i18n";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDocumentTitle } from "@/components/use-document-title";
import {
  articleQuery,
  useArchiveArticle,
  useCreateArticle,
  useUpdateArticle,
  type Article,
} from "@/features/articles/api";
import { ArticleForm } from "@/features/articles/article-form";
import { articleToForm, emptyArticle, formToRequest } from "@/features/articles/article-form-model";
import { FormAlert } from "@/features/shared/form-alert";
import { useErrorMessage } from "@/features/shared/use-error-message";

import { showUndoToast } from "@/features/shared/undo";

function BackLink() {
  const { t } = useI18n();
  return (
    <Link
      to="/articles"
      className="inline-flex min-h-6 w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
    >
      <ArrowLeftIcon className="size-4" aria-hidden="true" />
      {t("articles.title")}
    </Link>
  );
}

export function NewArticlePage() {
  const { t, locale } = useI18n();
  useDocumentTitle(t("app.pageTitle", { title: t("articles.new") }));
  const navigate = useNavigate();
  const create = useCreateArticle();
  return (
    <>
      <BackLink />
      <PageHeader title={t("articles.new")} />
      <ArticleForm
        defaultValues={emptyArticle()}
        onSubmit={async (values) => {
          const article = await create.mutateAsync(formToRequest(values, locale));
          toast.success(t("articles.created", { name: article.name }));
          await navigate({ to: "/articles/$articleId", params: { articleId: article.id } });
        }}
      />
    </>
  );
}

export function ArticlePage({ articleId }: { readonly articleId: string }) {
  const { t } = useI18n();
  const errorMessage = useErrorMessage();
  const query = useQuery(articleQuery(articleId));
  useDocumentTitle(t("app.pageTitle", { title: query.data?.name ?? t("articles.edit") }));
  if (query.isError) {
    return (
      <>
        <BackLink />
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
  return <ArticleEditor article={query.data} />;
}

function ArticleEditor({ article }: { readonly article: Article }) {
  const { t, locale } = useI18n();
  const update = useUpdateArticle(article.id);
  const archive = useArchiveArticle();
  const errorMessage = useErrorMessage();

  const fail = (caught: unknown) => {
    toast.error(errorMessage(caught) ?? t("error.generic"), { duration: Infinity });
  };

  const setArchived = (archived: boolean) => {
    archive.mutate(
      { id: article.id, archived },
      {
        onSuccess: (changed) => {
          const message = archived ? "articles.archivedToast" : "articles.restoredToast";
          showUndoToast(t(message, { name: changed.name }), t("common.undo"), () => {
            archive.mutate({ id: changed.id, archived: !archived }, { onError: fail });
          });
        },
        onError: fail,
      },
    );
  };

  return (
    <>
      <BackLink />
      <PageHeader
        title={article.name}
        description={`${t("articles.numberLabel")} ${article.number}`}
        actions={
          <Button
            variant="outline"
            onClick={() => {
              setArchived(!article.archived);
            }}
          >
            {article.archived ? (
              <ArchiveRestoreIcon aria-hidden="true" />
            ) : (
              <ArchiveIcon aria-hidden="true" />
            )}
            {article.archived ? t("common.restore") : t("common.archive")}
          </Button>
        }
      />
      {article.archived ? (
        <p className="flex items-center gap-2 text-sm">
          <Badge>
            <ArchiveIcon aria-hidden="true" />
            {t("common.archived")}
          </Badge>
          {t("articles.archivedNotice")}
        </p>
      ) : null}
      <ArticleForm
        key={article.id}
        defaultValues={articleToForm(article, locale)}
        onSubmit={async (values) => {
          await update.mutateAsync(formToRequest(values, locale));
          toast.success(t("common.saved"));
        }}
      />
    </>
  );
}
