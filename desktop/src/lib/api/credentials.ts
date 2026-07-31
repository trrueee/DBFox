import {
  apiEnrollCredentialApiV1CredentialsPost,
  apiEnrollCredentialsApiV1CredentialsBatchPost,
  apiReleaseCredentialLeaseApiV1CredentialsLeasesLeaseIdDelete,
} from "./generated/sdk.gen";
import type {
  CredentialEnrollmentBatchResponse,
  CredentialEnrollmentRequestWritable,
  CredentialKind,
  CredentialReference,
} from "./generated/types.gen";

export type { CredentialKind, CredentialReference };
export type CredentialEnrollmentInput = CredentialEnrollmentRequestWritable;
export type CredentialEnrollmentBatch = CredentialEnrollmentBatchResponse;

export async function enrollCredential(
  kind: CredentialKind,
  secret: string,
): Promise<CredentialReference> {
  const { data } = await apiEnrollCredentialApiV1CredentialsPost({
    body: { kind, secret },
    throwOnError: true,
  });
  return data;
}

export async function enrollCredentials(
  credentials: CredentialEnrollmentInput[],
): Promise<CredentialEnrollmentBatch | null> {
  if (credentials.length === 0) return null;
  const { data } = await apiEnrollCredentialsApiV1CredentialsBatchPost({
    body: { credentials },
    throwOnError: true,
  });
  return data;
}

export async function releaseCredentialLease(leaseId: string): Promise<void> {
  await apiReleaseCredentialLeaseApiV1CredentialsLeasesLeaseIdDelete({
    path: { lease_id: leaseId },
    throwOnError: true,
  });
}
