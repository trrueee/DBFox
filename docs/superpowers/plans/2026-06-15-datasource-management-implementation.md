# Data Source Management Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved DBFox-style data source management console with create, edit, delete, health check, Schema sync, and active-source switching.

**Architecture:** Add a minimal backend update endpoint, extend the frontend API/payload layer, then rebuild `DataSourcesPage` around an explicit `detail | create | edit` mode. Keep the selected management row separate from the active workbench data source so browsing management details does not accidentally change workspace context.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, React 19, TypeScript, Vitest, Testing Library, existing DBFox CSS tokens.

---

## Files and Responsibilities

- `engine/schemas/datasource.py`: Defines create/test/update request models for data source API payload validation.
- `engine/api/datasources.py`: Owns data source CRUD, health check, delete confirmation, and Schema sync endpoints.
- `engine/tests/test_datasource_update_api.py`: Covers the new update endpoint and secret-preservation behavior.
- `desktop/src/lib/datasourcePayload.ts`: Builds create, update, and test payloads from the UI form shape.
- `desktop/src/lib/__tests__/datasourcePayload.test.ts`: Covers update payload behavior, especially blank secret preservation.
- `desktop/src/lib/api/datasources.ts`: Exposes `updateDatasource`.
- `desktop/src/pages/DataSourcesPage.tsx`: Renders the management console and handles page state/actions.
- `desktop/src/pages/__tests__/DataSourcesPage.test.tsx`: Covers management view behavior, create/edit/delete flows, and reused tab mode switching.
- `desktop/src/App.css`: Adds focused DBFox-style management console layout classes.
- `desktop/src/__tests__/datasourceTabs.test.ts`: Keeps the reused settings tab behavior covered with stable UTF-8 assertions.

## Task 1: Backend Update Endpoint

**Files:**
- Create: `engine/tests/test_datasource_update_api.py`
- Modify: `engine/schemas/datasource.py`
- Modify: `engine/api/datasources.py`

- [ ] **Step 1: Write the failing backend API tests**

Create `engine/tests/test_datasource_update_api.py` with:

```python
from fastapi.testclient import TestClient
import pytest

from engine.crypto import decrypt_password, encrypt_password
from engine.db import get_db
from engine.main import LOCAL_SECURE_TOKEN, app
from engine.models import DEFAULT_PROJECT_ID, DataSource


def _headers() -> dict[str, str]:
    return {"X-Local-Token": LOCAL_SECURE_TOKEN}


@pytest.fixture
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _create_datasource(db_session, *, password: str = "old-secret") -> DataSource:
    cipher, nonce = encrypt_password(password)
    ssh_cipher, ssh_nonce = encrypt_password("old-ssh")
    passphrase_cipher, passphrase_nonce = encrypt_password("old-passphrase")
    datasource = DataSource(
        id="update-ds",
        project_id=DEFAULT_PROJECT_ID,
        name="Old name",
        db_type="mysql",
        host="old.example.com",
        port=3306,
        database_name="old_db",
        username="old_user",
        password_ciphertext=cipher,
        password_nonce=nonce,
        ssh_enabled=True,
        ssh_host="old-bastion",
        ssh_port=22,
        ssh_username="old-ssh-user",
        ssh_password_ciphertext=ssh_cipher,
        ssh_password_nonce=ssh_nonce,
        ssh_pkey_path="C:/keys/old.pem",
        ssh_pkey_passphrase_ciphertext=passphrase_cipher,
        ssh_pkey_passphrase_nonce=passphrase_nonce,
        ssl_enabled=True,
        ssl_ca_path="C:/certs/old-ca.pem",
        ssl_cert_path="C:/certs/old-cert.pem",
        ssl_key_path="C:/certs/old-key.pem",
        ssl_verify_identity=True,
        connection_mode="direct",
        is_read_only=True,
        env="prod",
        status="active",
    )
    db_session.add(datasource)
    db_session.commit()
    return datasource


def _payload(**overrides):
    payload = {
        "name": "New name",
        "db_type": "mysql",
        "host": "new.example.com",
        "port": 3307,
        "database_name": "new_db",
        "username": "new_user",
        "password": "",
        "connection_mode": "direct",
        "is_read_only": False,
        "env": "test",
        "ssh_enabled": False,
        "ssh_host": "",
        "ssh_port": 22,
        "ssh_username": "",
        "ssh_password": "",
        "ssh_pkey_path": "",
        "ssh_pkey_passphrase": "",
        "ssl_enabled": False,
        "ssl_ca_path": "",
        "ssl_cert_path": "",
        "ssl_key_path": "",
        "ssl_verify_identity": True,
    }
    payload.update(overrides)
    return payload


def test_update_datasource_updates_public_fields(client, db_session) -> None:
    datasource = _create_datasource(db_session)

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    body = response.json()
    assert body["name"] == "New name"
    assert body["host"] == "new.example.com"
    assert body["port"] == 3307
    assert body["database_name"] == "new_db"
    assert body["username"] == "new_user"
    assert body["is_read_only"] is False
    assert body["env"] == "test"
    assert body["ssh_enabled"] is False
    assert body["ssl_enabled"] is False

    db_session.refresh(datasource)
    assert datasource.name == "New name"
    assert datasource.host == "new.example.com"
    assert datasource.port == 3307


def test_update_datasource_preserves_blank_secrets(client, db_session) -> None:
    datasource = _create_datasource(db_session)
    old_password_cipher = datasource.password_ciphertext
    old_password_nonce = datasource.password_nonce
    old_ssh_cipher = datasource.ssh_password_ciphertext
    old_passphrase_cipher = datasource.ssh_pkey_passphrase_ciphertext

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    db_session.refresh(datasource)
    assert datasource.password_ciphertext == old_password_cipher
    assert datasource.password_nonce == old_password_nonce
    assert datasource.ssh_password_ciphertext == old_ssh_cipher
    assert datasource.ssh_pkey_passphrase_ciphertext == old_passphrase_cipher


def test_update_datasource_replaces_non_empty_secrets(client, db_session) -> None:
    datasource = _create_datasource(db_session)

    response = client.put(
        f"/api/v1/datasources/{datasource.id}",
        json=_payload(
            password="new-secret",
            ssh_enabled=True,
            ssh_password="new-ssh",
            ssh_pkey_path="C:/keys/new.pem",
            ssh_pkey_passphrase="new-passphrase",
        ),
        headers=_headers(),
    )

    assert response.status_code == 200, response.json()
    db_session.refresh(datasource)
    assert decrypt_password(datasource.password_ciphertext, datasource.password_nonce) == "new-secret"
    assert decrypt_password(datasource.ssh_password_ciphertext, datasource.ssh_password_nonce) == "new-ssh"
    assert decrypt_password(datasource.ssh_pkey_passphrase_ciphertext, datasource.ssh_pkey_passphrase_nonce) == "new-passphrase"


def test_update_datasource_missing_id_returns_404(client) -> None:
    response = client.put(
        "/api/v1/datasources/missing",
        json=_payload(),
        headers=_headers(),
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "NOT_FOUND"
```

- [ ] **Step 2: Run backend test and verify RED**

Run: `python -m pytest engine/tests/test_datasource_update_api.py -q`

Expected: FAIL with 404 or method not allowed for `PUT /api/v1/datasources/{id}`.

- [ ] **Step 3: Add update schema**

Modify `engine/schemas/datasource.py` to include:

```python
class DataSourceUpdateRequest(BaseModel):
    name: str
    db_type: str = "mysql"
    host: str | None = None
    port: int | None = None
    database_name: str
    username: str | None = None
    password: str | None = None
    connection_mode: str = "direct"
    is_read_only: bool = False
    env: str = "dev"

    ssh_enabled: bool = False
    ssh_host: str | None = None
    ssh_port: int = 22
    ssh_username: str | None = None
    ssh_password: str | None = None
    ssh_pkey_path: str | None = None
    ssh_pkey_passphrase: str | None = None

    ssl_enabled: bool = False
    ssl_ca_path: str | None = None
    ssl_cert_path: str | None = None
    ssl_key_path: str | None = None
    ssl_verify_identity: bool = True
```

- [ ] **Step 4: Add backend endpoint**

Modify `engine/api/datasources.py`:

```python
from engine.schemas import DataSourceTestRequest, DataSourceCreateRequest, DataSourceUpdateRequest
```

Add helpers above routes:

```python
def _replace_secret_if_present(obj: DataSource, value: str | None, cipher_attr: str, nonce_attr: str) -> None:
    if value is None or value == "":
        return
    cipher, nonce = encrypt_password(value)
    setattr(obj, cipher_attr, cipher)
    setattr(obj, nonce_attr, nonce)
```

Add route after `api_list_datasources`:

```python
@router.put("/datasources/{id}")
def api_update_datasource(id: str, req: DataSourceUpdateRequest, db: Session = Depends(get_db)) -> dict[str, Any]:
    datasource = db.query(DataSource).filter(DataSource.id == id).first()
    if not datasource:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "数据源不存在"})

    try:
        config = req.model_dump()
        if req.db_type == "mysql":
            build_mysql_ssl_params(config)
        elif req.db_type == "postgresql":
            build_postgres_ssl_params(config)

        datasource.name = req.name
        datasource.db_type = req.db_type
        datasource.host = req.host
        datasource.port = req.port
        datasource.database_name = req.database_name
        datasource.username = req.username
        datasource.connection_mode = req.connection_mode
        datasource.is_read_only = req.is_read_only
        datasource.env = req.env
        datasource.ssh_enabled = req.ssh_enabled
        datasource.ssh_host = req.ssh_host
        datasource.ssh_port = req.ssh_port
        datasource.ssh_username = req.ssh_username
        datasource.ssh_pkey_path = req.ssh_pkey_path
        datasource.ssl_enabled = req.ssl_enabled
        datasource.ssl_ca_path = req.ssl_ca_path
        datasource.ssl_cert_path = req.ssl_cert_path
        datasource.ssl_key_path = req.ssl_key_path
        datasource.ssl_verify_identity = req.ssl_verify_identity

        _replace_secret_if_present(datasource, req.password, "password_ciphertext", "password_nonce")
        _replace_secret_if_present(datasource, req.ssh_password, "ssh_password_ciphertext", "ssh_password_nonce")
        _replace_secret_if_present(
            datasource,
            req.ssh_pkey_passphrase,
            "ssh_pkey_passphrase_ciphertext",
            "ssh_pkey_passphrase_nonce",
        )

        db.commit()
        db.refresh(datasource)
        return _datasource_to_dict(datasource)
    except HTTPException:
        db.rollback()
        raise
    except DBFoxError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
    except Exception:
        db.rollback()
        logger.exception("Failed to update datasource")
        raise HTTPException(
            status_code=500,
            detail={"code": "DATASOURCE_UPDATE_FAILED", "message": "更新数据源失败，请稍后重试。"},
        )
```

- [ ] **Step 5: Run backend test and verify GREEN**

Run: `python -m pytest engine/tests/test_datasource_update_api.py -q`

Expected: PASS for all tests in the file.

## Task 2: Frontend API and Payload

**Files:**
- Modify: `desktop/src/lib/datasourcePayload.ts`
- Modify: `desktop/src/lib/__tests__/datasourcePayload.test.ts`
- Modify: `desktop/src/lib/api/datasources.ts`

- [ ] **Step 1: Write failing payload tests**

Append tests to `desktop/src/lib/__tests__/datasourcePayload.test.ts`:

```ts
import { buildDatasourceUpdatePayload } from "../datasourcePayload";

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
```

- [ ] **Step 2: Run frontend payload test and verify RED**

Run: `cd desktop; npm test -- src/lib/__tests__/datasourcePayload.test.ts`

Expected: FAIL because `buildDatasourceUpdatePayload` is not exported.

- [ ] **Step 3: Implement update payload builder**

Add to `desktop/src/lib/datasourcePayload.ts`:

```ts
export function buildDatasourceUpdatePayload(form: DatasourceFormShape) {
  return {
    ...buildDatasourceTestPayload(form),
    name: form.name || "",
    connection_mode: "direct",
    is_read_only: Boolean(form.is_read_only),
    env: form.env || "dev",
  };
}
```

- [ ] **Step 4: Add API method**

Modify `desktop/src/lib/api/datasources.ts`:

```ts
updateDatasource: (id: string, params: unknown) =>
  request<DataSource>(`/datasources/${id}`, { method: "PUT", body: JSON.stringify(params) }),
```

- [ ] **Step 5: Run frontend payload tests and verify GREEN**

Run: `cd desktop; npm test -- src/lib/__tests__/datasourcePayload.test.ts`

Expected: PASS.

## Task 3: DataSourcesPage Behavior Tests

**Files:**
- Modify: `desktop/src/pages/__tests__/DataSourcesPage.test.tsx`

- [ ] **Step 1: Replace page test setup with reusable fixtures**

Use a test data source fixture with all fields used by the UI:

```ts
const datasource = {
  id: "ds-1",
  name: "生产只读库",
  db_type: "mysql",
  host: "db.example.com",
  port: 3306,
  database_name: "analytics",
  username: "readonly",
  connection_mode: "direct",
  is_read_only: true,
  env: "prod",
  status: "active",
  ssh_enabled: false,
  ssh_host: "",
  ssh_port: 22,
  ssh_username: "",
  ssh_pkey_path: "",
  ssl_enabled: true,
  ssl_ca_path: "C:/certs/ca.pem",
  ssl_cert_path: "",
  ssl_key_path: "",
  ssl_verify_identity: true,
  last_test_status: "success",
  last_test_latency_ms: 38,
  last_test_tables_count: 128,
  last_sync_status: "success",
  created_at: "2026-06-15T00:00:00Z",
};
```

Keep the existing `vi.mock("../../lib/api", ...)` and add `updateDatasource: vi.fn()`.

- [ ] **Step 2: Add failing management/default-mode tests**

Add tests:

```ts
it("renders the management list and selected detail by default", async () => {
  vi.mocked(api.listDatasources).mockResolvedValue([datasource]);
  render(renderPage(false));

  expect(await screen.findByText("生产只读库")).toBeInTheDocument();
  expect(screen.getByText("连接配置摘要")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "新增数据源" })).not.toBeInTheDocument();
});

it("selecting a row does not activate the datasource until the user clicks set current", async () => {
  const onSelectDataSource = vi.fn();
  vi.mocked(api.listDatasources).mockResolvedValue([datasource]);
  render(renderPage(false, { onSelectDataSource }));

  await screen.findByText("生产只读库");
  expect(onSelectDataSource).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "设为当前" }));
  expect(onSelectDataSource).toHaveBeenCalledWith(expect.objectContaining({ id: "ds-1" }));
});
```

- [ ] **Step 3: Add failing create/edit/delete tests**

Add tests:

```ts
it("opens create mode from the reused new-connection tab", async () => {
  vi.mocked(api.listDatasources).mockResolvedValue([datasource]);
  render(renderPage(true));

  expect(await screen.findByRole("heading", { name: "新增数据源" })).toBeInTheDocument();
});

it("opens edit mode with existing non-secret fields prefilled", async () => {
  vi.mocked(api.listDatasources).mockResolvedValue([datasource]);
  render(renderPage(false));

  await userEvent.click(await screen.findByRole("button", { name: "编辑" }));
  expect(screen.getByRole("heading", { name: "编辑数据源" })).toBeInTheDocument();
  expect(screen.getByDisplayValue("生产只读库")).toBeInTheDocument();
  expect(screen.getByDisplayValue("db.example.com")).toBeInTheDocument();
});

it("saves edits through updateDatasource", async () => {
  vi.mocked(api.listDatasources).mockResolvedValue([datasource]);
  vi.mocked(api.updateDatasource).mockResolvedValue({ ...datasource, name: "生产分析库" });
  render(renderPage(false));

  await userEvent.click(await screen.findByRole("button", { name: "编辑" }));
  await userEvent.clear(screen.getByLabelText("连接名称"));
  await userEvent.type(screen.getByLabelText("连接名称"), "生产分析库");
  await userEvent.click(screen.getByRole("button", { name: "保存修改" }));

  await waitFor(() => expect(api.updateDatasource).toHaveBeenCalledWith("ds-1", expect.objectContaining({ name: "生产分析库" })));
});

it("handles delete confirmation-required flow", async () => {
  vi.mocked(api.listDatasources).mockResolvedValue([datasource]);
  vi.mocked(api.deleteDatasource)
    .mockResolvedValueOnce({
      success: false,
      requires_confirmation: true,
      confirm_token: "token-1",
      impact_summary: "delete impact",
      expected_confirm_text: "生产只读库",
    })
    .mockResolvedValueOnce({ success: true, message: "deleted" });
  render(renderPage(false));

  await userEvent.click(await screen.findByRole("button", { name: "删除" }));
  await waitFor(() => expect(api.deleteDatasource).toHaveBeenCalledWith("ds-1"));
  expect(screen.getByText("delete impact")).toBeInTheDocument();
});
```

- [ ] **Step 4: Run page tests and verify RED**

Run: `cd desktop; npm test -- src/pages/__tests__/DataSourcesPage.test.tsx`

Expected: FAIL because the management console, edit mode, and delete confirmation behavior are not implemented yet.

## Task 4: DataSourcesPage Implementation

**Files:**
- Modify: `desktop/src/pages/DataSourcesPage.tsx`

- [ ] **Step 1: Add local types and helpers**

Inside `DataSourcesPage.tsx`, add:

```ts
type DataSourcePageMode = "detail" | "create" | "edit";
type ActionState = "idle" | "testing" | "saving" | "syncing" | "deleting";
type DatasourceFormState = Required<Omit<DatasourceFormShape, "project_id">>;
```

Add helpers:

```ts
const defaultForm = (): DatasourceFormState => ({
  db_type: "mysql",
  name: "",
  host: "",
  port: 3306,
  database_name: "",
  username: "",
  password: "",
  is_read_only: false,
  env: "dev",
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
```

```ts
const formFromDataSource = (ds: DataSource): DatasourceFormState => ({
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
```

- [ ] **Step 2: Add page state and datasource loading**

Use state for `datasources`, `selectedDataSourceId`, `mode`, `form`, `search`, `formError`, `testResult`, `actionState`, and `confirmDetails`.

Add `loadPageDatasources`:

```ts
const loadPageDatasources = async (preferredId?: string) => {
  const next = await api.listDatasources(activeProject?.id);
  setDatasources(next);
  setSelectedDataSourceId((current) => {
    if (preferredId && next.some((item) => item.id === preferredId)) return preferredId;
    if (current && next.some((item) => item.id === current)) return current;
    if (activeDataSource && next.some((item) => item.id === activeDataSource.id)) return activeDataSource.id;
    return next[0]?.id || "";
  });
  return next;
};
```

- [ ] **Step 3: Implement actions**

Implement:

- `startCreate()`: set `mode` to `create`, reset form.
- `startEdit(ds)`: set `mode` to `edit`, map ds to form.
- `handleTestConnection()`: test current form payload.
- `handleCreateDataSource()`: create, sync, refresh app datasource state, select and activate created source.
- `handleUpdateDataSource()`: update, refresh, return to detail.
- `handleSavedHealthCheck()`: call `api.checkDatasourceHealth(selected.id)`, refresh returned datasource/list.
- `handleSyncSchema()`: call `api.syncSchema(selected.id)`, refresh page list and `onRefreshDatasources`.
- `handleDeleteDataSource()`: call `api.deleteDatasource(id)` and set `confirmDetails` if required.

- [ ] **Step 4: Render management console**

Render:

- left list header/search/list rows
- right detail view for `mode === "detail"`
- form panel for `mode === "create" || mode === "edit"`
- empty state when no data sources and not in create mode
- `DangerConfirmDialog details={confirmDetails}`

Use labels with `htmlFor`/`id` for testable inputs, especially `连接名称`.

- [ ] **Step 5: Run page tests and verify GREEN**

Run: `cd desktop; npm test -- src/pages/__tests__/DataSourcesPage.test.tsx`

Expected: PASS.

## Task 5: DBFox Styling

**Files:**
- Modify: `desktop/src/App.css`

- [ ] **Step 1: Add focused CSS classes**

Add CSS under the existing datasource page section:

```css
.hifi-datasource-console {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  border: 1px solid var(--hairline);
  border-radius: 8px;
  overflow: hidden;
  background: var(--color-panel);
}

.hifi-datasource-list {
  min-width: 0;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
}

.hifi-datasource-list-item {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--color-text-primary);
  cursor: pointer;
  text-align: left;
  padding: 10px;
}

.hifi-datasource-list-item.active {
  background: var(--color-panel);
  border-color: var(--color-primary-soft);
  box-shadow: var(--shadow-panel);
}

.hifi-datasource-detail {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--color-panel);
}

.hifi-datasource-metrics,
.hifi-datasource-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 10px;
}

.hifi-datasource-config-grid {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 10px 14px;
}
```

Add any missing compact badge/status classes used by the component.

- [ ] **Step 2: Run page tests after CSS changes**

Run: `cd desktop; npm test -- src/pages/__tests__/DataSourcesPage.test.tsx`

Expected: PASS.

## Task 6: Reused Tab and Full Verification

**Files:**
- Modify: `desktop/src/__tests__/datasourceTabs.test.ts`
- Verify: `desktop/src/App.tsx`

- [ ] **Step 1: Replace brittle mojibake assertions**

Modify `desktop/src/__tests__/datasourceTabs.test.ts` to assert stable source snippets:

```ts
expect(app).toContain('title: "数据源管理"');
expect(app).toContain('title: "新建数据源"');
expect(app).toContain('initialShowAddForm={activeTab.title === "新建数据源"}');
```

Keep the existing assertions that reject DOM query and delayed click hacks.

- [ ] **Step 2: Run targeted frontend suite**

Run:

```powershell
cd desktop
npm test -- src/pages/__tests__/DataSourcesPage.test.tsx src/lib/__tests__/datasourcePayload.test.ts src/__tests__/datasourceTabs.test.ts
```

Expected: PASS.

- [ ] **Step 3: Run backend targeted suite**

Run:

```powershell
python -m pytest engine/tests/test_datasource_update_api.py -q
```

Expected: PASS.

- [ ] **Step 4: Run type/build verification**

Run:

```powershell
cd desktop
npm run build
```

Expected: exit code 0.

- [ ] **Step 5: Review diff for scope**

Run: `git diff --stat`

Expected modified files only in the files listed by this plan, plus the already-existing local `desktop/src/App.tsx` change if it is still present.

- [ ] **Step 6: Commit implementation**

Only if all verification passes:

```powershell
git add engine/schemas/datasource.py engine/api/datasources.py engine/tests/test_datasource_update_api.py desktop/src/lib/datasourcePayload.ts desktop/src/lib/__tests__/datasourcePayload.test.ts desktop/src/lib/api/datasources.ts desktop/src/pages/DataSourcesPage.tsx desktop/src/pages/__tests__/DataSourcesPage.test.tsx desktop/src/App.css desktop/src/__tests__/datasourceTabs.test.ts docs/superpowers/plans/2026-06-15-datasource-management-implementation.md
git commit -m "feat: redesign datasource management console"
```
