import { describe, expect, it } from "vitest";
import { buildDatasourceCreatePayload, buildDatasourceTestPayload } from "../datasourcePayload";

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
