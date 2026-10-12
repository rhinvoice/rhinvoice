import { keepPreviousData, queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type Article = components["schemas"]["ArticleResponse"];
export type ArticleRequest = components["schemas"]["ArticleRequest"];
export type ArticleSort = components["schemas"]["ArticleSort"];
export type TaxCategory = components["schemas"]["TaxCategory"];

export interface ArticleListParams {
  readonly q: string;
  readonly includeArchived: boolean;
  readonly sort: ArticleSort;
  readonly direction: "asc" | "desc";
  readonly offset: number;
  readonly limit: number;
}

export const articleKeys = {
  all: ["articles"] as const,
  list: (params: ArticleListParams) => ["articles", "list", params] as const,
  detail: (id: string) => ["articles", "detail", id] as const,
};

export function articleListQuery(params: ArticleListParams) {
  return queryOptions({
    queryKey: articleKeys.list(params),
    queryFn: () =>
      unwrap(
        api.GET("/api/articles", {
          params: {
            query: {
              q: params.q,
              include_archived: params.includeArchived,
              sort: params.sort,
              direction: params.direction,
              limit: params.limit,
              offset: params.offset,
            },
          },
        }),
      ),
    placeholderData: keepPreviousData,
  });
}

export function articleQuery(id: string) {
  return queryOptions({
    queryKey: articleKeys.detail(id),
    queryFn: () =>
      unwrap(api.GET("/api/articles/{article_id}", { params: { path: { article_id: id } } })),
  });
}

function useOnSaved() {
  const client = useQueryClient();
  return (article: Article) => {
    client.setQueryData(articleKeys.detail(article.id), article);
    void client.invalidateQueries({ queryKey: [...articleKeys.all, "list"] });
  };
}

export function useCreateArticle() {
  const onSuccess = useOnSaved();
  return useMutation({
    mutationFn: (body: ArticleRequest) => unwrap(api.POST("/api/articles", { body })),
    onSuccess,
  });
}

export function useUpdateArticle(id: string) {
  const onSuccess = useOnSaved();
  return useMutation({
    mutationFn: (body: ArticleRequest) =>
      unwrap(api.PUT("/api/articles/{article_id}", { params: { path: { article_id: id } }, body })),
    onSuccess,
  });
}

/**
 * Archive or restore optimistically: the page shows the new state at once and
 * rolls back if the server refuses (principles.md 4.7).
 */
export function useArchiveArticle() {
  const client = useQueryClient();
  const onSuccess = useOnSaved();
  return useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) =>
      archived
        ? unwrap(
            api.POST("/api/articles/{article_id}/archive", {
              params: { path: { article_id: id } },
            }),
          )
        : unwrap(
            api.POST("/api/articles/{article_id}/restore", {
              params: { path: { article_id: id } },
            }),
          ),
    onMutate: async ({ id, archived }) => {
      const key = articleKeys.detail(id);
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<Article>(key);
      if (previous !== undefined) client.setQueryData<Article>(key, { ...previous, archived });
      return { previous };
    },
    onError: (_error, { id }, context) => {
      if (context?.previous !== undefined)
        client.setQueryData(articleKeys.detail(id), context.previous);
    },
    onSuccess,
  });
}
