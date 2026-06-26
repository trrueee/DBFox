import { describe, expect, it } from "vitest";

import {
  DataSourceDetail,
  DataSourceForm,
  DataSourceList,
  SchemaSyncPanel,
} from "../../features/datasource-management";
import { emptyDatasourceForm, formFromDataSource } from "../../features/datasource-management/formState";

describe("DataSourcesPage module boundaries", () => {
  it("exports focused datasource management components", () => {
    expect(DataSourceDetail).toBeTypeOf("function");
    expect(DataSourceForm).toBeTypeOf("function");
    expect(DataSourceList).toBeTypeOf("function");
    expect(SchemaSyncPanel).toBeTypeOf("function");
  });

  it("keeps datasource form defaults outside the page component", () => {
    expect(emptyDatasourceForm()).toMatchObject({
      db_type: "mysql",
      port: 3306,
      env: "dev",
      ssh_port: 22,
      ssl_verify_identity: true,
    });
    expect(
      formFromDataSource({
        id: "ds-structure",
        name: "Local",
        db_type: "sqlite",
        host: null,
        port: 0,
        database_name: "local.db",
        username: null,
        status: "active",
        created_at: "",
      }),
    ).toMatchObject({
      db_type: "sqlite",
      host: "",
      port: 0,
      username: "",
      database_name: "local.db",
    });
  });
});
