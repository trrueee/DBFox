import type { DataSource } from "../../lib/api";

export type DatasourceFormState = ReturnType<typeof emptyDatasourceForm>;

export type PageMode = "detail" | "create" | "edit";
export type ActionState = "idle" | "testing" | "saving" | "syncing" | "deleting";
export type ToastType = "success" | "warning" | "info";

export interface ConnectionTestResultState {
  status: "idle" | "testing" | "success" | "error";
  message: string;
  details?: { serverVersion?: string; readonly?: boolean; tablesCount?: number };
}

export const emptyDatasourceForm = () => ({
  db_type: "mysql" as string,
  name: "",
  host: "",
  port: 3306 as number,
  database_name: "",
  username: "",
  password: "",
  is_read_only: false,
  env: "dev" as string,
  ssh_enabled: false,
  ssh_host: "",
  ssh_port: 22,
  ssh_username: "",
  ssh_password: "",
  ssh_pkey_path: "",
  ssh_pkey_passphrase: "",
  ssl_enabled: false,
  ssl_ca_path: "",
  ssl_cert_path: "",
  ssl_key_path: "",
  ssl_verify_identity: true,
});

export const formFromDataSource = (ds: DataSource) => ({
  db_type: ds.db_type || "mysql",
  name: ds.name || "",
  host: ds.host || "",
  port: ds.port || (ds.db_type === "postgresql" ? 5432 : ds.db_type === "sqlite" ? 0 : 3306),
  database_name: ds.database_name || "",
  username: ds.username || "",
  password: "",
  is_read_only: Boolean(ds.is_read_only),
  env: ds.env || "dev",
  ssh_enabled: Boolean(ds.ssh_enabled),
  ssh_host: ds.ssh_host || "",
  ssh_port: ds.ssh_port || 22,
  ssh_username: ds.ssh_username || "",
  ssh_password: "",
  ssh_pkey_path: ds.ssh_pkey_path || "",
  ssh_pkey_passphrase: "",
  ssl_enabled: Boolean(ds.ssl_enabled),
  ssl_ca_path: ds.ssl_ca_path || "",
  ssl_cert_path: ds.ssl_cert_path || "",
  ssl_key_path: ds.ssl_key_path || "",
  ssl_verify_identity: ds.ssl_verify_identity !== false,
});
