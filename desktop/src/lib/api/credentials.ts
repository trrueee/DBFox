import { request } from "./client";

export type CredentialKind =
  | "llm_api_key"
  | "langsmith_api_key"
  | "datasource_password"
  | "ssh_password"
  | "ssh_key_passphrase";

export interface CredentialReference {
  id: string;
  kind: CredentialKind;
}

/**
 * The only desktop API call that carries a raw secret. The response contains
 * only the opaque OS-keyring reference used by all subsequent requests.
 */
export function enrollCredential(kind: CredentialKind, secret: string): Promise<CredentialReference> {
  return request<CredentialReference>("/credentials", {
    method: "POST",
    body: JSON.stringify({ kind, secret }),
  });
}
