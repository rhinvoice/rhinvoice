import { queryOptions, useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type components } from "@/api/client";

export type User = components["schemas"]["UserResponse"];
export type LoginRequest = components["schemas"]["LoginRequest"];
export type SetupRequest = components["schemas"]["SetupRequest"];

export const authKeys = {
  me: ["auth", "me"] as const,
  setup: ["auth", "setup"] as const,
};

export const meQuery = queryOptions({
  queryKey: authKeys.me,
  queryFn: () => unwrap(api.GET("/api/auth/me")),
  staleTime: 60_000,
  retry: false,
});

export const setupStatusQuery = queryOptions({
  queryKey: authKeys.setup,
  queryFn: () => unwrap(api.GET("/api/auth/setup")),
  retry: false,
});

export function useLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LoginRequest) => unwrap(api.POST("/api/auth/login", { body })),
    onSuccess: (user) => {
      client.setQueryData(authKeys.me, user);
    },
  });
}

export function useSetup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: SetupRequest) => unwrap(api.POST("/api/auth/setup", { body })),
    onSuccess: (user) => {
      client.setQueryData(authKeys.me, user);
      client.setQueryData(authKeys.setup, { needs_setup: false });
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(api.POST("/api/auth/logout")),
    onSettled: () => {
      client.clear();
    },
  });
}

export function useChangePassword() {
  return useMutation({
    mutationFn: (body: components["schemas"]["ChangePasswordRequest"]) =>
      unwrap(api.POST("/api/auth/password", { body })),
  });
}

export function useTotpSetup() {
  return useMutation({ mutationFn: () => unwrap(api.POST("/api/auth/totp/setup")) });
}

export function useTotpConfirm() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (code: string) => unwrap(api.POST("/api/auth/totp/confirm", { body: { code } })),
    onSuccess: (user) => {
      client.setQueryData(authKeys.me, user);
    },
  });
}

export function useTotpDisable() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: components["schemas"]["DisableTotpRequest"]) =>
      unwrap(api.POST("/api/auth/totp/disable", { body })),
    onSuccess: (user) => {
      client.setQueryData(authKeys.me, user);
    },
  });
}
