/** Build API payloads for datasource test/create — strip UI-only fields. */

export interface DatasourceFormShape {
  db_type: string;
  name?: string;
  host?: string;
  port?: number;
  database_name: string;
  username?: string;
  password?: string;
  is_read_only?: boolean;
  env?: string;
  ssh_enabled?: boolean;
  ssh_host?: string;
  ssh_port?: number;
  ssh_username?: string;
  ssh_password?: string;
  ssh_pkey_path?: string;
  ssh_pkey_passphrase?: string;
  ssl_enabled?: boolean;
  ssl_ca_path?: string;
  ssl_cert_path?: string;
  ssl_key_path?: string;
  ssl_verify_identity?: boolean;
  project_id?: string;
}

export interface DatasourceCredentialReferences {
  password_credential_id?: string;
  ssh_password_credential_id?: string;
  ssh_key_passphrase_credential_id?: string;
}

export function buildDatasourceTestPayload(
  form: DatasourceFormShape,
  credentials: DatasourceCredentialReferences = {},
) {
  return {
    db_type: form.db_type || "mysql",
    host: form.host || null,
    port: form.port ?? null,
    database_name: form.database_name,
    username: form.username || null,
    password_credential_id: credentials.password_credential_id ?? null,
    ssh_enabled: Boolean(form.ssh_enabled),
    ssh_host: form.ssh_host || null,
    ssh_port: form.ssh_port ?? 22,
    ssh_username: form.ssh_username || null,
    ssh_password_credential_id: credentials.ssh_password_credential_id ?? null,
    ssh_pkey_path: form.ssh_pkey_path || null,
    ssh_key_passphrase_credential_id: credentials.ssh_key_passphrase_credential_id ?? null,
    ssl_enabled: Boolean(form.ssl_enabled),
    ssl_ca_path: form.ssl_ca_path || null,
    ssl_cert_path: form.ssl_cert_path || null,
    ssl_key_path: form.ssl_key_path || null,
    ssl_verify_identity: form.ssl_verify_identity !== false,
  };
}

export function buildDatasourceCreatePayload(
  form: DatasourceFormShape,
  projectId?: string,
  credentials: DatasourceCredentialReferences = {},
) {
  return {
    ...buildDatasourceTestPayload(form, credentials),
    project_id: projectId,
    name: form.name || "",
    connection_mode: "direct",
    is_read_only: Boolean(form.is_read_only),
    env: form.env || "dev",
  };
}

export function buildDatasourceUpdatePayload(
  form: DatasourceFormShape,
  credentials: DatasourceCredentialReferences = {},
) {
  return {
    ...buildDatasourceTestPayload(form, credentials),
    name: form.name || "",
    connection_mode: "direct",
    is_read_only: Boolean(form.is_read_only),
    env: form.env || "dev",
  };
}
