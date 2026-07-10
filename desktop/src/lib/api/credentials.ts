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

export interface CredentialEnrollmentInput {
  kind: CredentialKind;
  secret: string;
}

export interface CredentialEnrollmentBatch {
  credentials: CredentialReference[];
  lease_id: string;
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

/**
 * Atomically enroll related datasource secrets. If any write fails, the
 * backend removes every credential created by this request.
 */
export async function enrollCredentials(
  credentials: CredentialEnrollmentInput[],
): Promise<CredentialEnrollmentBatch | null> {
  if (credentials.length === 0) return null;
  return request<CredentialEnrollmentBatch>("/credentials/batch", {
    method: "POST",
    body: JSON.stringify({ credentials }),
  });
}

/** Idempotently revoke only a still-uncommitted server-issued lease. */
export function releaseCredentialLease(leaseId: string): Promise<void> {
  return request<void>(`/credentials/leases/${encodeURIComponent(leaseId)}`, {
    method: "DELETE",
  });
}
