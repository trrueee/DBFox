import { z } from "zod";

const requiredMySqlFieldsMessage = "请完整填写连接名称、主机、数据库名和用户名。";
const requiredSqliteFieldsMessage = "请完整填写连接名称和数据库路径。";

export const datasourceFormSchema = z.object({
  db_type: z.string(), name: z.string(), host: z.string(),
  port: z.number().int().min(0).max(65535), database_name: z.string(),
  username: z.string(), password: z.string(), is_read_only: z.boolean(), env: z.string(),
  ssh_enabled: z.boolean(), ssh_host: z.string(), ssh_port: z.number().int().min(0).max(65535),
  ssh_username: z.string(), ssh_password: z.string(), ssh_pkey_path: z.string(),
  ssh_pkey_passphrase: z.string(), ssl_enabled: z.boolean(), ssl_ca_path: z.string(),
  ssl_cert_path: z.string(), ssl_key_path: z.string(), ssl_verify_identity: z.boolean(),
}).superRefine((value, context) => {
  if (value.db_type === "sqlite") {
    if (!value.name.trim() || !value.database_name.trim()) {
      context.addIssue({ code: "custom", path: ["name"], message: requiredSqliteFieldsMessage });
    }
    return;
  }
  if (!value.name.trim() || !value.host.trim() || !value.database_name.trim() || !value.username.trim()) {
    context.addIssue({ code: "custom", path: ["name"], message: requiredMySqlFieldsMessage });
  }
});
