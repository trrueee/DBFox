import { describe, expect, it } from "vitest";
import { buildDatasourceCreatePayload, buildDatasourceTestPayload, buildDatasourceUpdatePayload } from "../datasourcePayload";

describe("datasourcePayload", () => {
  it("strips UI-only fields for test payload", () => {
    const payload = buildDatasourceTestPayload({
      db_type: "mysql",
      name: "local",
      host: "127.0.0.1",
      port: 3306,
      database_name: "analytics",
      username: "root",
      password: "secret",
      is_read_only: true,
      env: "dev",
      ssh_enabled: false,
      ssl_enabled: false,
    });

    expect(payload).toMatchObject({
      db_type: "mysql",
      host: "127.0.0.1",
      database_name: "analytics",
      username: "root",
      password: "secret",
    });
    expect(payload).not.toHaveProperty("name");
    expect(payload).not.toHaveProperty("env");
  });

  it("includes create metadata", () => {
    const payload = buildDatasourceCreatePayload(
      {
        db_type: "sqlite",
        name: "local-db",
        database_name: "C:/data/app.db",
      },
      "project-1",
    );

    expect(payload.name).toBe("local-db");
    expect(payload.project_id).toBe("project-1");
    expect(payload.db_type).toBe("sqlite");
  });
});

describe("buildDatasourceUpdatePayload", () => {
  it("builds update payload without project_id", () => {
    const payload = buildDatasourceUpdatePayload({
      db_type: "mysql",
      name: "Updated",
      host: "db.example.com",
      port: 3306,
      database_name: "analytics",
      username: "readonly",
      password: "",
      is_read_only: true,
      env: "prod",
      ssh_enabled: false,
      ssl_enabled: false,
    });

    expect(payload).toMatchObject({
      db_type: "mysql",
      name: "Updated",
      host: "db.example.com",
      port: 3306,
      database_name: "analytics",
      username: "readonly",
      password: "",
      connection_mode: "direct",
      is_read_only: true,
      env: "prod",
    });
    expect(payload).not.toHaveProperty("project_id");
  });

  it("keeps blank edit secrets as empty strings", () => {
    const payload = buildDatasourceUpdatePayload({
      db_type: "mysql",
      name: "Updated",
      host: "db.example.com",
      port: 3306,
      database_name: "analytics",
      username: "readonly",
      password: "",
      ssh_password: "",
      ssh_pkey_passphrase: "",
    });

    expect(payload.password).toBe("");
    expect(payload.ssh_password).toBeNull();
    expect(payload.ssh_pkey_passphrase).toBeNull();
  });
});
