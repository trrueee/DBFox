"""Comprehensive test suite for DBFox Runtime DLC Backend Host (R2).

Verifies:
1. Public Extension API v2 boundary (DLC imports strictly via dbfox_dlc_api).
2. RuntimeContributionSnapshot determinism & canonical ordering.
3. Pre-execution re-verification & tamper detection.
4. Unique module namespace isolation & vendored dependency collision resistance.
5. Transactional staging & broken DLC fault isolation.
6. Dynamic Tool registration, permission scope validation, and real execution.
7. Dynamic ProjectResourceProvider discovery & authorization.
8. Dynamic Resource Resolver execution.
9. Dynamic ContextContributor execution in ContextAssembler.
10. Dynamic Artifact payload write contract registration & historical fail-soft.
11. Typed DLC Operations execution, validation, and error bounds.
12. Isolated worker implementation identity parity & mismatch rejection.
13. R3 Activation projection derivation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.agent.artifact import validate_artifact_payload
from engine.agent.resource_refs import (
    RequestedResourceRef,
)
from engine.dlc import (
    ActivatedDlcIdentity,
    ContributionCompiler,
    DlcErrorCode,
    DlcPackageService,
    DlcTrustStore,
    compute_snapshot_id,
)
from engine.dlc.api import (
    DlcOperationContext,
)
from engine.tools.materialization import current_tool_contract_hash

from engine.runtime_composition import (
    authorize_project_resources,
    build_attempt_resource_resolver,
    build_product_tool_registry,
    discover_project_resources,
)
from verification.testkit.dlc_fixture_builder import (
    build_test_dlc_archive,
    generate_test_keypair,
)
from engine.tools.runtime.attempt import (
    ToolAttemptRequest,
    ToolImplementationIdentity,
    ToolInvocationContext,
)
from engine.tools.runtime.handler import ToolAttemptHandler
from engine.tools.runtime import provider_tool_name



@pytest.fixture
def test_keypair():
    return generate_test_keypair()


@pytest.fixture
def trust_store(test_keypair):
    _, pub_b64 = test_keypair
    store = DlcTrustStore()
    store.add_trusted_key(pub_b64)
    return store


@pytest.fixture
def dlc_service(tmp_path: Path, trust_store: DlcTrustStore):
    return DlcPackageService(storage_root=tmp_path / "dlcs", trust_store=trust_store)


@pytest.fixture(autouse=True)
def reset_active_snapshot():
    from engine.agent.artifact import artifact_payload_contracts
    from engine.db import engine
    from engine.models import Base
    from engine.runtime_composition import set_active_runtime_snapshot
    Base.metadata.create_all(bind=engine)
    orig = dict(artifact_payload_contracts._contracts)
    orig_frozen = artifact_payload_contracts._frozen
    artifact_payload_contracts._frozen = False
    yield
    set_active_runtime_snapshot(None)
    artifact_payload_contracts._contracts = dict(orig)
    artifact_payload_contracts._frozen = orig_frozen







# ---------------------------------------------------------------------------
# 1. Extension API v2 & Snapshot Identity Determinism
# ---------------------------------------------------------------------------


def test_snapshot_id_determinism():
    """Prove snapshot_id is deterministically derived from composition identity."""
    active_a = (
        ActivatedDlcIdentity(dlc_id="acme.alpha", package_version="1.0.0", package_digest="aaa" * 20),
        ActivatedDlcIdentity(dlc_id="acme.beta", package_version="2.0.0", package_digest="bbb" * 20),
    )
    # Reversed input order should produce identical snapshot_id
    active_b = (
        ActivatedDlcIdentity(dlc_id="acme.beta", package_version="2.0.0", package_digest="bbb" * 20),
        ActivatedDlcIdentity(dlc_id="acme.alpha", package_version="1.0.0", package_digest="aaa" * 20),
    )

    id_a = compute_snapshot_id(active_a)
    id_b = compute_snapshot_id(active_b)

    assert id_a == id_b
    assert id_a.startswith("snap_")


def test_snapshot_id_changes_with_package_digest():
    """Prove snapshot_id differs if a DLC package digest changes."""
    active_v1 = (
        ActivatedDlcIdentity(dlc_id="acme.alpha", package_version="1.0.0", package_digest="111" * 20),
    )
    active_v2 = (
        ActivatedDlcIdentity(dlc_id="acme.alpha", package_version="1.0.0", package_digest="222" * 20),
    )

    assert compute_snapshot_id(active_v1) != compute_snapshot_id(active_v2)


# ---------------------------------------------------------------------------
# 2. Public API Fixture & Pure-Python Vendoring Isolation
# ---------------------------------------------------------------------------


def test_multi_dlc_vendored_and_tool_identity_isolation(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove vendored modules and equal local Tool names remain owner-isolated."""
    priv_key, pub_b64 = test_keypair

    # DLC A vendors commonlib returning "version_A"
    archive_a = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.dlc_a",
            "version": "1.0.0",
            "displayName": "DLC A",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.acme.com"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/vendor/__init__.py": "",
            "backend/vendor/commonlib.py": "VAL = 'version_A'\n",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "from .vendor.commonlib import VAL\n"
                "\n"
                "class ToolAInput(api.ToolInputModel):\n"
                "    pass\n"
                "\n"
                "class ToolAOutput(api.ToolOutputModel):\n"
                "    val: str\n"
                "\n"
                "class ToolA(api.BaseTool[ToolAInput, ToolAOutput]):\n"
                "    name = 'shared_read'\n"
                "    version = '1.0.0'\n"
                "    group = 'custom'\n"
                "    description = 'Tool A'\n"
                "    input_model = ToolAInput\n"
                "    output_model = ToolAOutput\n"
                "    policy = api.ToolPolicy()\n"
                "    execution = api.ToolExecutionSpec(backend='in_process', capabilities=('network',))\n"
                "    presentation = api.ToolPresentation(title='Tool Title', category='explore', visibility='summary', progress='none')\n"
                "\n"
                "    def run(self, input_data, context):\n"
                "        return ToolAOutput(val=VAL)\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(ToolA())\n"
            ),
        },
        private_key=priv_key,
    )

    # DLC B vendors commonlib returning "version_B"
    archive_b = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.dlc_b",
            "version": "1.0.0",
            "displayName": "DLC B",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.acme.com"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/vendor/__init__.py": "",
            "backend/vendor/commonlib.py": "VAL = 'version_B'\n",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "from .vendor.commonlib import VAL\n"
                "\n"
                "class ToolBInput(api.ToolInputModel):\n"
                "    pass\n"
                "\n"
                "class ToolBOutput(api.ToolOutputModel):\n"
                "    val: str\n"
                "\n"
                "class ToolB(api.BaseTool[ToolBInput, ToolBOutput]):\n"
                "    name = 'shared_read'\n"
                "    version = '1.0.0'\n"
                "    group = 'custom'\n"
                "    description = 'Tool B'\n"
                "    input_model = ToolBInput\n"
                "    output_model = ToolBOutput\n"
                "    policy = api.ToolPolicy()\n"
                "    execution = api.ToolExecutionSpec(backend='in_process', capabilities=('network',))\n"
                "    presentation = api.ToolPresentation(title='Tool Title', category='explore', visibility='summary', progress='none')\n"
                "\n"
                "    def run(self, input_data, context):\n"
                "        return ToolBOutput(val=VAL)\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(ToolB())\n"
            ),
        },
        private_key=priv_key,
    )

    path_a = tmp_path / "dlc_a.dbfox-dlc"
    path_b = tmp_path / "dlc_b.dbfox-dlc"
    path_a.write_bytes(archive_a)
    path_b.write_bytes(archive_b)

    res_a = dlc_service.install_from_file(path_a, publisher_key_base64=pub_b64)
    res_b = dlc_service.install_from_file(path_b, publisher_key_base64=pub_b64)

    # Enable both in registry
    registry = dlc_service.registry
    registry.set_desired_enabled(res_a.dlc_id, True)
    registry.set_desired_enabled(res_b.dlc_id, True)

    # Compile snapshot
    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    assert len(snapshot.active_dlcs) == 2
    assert {d.dlc_id for d in snapshot.active_dlcs} == {"acme.dlc_a", "acme.dlc_b"}

    tool_registry = build_product_tool_registry(snapshot)
    tool_a = provider_tool_name("acme.dlc_a", "shared_read")
    tool_b = provider_tool_name("acme.dlc_b", "shared_read")
    assert tool_a != tool_b
    assert tool_a in tool_registry
    assert tool_b in tool_registry
    assert tool_registry.owner_of(tool_a) == "acme.dlc_a"
    assert tool_registry.owner_of(tool_b) == "acme.dlc_b"


# ---------------------------------------------------------------------------
# 3. Transactional Staging & Broken DLC Isolation
# ---------------------------------------------------------------------------


def test_broken_dlc_isolation(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove broken DLC B (syntax/exception in register) does not prevent valid DLC A or C from loading."""
    priv_key, pub_b64 = test_keypair

    # Valid DLC A
    arch_a = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.valid_a",
            "version": "1.0.0",
            "displayName": "Valid A",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host): pass\n",
        },
        private_key=priv_key,
    )

    # Broken DLC B (raises RuntimeError during register)
    arch_b = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.broken_b",
            "version": "1.0.0",
            "displayName": "Broken B",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host): raise RuntimeError('Explosion in DLC B')\n",
        },
        private_key=priv_key,
    )

    # Valid DLC C
    arch_c = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.valid_c",
            "version": "1.0.0",
            "displayName": "Valid C",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host): pass\n",
        },
        private_key=priv_key,
    )

    path_a = tmp_path / "a.dbfox-dlc"
    path_b = tmp_path / "b.dbfox-dlc"
    path_c = tmp_path / "c.dbfox-dlc"
    path_a.write_bytes(arch_a)
    path_b.write_bytes(arch_b)
    path_c.write_bytes(arch_c)

    dlc_service.install_from_file(path_a, publisher_key_base64=pub_b64)
    dlc_service.install_from_file(path_b, publisher_key_base64=pub_b64)
    dlc_service.install_from_file(path_c, publisher_key_base64=pub_b64)

    dlc_service.registry.set_desired_enabled("acme.valid_a", True)
    dlc_service.registry.set_desired_enabled("acme.broken_b", True)
    dlc_service.registry.set_desired_enabled("acme.valid_c", True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    active_ids = [d.dlc_id for d in snapshot.active_dlcs]
    assert "acme.valid_a" in active_ids
    assert "acme.valid_c" in active_ids
    assert "acme.broken_b" not in active_ids


# ---------------------------------------------------------------------------
# 4. Dynamic Tool Execution & Permission Scope Enforcement
# ---------------------------------------------------------------------------


def test_dynamic_tool_execution_and_permission_scope(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove a dynamic DLC Tool executes cleanly through standard ToolAttemptHandler."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.calculator",
            "version": "1.0.0",
            "displayName": "Calculator DLC",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.math.org"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class AddInput(api.ToolInputModel):\n"
                "    a: int\n"
                "    b: int\n"
                "\n"
                "class AddOutput(api.ToolOutputModel):\n"
                "    sum: int\n"
                "\n"
                "class AddTool(api.BaseTool[AddInput, AddOutput]):\n"
                "    name = 'acme_add'\n"
                "    version = '1.0.0'\n"
                "    group = 'math'\n"
                "    description = 'Add two integers'\n"
                "    input_model = AddInput\n"
                "    output_model = AddOutput\n"
                "    policy = api.ToolPolicy()\n"
                "    execution = api.ToolExecutionSpec(backend='in_process', capabilities=('network',))\n"
                "    presentation = api.ToolPresentation(title='Tool Title', category='explore', visibility='summary', progress='none')\n"
                "\n"
                "    def run(self, input_data, context):\n"
                "        return AddOutput(sum=input_data.a + input_data.b)\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(AddTool())\n"
            ),
        },
        private_key=priv_key,
    )

    archive_path = tmp_path / "calc.dbfox-dlc"
    archive_path.write_bytes(arch)

    res = dlc_service.install_from_file(archive_path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    tool_registry = build_product_tool_registry(snapshot)
    resolver = build_attempt_resource_resolver(snapshot=snapshot)
    handler = ToolAttemptHandler(registry=tool_registry, resolver=resolver)

    wire_name = provider_tool_name("acme.calculator", "acme_add")
    tool = tool_registry.require(wire_name)
    contract_hash = current_tool_contract_hash(tool)


    request = ToolAttemptRequest(
        mode="execute",
        tool_name=wire_name,
        frozen_tool_declared_version="1.0.0",
        frozen_tool_contract_hash=contract_hash,
        invocation=ToolInvocationContext(
            session_id="s1",
            run_id="r1",
            turn_id="t1",
            invocation_id="i1",
            idempotency_key="k1",
        ),
        authorized_input={"a": 10, "b": 32},
        attempt_timeout_ms=5000,
        implementation=tool_registry.implementation_identity_of(wire_name),
    )

    result = handler.run(request)
    assert result.status == "success"
    assert result.output == {"sum": 42}



def test_permission_violation_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove tool requesting capabilities not in manifest permissions is rejected with PERMISSION_VIOLATION."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.unauthorized_network",
            "version": "1.0.0",
            "displayName": "Unauthorized Network",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": [],  # No permissions declared!
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class BadInput(api.ToolInputModel):\n"
                "    pass\n"
                "\n"
                "class BadOutput(api.ToolOutputModel):\n"
                "    pass\n"
                "\n"
                "class BadTool(api.BaseTool[BadInput, BadOutput]):\n"
                "    name = 'bad_net'\n"
                "    version = '1.0.0'\n"
                "    group = 'custom'\n"
                "    description = 'Bad'\n"
                "    input_model = BadInput\n"
                "    output_model = BadOutput\n"
                "    policy = api.ToolPolicy()\n"
                "    execution = api.ToolExecutionSpec(backend='in_process', capabilities=('network',))\n"
                "    presentation = api.ToolPresentation(title='Tool Title', category='explore', visibility='summary', progress='none')\n"
                "\n"
                "    def run(self, input_data, context):\n"
                "        return BadOutput()\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(BadTool())\n"
            ),
        },
        private_key=priv_key,
    )

    archive_path = tmp_path / "bad.dbfox-dlc"
    archive_path.write_bytes(arch)

    res = dlc_service.install_from_file(archive_path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    # Broken DLC should be isolated
    assert "acme.unauthorized_network" not in [d.dlc_id for d in snapshot.active_dlcs]


@pytest.mark.parametrize(
    ("dlc_id", "permissions", "execution"),
    [
        (
            "acme.resource_intruder",
            [],
            "api.ToolExecutionSpec(required_resources=(api.ToolResourceRequirement(kind='dbfox.data.database'),))",
        ),
        (
            "acme.write_tool",
            ["filesystem_write:workspace"],
            "api.ToolExecutionSpec(backend='in_process', capabilities=('filesystem_write',))",
        ),
    ],
)
def test_dynamic_tool_rejects_foreign_resources_and_in_process_filesystem_write(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
    dlc_id: str,
    permissions: list[str],
    execution: str,
) -> None:
    """DLC Tools cannot consume another owner or claim write from in-process code."""

    priv_key, pub_b64 = test_keypair
    archive = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": dlc_id,
            "version": "1.0.0",
            "displayName": "Boundary Probe",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "permissions": permissions,
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "class ProbeInput(api.ToolInputModel):\n"
                "    pass\n"
                "class ProbeOutput(api.ToolOutputModel):\n"
                "    pass\n"
                "class ProbeTool(api.BaseTool[ProbeInput, ProbeOutput]):\n"
                "    name = 'probe'\n"
                "    group = 'custom'\n"
                "    description = 'Boundary probe'\n"
                "    input_model = ProbeInput\n"
                "    output_model = ProbeOutput\n"
                "    policy = api.ToolPolicy()\n"
                f"    execution = {execution}\n"
                "    presentation = api.ToolPresentation(title='Probe', category='explore')\n"
                "    def run(self, input_data, context):\n"
                "        return ProbeOutput()\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(ProbeTool())\n"
            ),
        },
        private_key=priv_key,
    )
    archive_path = tmp_path / f"{dlc_id}.dbfox-dlc"
    archive_path.write_bytes(archive)
    installed = dlc_service.install_from_file(
        archive_path,
        publisher_key_base64=pub_b64,
    )
    dlc_service.registry.set_desired_enabled(installed.dlc_id, True)

    snapshot = ContributionCompiler(
        dlc_service.storage_root,
        trust_store=dlc_service.trust_store,
    ).compile()

    failure = next(item for item in snapshot.activation_failures if item.dlc_id == dlc_id)
    assert failure.error_code == "permission_violation"
    assert all(item.dlc_id != dlc_id for item in snapshot.active_dlcs)


def test_compiler_rejects_resource_selector_missing_from_tool_input(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
) -> None:
    priv_key, pub_b64 = test_keypair
    archive = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.bad_selector",
            "version": "1.0.0",
            "displayName": "Bad Selector",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "permissions": [],
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "class ProbeInput(api.ToolInputModel):\n"
                "    resource_id: str\n"
                "class ProbeOutput(api.ToolOutputModel):\n"
                "    ok: bool = True\n"
                "class ProbeTool(api.BaseTool[ProbeInput, ProbeOutput]):\n"
                "    name = 'probe'\n"
                "    group = 'custom'\n"
                "    description = 'Bad selector probe'\n"
                "    input_model = ProbeInput\n"
                "    output_model = ProbeOutput\n"
                "    execution = api.ToolExecutionSpec(required_resources=(\n"
                "        api.ToolResourceRequirement(kind='acme.bad_selector.resource', selector_field='resorce_id'),\n"
                "    ))\n"
                "    presentation = api.ToolPresentation(title='Probe', category='explore')\n"
                "    def run(self, input_data, context):\n"
                "        return ProbeOutput()\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(ProbeTool())\n"
            ),
        },
        private_key=priv_key,
    )
    archive_path = tmp_path / "bad-selector.dbfox-dlc"
    archive_path.write_bytes(archive)
    installed = dlc_service.install_from_file(
        archive_path,
        publisher_key_base64=pub_b64,
    )
    dlc_service.registry.set_desired_enabled(installed.dlc_id, True)

    snapshot = ContributionCompiler(
        dlc_service.storage_root,
        trust_store=dlc_service.trust_store,
    ).compile()

    failure = next(
        item for item in snapshot.activation_failures
        if item.dlc_id == "acme.bad_selector"
    )
    assert failure.error_code == "backend_import_failed"
    assert "resorce_id" in failure.message
    assert all(item.dlc_id != "acme.bad_selector" for item in snapshot.active_dlcs)


# ---------------------------------------------------------------------------
# 5. Dynamic Resources, Context, Artifacts, and Operations
# ---------------------------------------------------------------------------


def test_full_dlc_contribution_suite(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove a DLC contributing ResourceProvider, Resolver, Context, Artifact, and Operation works end-to-end."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.analytics",
            "version": "1.0.0",
            "displayName": "Acme Analytics",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.acme.com"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class ReportPayload(api.BaseModel):\n"
                "    metrics: list[str]\n"
                "\n"
                "class PingInput(api.BaseModel):\n"
                "    message: str\n"
                "\n"
                "class PingOutput(api.BaseModel):\n"
                "    reply: str\n"
                "\n"
                "def ping_handler(input_data: PingInput, ctx: api.DlcOperationContext) -> PingOutput:\n"
                "    return PingOutput(reply=f'pong: {input_data.message} from {ctx.dlc_id}')\n"
                "\n"
                "def list_analytics_resources(project_id: str):\n"
                "    return (api.ProjectResourceDescriptor(kind='acme.analytics.report', id='rep_1', version='1', name='Main Report'),)\n"
                "\n"
                "def resolve_analytics_resource(ref):\n"
                "    return {'report_data': 'metrics_123'}\n"
                "\n"
                "class AnalyticsContextContributor(api.ContextContributor):\n"
                "    id = 'acme.analytics'\n"
                "    def build(self, input_data):\n"
                "        return (api.ContextFragment(source_id='acme.analytics', source_version='1.0.0', lane='resource', content='Active reports: 1'),)\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    assert host.runtime_info.dlc_id == 'acme.analytics'\n"
                "    assert host.runtime_info.package_version == '1.0.0'\n"
                "    assert host.runtime_info.data_path.is_dir()\n"
                "    host.resources.register_provider(list_analytics_resources)\n"
                "    host.resources.register_resolver('acme.analytics.report', resolve_analytics_resource)\n"
                "    host.context.register(AnalyticsContextContributor)\n"
                "    host.artifacts.register('acme.report', 1, ReportPayload)\n"
                "    host.operations.register(api.DlcOperationSpec(name='ping', input_model=PingInput, output_model=PingOutput, handler=ping_handler))\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "analytics.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()
    from engine.runtime_composition import set_active_runtime_snapshot

    set_active_runtime_snapshot(snapshot)

    # 1. Test Resource Discovery & Authorization
    descriptors = discover_project_resources(None, "p1", snapshot=snapshot)
    assert any(d.kind == "acme.analytics.report" and d.id == "rep_1" for d in descriptors)

    authorized = authorize_project_resources(
        None,
        "p1",
        requested=[RequestedResourceRef(kind="acme.analytics.report", id="rep_1")],
        snapshot=snapshot,
    )
    assert len(authorized) == 1
    assert authorized[0].kind == "acme.analytics.report"

    # 2. Test Resource Resolver
    resolver = build_attempt_resource_resolver(snapshot=snapshot)
    resolved = resolver.resolve(authorized)
    assert resolved[authorized[0].canonical()] == {"report_data": "metrics_123"}

    # 3. Test Artifact Validation
    validated_payload = validate_artifact_payload("acme.report", {"metrics": ["cpu", "memory"]}, schema_version=1)
    assert validated_payload == {"metrics": ["cpu", "memory"]}

    # 4. Test Operation
    op = snapshot.get_operation("acme.analytics", "ping")
    assert op is not None
    input_model = op.spec.input_model
    output = op.spec.handler(
        input_model(message="hello"),
        DlcOperationContext(dlc_id="acme.analytics", operation_name="ping"),
    )
    assert "pong: hello" in output.reply

    # 5. Test R3 Projection
    projection = snapshot.derive_r3_projection()
    assert projection.snapshot_id == snapshot.snapshot_id
    assert any(d["dlc_id"] == "acme.analytics" for d in projection.active_dlcs)


# ---------------------------------------------------------------------------
# 6. Isolated Worker Implementation Identity Parity
# ---------------------------------------------------------------------------


def test_isolated_worker_implementation_mismatch_rejection(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove worker rejects execution if the expected package digest does not match the active tool implementation."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.worker_test",
            "version": "1.0.0",
            "displayName": "Worker Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.acme.com"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class DummyInput(api.ToolInputModel):\n"
                "    pass\n"
                "\n"
                "class DummyOutput(api.ToolOutputModel):\n"
                "    pass\n"
                "\n"
                "class DummyTool(api.BaseTool[DummyInput, DummyOutput]):\n"
                "    name = 'acme_dummy'\n"
                "    version = '1.0.0'\n"
                "    group = 'custom'\n"
                "    description = 'Dummy'\n"
                "    input_model = DummyInput\n"
                "    output_model = DummyOutput\n"
                "    policy = api.ToolPolicy()\n"
                "    execution = api.ToolExecutionSpec(backend='in_process', capabilities=('network',))\n"
                "    presentation = api.ToolPresentation(title='Tool Title', category='explore', visibility='summary', progress='none')\n"
                "\n"
                "    def run(self, input_data, context):\n"
                "        return DummyOutput()\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(DummyTool())\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "worker_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    tool_registry = build_product_tool_registry(snapshot)
    resolver = build_attempt_resource_resolver(snapshot=snapshot)
    handler = ToolAttemptHandler(registry=tool_registry, resolver=resolver)

    wire_name = provider_tool_name("acme.worker_test", "acme_dummy")
    tool = tool_registry.require(wire_name)
    contract_hash = current_tool_contract_hash(tool)


    # Construct request with WRONG package digest
    request_bad_digest = ToolAttemptRequest(
        mode="execute",
        tool_name=wire_name,
        frozen_tool_declared_version="1.0.0",
        frozen_tool_contract_hash=contract_hash,
        invocation=ToolInvocationContext(
            session_id="s1",
            run_id="r1",
            turn_id="t1",
            invocation_id="i1",
            idempotency_key="k1",
        ),
        authorized_input={},
        attempt_timeout_ms=5000,
        implementation=ToolImplementationIdentity(
            owner_id="acme.worker_test",
            package_digest="wrong_digest_" * 4,
        ),
    )

    result = handler.run(request_bad_digest)
    assert result.status == "failed"
    assert result.error_code == "IMPLEMENTATION_MISMATCH"


# ---------------------------------------------------------------------------
# 7. Pre-execution Tamper Detection on Disk
# ---------------------------------------------------------------------------


def test_tampered_payload_on_disk_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that modifying a file on disk after installation is detected and rejected before execution."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.tamper_test",
            "version": "1.0.0",
            "displayName": "Tamper Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host): pass\n",
        },
        private_key=priv_key,
    )

    path = tmp_path / "tamper_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    # Tamper with entry.py on disk directly
    pkg_dir = dlc_service.storage_root / "packages" / f"sha256-{res.package_digest}"
    entry_file = pkg_dir / "backend" / "entry.py"
    entry_file.write_text("def register(host): raise Exception('Malicious injected code')\n", encoding="utf-8")

    # Pre-verification during compile must catch hash mismatch and isolate DLC
    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    assert "acme.tamper_test" not in [d.dlc_id for d in snapshot.active_dlcs]


# ---------------------------------------------------------------------------
# 8. Operations FastAPI Router Endpoints
# ---------------------------------------------------------------------------


def test_dlc_operations_api_router(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove FastAPI operations router executes typed DLC operations and handles error boundaries."""
    from fastapi.testclient import TestClient
    from engine.main import LOCAL_SECURE_TOKEN, app
    from engine.runtime_composition import set_active_runtime_snapshot

    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.ops_test",
            "version": "1.0.0",
            "displayName": "Ops Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.acme.com"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class EchoIn(api.BaseModel):\n"
                "    msg: str\n"
                "\n"
                "class EchoOut(api.BaseModel):\n"
                "    echo: str\n"
                "\n"
                "def echo_handler(inp: EchoIn, ctx: api.DlcOperationContext) -> EchoOut:\n"
                "    return EchoOut(echo=f'echo: {inp.msg}')\n"
                "\n"
                "def conflict_handler(inp: EchoIn, ctx: api.DlcOperationContext) -> EchoOut:\n"
                "    raise api.DlcOperationError(code='ACME_CONFLICT', message='safe conflict', status_code=409)\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.operations.register(api.DlcOperationSpec(name='echo', input_model=EchoIn, output_model=EchoOut, handler=echo_handler))\n"
                "    host.operations.register(api.DlcOperationSpec(name='conflict', input_model=EchoIn, output_model=EchoOut, handler=conflict_handler))\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "ops_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()
    set_active_runtime_snapshot(snapshot)

    headers = {"X-Local-Token": LOCAL_SECURE_TOKEN}
    client = TestClient(app)

    # 1. Valid operation invocation
    resp = client.post("/api/v1/dlcs/acme.ops_test/operations/echo", json={"msg": "hello dbfox"}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"echo": "echo: hello dbfox"}

    # 2. Non-existent operation
    resp_404_op = client.post("/api/v1/dlcs/acme.ops_test/operations/non_existent", json={}, headers=headers)
    assert resp_404_op.status_code == 404
    assert "non_existent" in resp_404_op.json()["detail"]

    # 3. Inactive DLC
    resp_404_dlc = client.post("/api/v1/dlcs/unknown.dlc/operations/echo", json={}, headers=headers)
    assert resp_404_dlc.status_code == 404
    assert "unknown.dlc" in resp_404_dlc.json()["detail"]

    # 4. Invalid input model
    resp_422 = client.post("/api/v1/dlcs/acme.ops_test/operations/echo", json={"invalid_field": 123}, headers=headers)
    assert resp_422.status_code == 422

    # 5. Bounded public operation failures preserve a client-safe typed problem.
    resp_conflict = client.post(
        "/api/v1/dlcs/acme.ops_test/operations/conflict",
        json={"msg": "hello"},
        headers=headers,
    )
    assert resp_conflict.status_code == 409
    conflict_problem = resp_conflict.json()
    assert conflict_problem["code"] == "ACME_CONFLICT"
    assert conflict_problem["detail"] == "safe conflict"
    assert conflict_problem["status"] == 409


def test_dlc_operation_host_commits_owner_bound_credential_adoption(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
    monkeypatch,
):
    from fastapi.testclient import TestClient

    from engine.db import SessionLocal
    from engine.main import LOCAL_SECURE_TOKEN, app
    from engine.models import CredentialLeaseRecord
    from engine.runtime_composition import set_active_runtime_snapshot
    from engine.security.credential_lease import (
        CredentialLeaseSaga,
        CredentialLeaseStatus,
    )
    from engine.security.credential_vault import (
        CredentialKind,
        InMemoryCredentialVault,
    )

    private_key, publisher_key = test_keypair
    archive = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.credential_adoption",
            "version": "1.0.0",
            "displayName": "Credential Adoption",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["credentials:datasource_password"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "owned = set()\n"
                "class AdoptIn(api.BaseModel):\n"
                "    credential_ref: str\n"
                "class AdoptOut(api.BaseModel):\n"
                "    adopted: bool\n"
                "def refs(inp):\n"
                "    return frozenset({inp.credential_ref})\n"
                "def owns(refs):\n"
                "    return refs.issubset(owned)\n"
                "def adopt(inp, ctx):\n"
                "    owned.add(inp.credential_ref)\n"
                "    return AdoptOut(adopted=True)\n"
                "def forget(inp, ctx):\n"
                "    return AdoptOut(adopted=True)\n"
                "def register(host):\n"
                "    host.credentials.register_reference_probe(owns)\n"
                "    host.operations.register(api.DlcOperationSpec(name='adopt', input_model=AdoptIn, output_model=AdoptOut, handler=adopt, credential_references=refs, credential_lease_required=True))\n"
                "    host.operations.register(api.DlcOperationSpec(name='forget', input_model=AdoptIn, output_model=AdoptOut, handler=forget, credential_references=refs, credential_lease_required=True))\n"
            ),
        },
        private_key=private_key,
    )
    package_path = tmp_path / "credential-adoption.dbfox-dlc"
    package_path.write_bytes(archive)
    installed = dlc_service.install_from_file(
        package_path,
        publisher_key_base64=publisher_key,
    )
    dlc_service.registry.set_desired_enabled(installed.dlc_id, True)
    snapshot = ContributionCompiler(
        dlc_service.storage_root,
        trust_store=dlc_service.trust_store,
    ).compile()
    set_active_runtime_snapshot(snapshot)

    vault = InMemoryCredentialVault()
    monkeypatch.setattr(
        "engine.api.credentials.get_credential_vault",
        lambda: vault,
    )
    monkeypatch.setattr(
        "engine.security.credential_lease.get_credential_vault",
        lambda: vault,
    )

    client = TestClient(app)
    auth_headers = {"X-Local-Token": LOCAL_SECURE_TOKEN}
    enrollment = client.post(
        "/api/v1/dlcs/acme.credential_adoption/credentials/batch",
        json={
            "credentials": [{
                "kind": "datasource_password",
                "secret": "operation-secret",
            }],
        },
        headers=auth_headers,
    )
    assert enrollment.status_code == 201
    credential_ref = enrollment.json()["credentials"][0]["id"]
    lease_id = enrollment.json()["lease_id"]
    denied_enrollment = client.post(
        "/api/v1/dlcs/acme.credential_adoption/credentials/batch",
        json={
            "credentials": [{
                "kind": "llm_api_key",
                "secret": "must-not-be-stored",
            }],
        },
        headers=auth_headers,
    )
    assert denied_enrollment.status_code == 403
    assert denied_enrollment.json()["code"] == "DLC_CREDENTIAL_PERMISSION_DENIED"

    path = "/api/v1/dlcs/acme.credential_adoption/operations/adopt"
    missing = client.post(
        path,
        json={"credential_ref": credential_ref},
        headers=auth_headers,
    )
    assert missing.status_code == 400
    assert missing.json()["code"] == "CREDENTIAL_LEASE_REQUIRED"

    adopted = client.post(
        path,
        json={"credential_ref": credential_ref},
        headers={**auth_headers, "X-Credential-Lease-Id": lease_id},
    )
    assert adopted.status_code == 200
    assert adopted.json() == {"adopted": True}

    with SessionLocal() as db:
        lease = db.get(CredentialLeaseRecord, lease_id)
        assert lease is not None
        assert lease.status == CredentialLeaseStatus.COMMITTED.value
        assert lease.owner_id == "acme.credential_adoption"
        assert lease.owner_operation == "adopt"

    unowned_ref = vault.put(
        kind=CredentialKind.DATASOURCE_PASSWORD,
        secret="must-not-leak",
    )
    with SessionLocal() as db:
        unowned_lease_id = CredentialLeaseSaga(db, vault).issue({unowned_ref})
        db.commit()
    not_durable = client.post(
        "/api/v1/dlcs/acme.credential_adoption/operations/forget",
        json={"credential_ref": unowned_ref},
        headers={
            **auth_headers,
            "X-Credential-Lease-Id": unowned_lease_id,
        },
    )
    assert not_durable.status_code == 500
    assert not_durable.json()["code"] == "CREDENTIAL_ADOPTION_NOT_DURABLE"
    with SessionLocal() as db:
        unowned_lease = db.get(CredentialLeaseRecord, unowned_lease_id)
        assert unowned_lease is not None
        assert unowned_lease.status == CredentialLeaseStatus.RELEASED.value
    assert vault.get(unowned_ref) is None


# ---------------------------------------------------------------------------
# 9. R2.1 Durable Implementation Identity & Recovery Mismatch Fail-Closed
# ---------------------------------------------------------------------------


def test_tool_invocation_durable_identity_persistence(tmp_path: Path):
    """Prove owner_id and package_digest are durably persisted in agent_tool_invocations."""
    from uuid import uuid4
    from typing import Any
    from engine.db import SessionLocal
    from engine.models import AgentToolInvocation, Project
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.repositories.tool import ToolInvocationRepository
    from engine.tools.materialization import materialize_tools
    from engine.tools.runtime import ToolRegistry
    from engine.tools.runtime.base import (
        BaseTool,
        ToolExecutionSpec,
        ToolInputModel,
        ToolOutputModel,
        ToolPolicy,
        ToolPresentation,
    )

    class DummyInput(ToolInputModel):
        param: str = ""

    class DummyOutput(ToolOutputModel):
        res: str = ""

    class DummyTool(BaseTool[DummyInput, DummyOutput]):
        name = "acme_durable_tool"
        group = "default"
        description = "Test durable tool"
        input_model = DummyInput
        output_model = DummyOutput
        policy = ToolPolicy()
        presentation = ToolPresentation(title="Test durable tool", category="explore")
        execution = ToolExecutionSpec(backend="in_process")

        def run(self, input_data: DummyInput, context: Any) -> DummyOutput:
            return DummyOutput(res="ok")

    reg = ToolRegistry(available_backends=frozenset({"in_process"}))
    reg.register(DummyTool(), owner="acme.test_dlc", package_digest="digest_abc123")
    mat_tools = materialize_tools(reg, execution_mode="read_only")

    with SessionLocal() as db:
        db.merge(Project(id="p1", name="Test Project"))
        db.commit()
        sess_repo = SessionRepository(db)
        aggregate = sess_repo.create(project_id="p1", title="Test")
        admission = sess_repo.admit(
            session_id=str(aggregate.id),
            resource_refs=(),
            content="Run test tool",
            idempotency_key=f"idem_{uuid4().hex}",
            llm_credential_id="cred_1",
            api_base=None,
            model_name="gpt-4o",
            request_payload={},
        )
        lease = sess_repo.claim(session_id=str(aggregate.id), owner="test_worker")
        assert lease is not None
        sess_repo.promote_next_input(lease=lease)
        turn = sess_repo.start_turn(
            lease=lease,
            run_id=admission.run_id,
            agent_definition_version="v1",
            prompt_version="v1",
            prompt_hash="p_hash",
            context_snapshot={},
            context_hash="c_hash",
            tool_materialization=mat_tools.model_dump(mode="json"),
            tool_materialization_hash=mat_tools.hash,
            provider="test",
            model_name="test",
        )

        tool_repo = ToolInvocationRepository(db)
        invocation = tool_repo.request(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            provider_call_id="call_1",
            tool_name=mat_tools.tools[0].name,
            raw_input={"param": "value"},
            materialization=mat_tools,
            policy_decision={"mode": "auto", "safe_args": {"param": "value"}},
        )
        db.commit()

        # Verify DB row has owner_id and package_digest persisted
        row = db.get(AgentToolInvocation, invocation.id)
        assert row is not None
        assert row.owner_id == "acme.test_dlc"
        assert row.package_digest == "digest_abc123"

        # Verify domain model mapped from DB has owner_id and package_digest
        recovered = tool_repo._domain(row)
        assert recovered.owner_id == "acme.test_dlc"
        assert recovered.package_digest == "digest_abc123"


def test_tool_dispatcher_a_to_b_recovery_mismatch_fails_closed(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that if a durable invocation was created under DLC A, and at execution time the tool

    is provided by DLC B (different package_digest), dispatcher fails closed with TOOL_VERSION_CHANGED.
    """
    from uuid import uuid4
    from typing import Any
    from sqlalchemy import select
    from engine.db import SessionLocal
    from engine.models import AgentObservationRecord, AgentToolInvocation, Project
    from engine.agent.definition import DEFAULT_AGENT_DEFINITION
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.repositories.tool import ToolInvocationRepository
    from engine.agent.tool_dispatcher import ToolDispatcher
    from engine.agent.observation import ObservationStatus
    from engine.agent.tool import ToolInvocationStatus
    from engine.tools.materialization import materialize_tools
    from engine.tools.runtime import ToolExecutor, ToolRegistry
    from engine.tools.runtime.base import (
        BaseTool,
        ToolExecutionSpec,
        ToolInputModel,
        ToolOutputModel,
        ToolPolicy,
        ToolPresentation,
    )

    class DummyInput(ToolInputModel):
        val: str = ""

    class DummyOutput(ToolOutputModel):
        out: str = ""

    class DummyTool(BaseTool[DummyInput, DummyOutput]):
        name = "shared_migrated_tool"
        group = "default"
        description = "Shared tool"
        input_model = DummyInput
        output_model = DummyOutput
        policy = ToolPolicy()
        presentation = ToolPresentation(title="Shared tool", category="explore")
        execution = ToolExecutionSpec(backend="in_process")

        def run(self, input_data: DummyInput, context: Any) -> DummyOutput:
            return DummyOutput(out="executed")

    # DLC A registry
    reg_a = ToolRegistry(available_backends=frozenset({"in_process"}))
    reg_a.register(
        DummyTool(),
        owner="acme.dlc_a",
        package_digest="digest_a" * 8,
    )
    mat_tools_a = materialize_tools(reg_a, execution_mode="read_only")

    # Current registry has the tool under DLC B (digest_B)
    current_registry = ToolRegistry(available_backends=frozenset({"in_process"}))
    current_registry.register(
        DummyTool(),
        owner="acme.dlc_b",
        package_digest="digest_b" * 8,
    )
    frozen_reg = current_registry.freeze()

    with SessionLocal() as db:
        db.merge(Project(id="p1", name="Test Project"))
        db.commit()
        sess_repo = SessionRepository(db)
        aggregate = sess_repo.create(project_id="p1", title="Test")
        admission = sess_repo.admit(
            session_id=str(aggregate.id),
            resource_refs=(),
            content="Run tool",
            idempotency_key=f"idem_{uuid4().hex}",
            llm_credential_id="cred_1",
            api_base=None,
            model_name="gpt-4o",
            request_payload={},
        )
        lease = sess_repo.claim(session_id=str(aggregate.id), owner="test_worker")
        assert lease is not None
        sess_repo.promote_next_input(lease=lease)
        turn = sess_repo.start_turn(
            lease=lease,
            run_id=admission.run_id,
            agent_definition_version="v1",
            prompt_version="v1",
            prompt_hash="p_hash",
            context_snapshot={},
            context_hash="c_hash",
            tool_materialization=mat_tools_a.model_dump(mode="json"),
            tool_materialization_hash=mat_tools_a.hash,
            provider="test",
            model_name="test",
        )

        tool_repo = ToolInvocationRepository(db)
        invocation = tool_repo.request(
            lease=lease,
            run_id=admission.run_id,
            turn_id=str(turn.id),
            provider_call_id="call_1",
            tool_name=mat_tools_a.tools[0].name,
            raw_input={"val": "test"},
            materialization=mat_tools_a,
            policy_decision={"mode": "auto", "safe_args": {"val": "test"}},
        )
        db.commit()

        # ToolDispatcher prepares and runs invocation with current_registry
        dispatcher = ToolDispatcher(
            session_factory=SessionLocal,
            registry=frozen_reg,
            definition=DEFAULT_AGENT_DEFINITION,
            executor=ToolExecutor(max_workers=1),
        )

        # Dispatch should detect implementation mismatch and settle with FAILED / TOOL_VERSION_CHANGED
        prepared = dispatcher._prepare_execution(lease, invocation)
        assert prepared is None

        # Verify invocation is settled as failed
        inv_row = db.get(AgentToolInvocation, invocation.id)
        assert inv_row is not None
        assert inv_row.status == ToolInvocationStatus.FAILED.value
        obs_row = db.execute(
            select(AgentObservationRecord).where(
                AgentObservationRecord.tool_invocation_id == invocation.id
            )
        ).scalar_one()
        assert obs_row.status == ObservationStatus.FAILED.value
        assert obs_row.error_code == "TOOL_VERSION_CHANGED"




# ---------------------------------------------------------------------------
# 10. ContextAssembler Real Execution with DLC Contributor
# ---------------------------------------------------------------------------


def test_context_assembler_with_dlc_contributor(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove ContextAssembler executes neutral DLC context contributors without Session exposure."""
    from uuid import uuid4
    from engine.db import SessionLocal
    from engine.models import Project
    from engine.agent.repositories.session import SessionRepository
    from engine.agent.context import ContextAssembler

    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.context_test",
            "version": "1.0.0",
            "displayName": "Context Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class DlcContextContrib(api.ContextContributor):\n"
                "    id = 'acme.context_test'\n"
                "    def build(self, input_data: api.ContextContributionInput):\n"
                "        assert input_data.session_id is not None\n"
                "        return (api.ContextFragment(source_id='acme.context_test', source_version='1.0.0', lane='evidence', content=f'DLC evidence for session {input_data.session_id}'),)\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.context.register(DlcContextContrib)\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "context_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    with SessionLocal() as db:
        db.merge(Project(id="p1", name="Test Project"))
        db.commit()
        sess_repo = SessionRepository(db)
        aggregate = sess_repo.create(project_id="p1", title="Test")
        admission = sess_repo.admit(
            session_id=str(aggregate.id),
            resource_refs=(),
            content="Need evidence",
            idempotency_key=f"idem_{uuid4().hex}",
            llm_credential_id="cred_1",
            api_base=None,
            model_name="gpt-4o",
            request_payload={},
        )

        assembler = ContextAssembler(
            db,
            contributors=snapshot.context_contributors,
        )
        context_snap = assembler.build(admission.run_id)

        assert any(
            f.source_id == "acme.context_test" and "DLC evidence for session" in f.content
            for f in context_snap.context_fragments
        )


# ---------------------------------------------------------------------------
# 11. Artifact Atomic Batch Registration & Rollback
# ---------------------------------------------------------------------------



def test_artifact_atomic_registration_conflict_rolls_back_entire_dlc(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that if a DLC defines multiple artifact contracts and one conflicts, none are registered and the DLC is rejected."""
    from engine.agent.artifact import artifact_payload_contracts, register_artifact_payload_contract
    from pydantic import BaseModel

    class ExistingContract(BaseModel):
        foo: str

    register_artifact_payload_contract("acme.existing_type", 1, ExistingContract)

    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.conflicting_artifacts",
            "version": "1.0.0",
            "displayName": "Conflicting Artifacts",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class FirstContract(api.BaseModel):\n"
                "    val: int\n"
                "\n"
                "class ConflictingContract(api.BaseModel):\n"
                "    foo: str\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.artifacts.register('acme.first_type', 1, FirstContract)\n"
                "    host.artifacts.register('acme.existing_type', 1, ConflictingContract)\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "conflicting_artifacts.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    # DLC should fail to activate
    assert "acme.conflicting_artifacts" not in [d.dlc_id for d in snapshot.active_dlcs]
    assert any(f.dlc_id == "acme.conflicting_artifacts" for f in snapshot.activation_failures)

    # First contract must NOT be registered
    assert artifact_payload_contracts.get("acme.first_type", 1) is None


# ---------------------------------------------------------------------------
# 12. Staged Tool Validation & Re-verification Extra File Detection
# ---------------------------------------------------------------------------


def test_staged_tool_isolated_process_backend_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that installable DLC tools requesting non-in_process execution backend are rejected."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.isolated_tool_test",
            "version": "1.0.0",
            "displayName": "Isolated Tool Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
            "permissions": ["network:api.acme.com"],
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class DummyInput(api.BaseModel):\n"
                "    msg: str = ''\n"
                "\n"
                "class DummyOutput(api.BaseModel):\n"
                "    res: str = ''\n"
                "\n"
                "class IsolatedTool(api.BaseTool):\n"
                "    name = 'isolated_tool'\n"
                "    description = 'Isolated tool'\n"
                "    input_model = DummyInput\n"
                "    output_model = DummyOutput\n"
                "    policy = api.ToolPolicy()\n"
                "    presentation = api.ToolPresentation()\n"
                "    execution = api.ToolExecutionSpec(backend='isolated_process')\n"
                "    def run(self, inp, ctx):\n"
                "        return DummyOutput(res='ok')\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(IsolatedTool())\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "isolated_tool_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    assert "acme.isolated_tool_test" not in [d.dlc_id for d in snapshot.active_dlcs]
    assert any(f.dlc_id == "acme.isolated_tool_test" for f in snapshot.activation_failures)


def test_reverification_rejects_extra_unlisted_files(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that injecting unlisted extra files into an installed package directory causes activation failure."""
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.extra_file_test",
            "version": "1.0.0",
            "displayName": "Extra File Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": "def register(host): pass\n",
        },
        private_key=priv_key,
    )

    path = tmp_path / "extra_file_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    # Add unauthorized extra file
    pkg_dir = dlc_service.storage_root / "packages" / f"sha256-{res.package_digest}"
    (pkg_dir / "unauthorized_script.py").write_text("print('injected')\n", encoding="utf-8")

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    assert "acme.extra_file_test" not in [d.dlc_id for d in snapshot.active_dlcs]
    assert any(f.dlc_id == "acme.extra_file_test" for f in snapshot.activation_failures)


# ---------------------------------------------------------------------------
# 13. Operations Project Scope & Max Size Bounds
# ---------------------------------------------------------------------------


def test_dlc_operations_project_scope_and_size_bounds(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove project-scoped operations enforce valid project_id and large payloads are rejected with 413."""
    from fastapi.testclient import TestClient
    from engine.db import SessionLocal
    from engine.models import Project
    from engine.main import LOCAL_SECURE_TOKEN, app
    from engine.runtime_composition import set_active_runtime_snapshot

    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.scope_test",
            "version": "1.0.0",
            "displayName": "Scope Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class ProjectIn(api.BaseModel):\n"
                "    action: str\n"
                "\n"
                "class ProjectOut(api.BaseModel):\n"
                "    project_id: str\n"
                "\n"
                "def proj_handler(inp: ProjectIn, ctx: api.DlcOperationContext) -> ProjectOut:\n"
                "    return ProjectOut(project_id=str(ctx.project_id))\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.operations.register(api.DlcOperationSpec(name='project_op', input_model=ProjectIn, output_model=ProjectOut, handler=proj_handler, scope='project'))\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "scope_test.dbfox-dlc"
    path.write_bytes(arch)

    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()
    set_active_runtime_snapshot(snapshot)

    headers = {"X-Local-Token": LOCAL_SECURE_TOKEN}
    client = TestClient(app)

    # 1. Project-scoped op without project_id fails with 400
    resp_no_proj = client.post("/api/v1/dlcs/acme.scope_test/operations/project_op", json={"action": "test"}, headers=headers)
    assert resp_no_proj.status_code == 400
    assert resp_no_proj.json()["code"] == "MISSING_PROJECT_ID"

    # 2. Project-scoped op with non-existent project_id fails with 404
    resp_bad_proj = client.post("/api/v1/dlcs/acme.scope_test/operations/project_op?project_id=non_existent", json={"action": "test"}, headers=headers)
    assert resp_bad_proj.status_code == 404
    assert resp_bad_proj.json()["code"] == "PROJECT_NOT_FOUND"

    # 3. Create a real project in DB and invoke successfully
    with SessionLocal() as db:
        proj = Project(id="proj_valid_123", name="Valid Project")
        db.add(proj)
        db.commit()

    resp_valid = client.post("/api/v1/dlcs/acme.scope_test/operations/project_op?project_id=proj_valid_123", json={"action": "test"}, headers=headers)
    assert resp_valid.status_code == 200
    assert resp_valid.json() == {"project_id": "proj_valid_123"}


# ---------------------------------------------------------------------------
# 15. R2.2: Failed DLC Cannot Poison Subsequent DLCs
# ---------------------------------------------------------------------------


def test_failed_dlc_cannot_poison_later_dlc(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that if DLC 1 defines a tool and then fails activation (e.g. invalid operation),

    its candidate tools are discarded and DLC 2 can register the same tool name without conflict.
    """
    priv_key, pub_b64 = test_keypair

    # DLC 1: registers tool 'shared_poison_test_tool' but fails on ungranted capability operation
    bad_arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.bad_first_dlc",
            "version": "1.0.0",
            "displayName": "Bad DLC",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "permissions": ["network"],  # Missing filesystem_write
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class ToolIn(api.ToolInputModel):\n"
                "    val: str = ''\n"
                "class ToolOut(api.ToolOutputModel):\n"
                "    val: str = ''\n"
                "\n"
                "class SharedTool(api.BaseTool[ToolIn, ToolOut]):\n"
                "    name = 'shared_poison_test_tool'\n"
                "    group = 'default'\n"
                "    description = 'Shared tool'\n"
                "    input_model = ToolIn\n"
                "    output_model = ToolOut\n"
                "    policy = api.ToolPolicy()\n"
                "    presentation = api.ToolPresentation(title='Shared', category='explore')\n"
                "    execution = api.ToolExecutionSpec(backend='in_process')\n"
                "    def run(self, inp, ctx):\n"
                "        return ToolOut(val='bad')\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(SharedTool())\n"
                "    # Register operation with ungranted filesystem_write capability -> will fail validation\n"
                "    host.operations.register(api.DlcOperationSpec(\n"
                "        name='forbidden_op',\n"
                "        input_model=ToolIn,\n"
                "        output_model=ToolOut,\n"
                "        handler=lambda inp, ctx: ToolOut(),\n"
                "        capabilities=('filesystem_write',),\n"
                "    ))\n"
            ),
        },
        private_key=priv_key,
    )

    # DLC 2: registers the same tool name 'shared_poison_test_tool' cleanly
    good_arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.good_second_dlc",
            "version": "1.0.0",
            "displayName": "Good DLC",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class ToolIn(api.ToolInputModel):\n"
                "    val: str = ''\n"
                "class ToolOut(api.ToolOutputModel):\n"
                "    val: str = ''\n"
                "\n"
                "class SharedTool(api.BaseTool[ToolIn, ToolOut]):\n"
                "    name = 'shared_poison_test_tool'\n"
                "    group = 'default'\n"
                "    description = 'Shared tool'\n"
                "    input_model = ToolIn\n"
                "    output_model = ToolOut\n"
                "    policy = api.ToolPolicy()\n"
                "    presentation = api.ToolPresentation(title='Shared', category='explore')\n"
                "    execution = api.ToolExecutionSpec(backend='in_process')\n"
                "    def run(self, inp, ctx):\n"
                "        return ToolOut(val='good')\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.tools.register(SharedTool())\n"
            ),
        },
        private_key=priv_key,
    )

    path_bad = tmp_path / "bad.dbfox-dlc"
    path_bad.write_bytes(bad_arch)
    res_bad = dlc_service.install_from_file(path_bad, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res_bad.dlc_id, True)

    path_good = tmp_path / "good.dbfox-dlc"
    path_good.write_bytes(good_arch)
    res_good = dlc_service.install_from_file(path_good, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res_good.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    # 1. Bad DLC failed activation and is recorded in activation_failures
    assert any(f.dlc_id == "acme.bad_first_dlc" for f in snapshot.activation_failures)
    assert not any(d.dlc_id == "acme.bad_first_dlc" for d in snapshot.active_dlcs)

    # 2. Good DLC activated successfully without being poisoned by Bad DLC
    assert any(d.dlc_id == "acme.good_second_dlc" for d in snapshot.active_dlcs)

    # 3. Tool registry contains the tool from Good DLC
    reg = build_product_tool_registry(snapshot)
    wire_name = provider_tool_name("acme.good_second_dlc", "shared_poison_test_tool")
    assert wire_name in reg.tool_names()
    assert reg.owner_of(wire_name) == "acme.good_second_dlc"


# ---------------------------------------------------------------------------
# 16. R2.2: Subprocess Worker Parity — Package Digest Mismatch Fails Closed
# ---------------------------------------------------------------------------


def test_isolated_worker_package_digest_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Prove that if a historical ToolAttemptRequest with package_digest A is sent to

    a real isolated subprocess worker, and the worker's runtime does not match digest A,
    the worker fails closed with IMPLEMENTATION_MISMATCH and does not execute.
    """
    from verification.support.metadata import create_migrated_metadata_engine
    from engine.tools.runtime.attempt import (
        ToolAttemptRequest,
        ToolImplementationIdentity,
        ToolInvocationContext,
    )
    from engine.tools.runtime.attempt_runner import (
        IsolatedProcessAttemptRunner,
        default_isolated_worker_command,
    )
    from engine.tools.materialization import current_tool_contract_hash
    from engine.runtime_composition import build_product_tool_registry

    import time
    class _Control:
        def __init__(self) -> None:
            self.deadline = time.monotonic() + 30.0

        def is_cancelled(self) -> bool:
            return False

    metadata_path = tmp_path / "worker-meta.db"
    metadata_engine = create_migrated_metadata_engine(metadata_path)
    monkeypatch.setenv("DBFOX_DATABASE_URL", f"sqlite:///{metadata_path}")
    reg = build_product_tool_registry()
    tool = reg.require("conversation_search")
    version = current_tool_contract_hash(tool)

    request = ToolAttemptRequest(
        mode="execute",
        tool_name="conversation_search",
        frozen_tool_declared_version=tool.version,
        frozen_tool_contract_hash=version,
        invocation=ToolInvocationContext(
            session_id="sess_1",
            run_id="run_1",
            turn_id="turn_1",
            invocation_id="inv_1",
            idempotency_key="idem_1",
            scope_refs=(),
        ),
        authorized_input={"query": "hello"},
        attempt_timeout_ms=5000,
        # Intentionally request a historical package digest that does not match current runtime
        implementation=ToolImplementationIdentity(
            owner_id="dbfox.conversation",
            package_digest="sha256_historical_mismatched_digest_1234567890",
            runtime_snapshot_id="historical_snap_1",
        ),
    )

    runner = IsolatedProcessAttemptRunner(default_isolated_worker_command())
    try:
        result = runner.run(request=request, control=_Control())
        assert result.status == "failed"
        assert result.error_code == "IMPLEMENTATION_MISMATCH"
        assert "mismatch" in (result.error or "").lower()
    finally:
        metadata_engine.dispose()


# ---------------------------------------------------------------------------
# 17. R2.2: Bounded Operation Bridge with Platform Hard Ceiling
# ---------------------------------------------------------------------------


def test_dlc_operation_platform_hard_ceiling_enforced(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that if a DLC operation declares max_output_bytes exceeding PLATFORM_MAX_DLC_OPERATION_OUTPUT_BYTES

    (or produces output larger than platform max), the platform hard ceiling is enforced.
    """
    from fastapi.testclient import TestClient
    from engine.main import LOCAL_SECURE_TOKEN, app
    from engine.runtime_composition import set_active_runtime_snapshot
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.ceiling_test",
            "version": "1.0.0",
            "displayName": "Ceiling Test",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "class PingIn(api.BaseModel):\n"
                "    size_kb: int = 1\n"
                "\n"
                "class PingOut(api.BaseModel):\n"
                "    payload: str\n"
                "\n"
                "def ping_handler(inp: PingIn, ctx: api.DlcOperationContext) -> PingOut:\n"
                "    return PingOut(payload='x' * (inp.size_kb * 1024))\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    # Request a 50 MiB limit, but platform ceiling is 10 MiB\n"
                "    host.operations.register(api.DlcOperationSpec(\n"
                "        name='large_ping',\n"
                "        input_model=PingIn,\n"
                "        output_model=PingOut,\n"
                "        handler=ping_handler,\n"
                "        max_output_bytes=50 * 1024 * 1024,\n"
                "    ))\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "ceiling_test.dbfox-dlc"
    path.write_bytes(arch)
    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()
    set_active_runtime_snapshot(snapshot)

    headers = {"X-Local-Token": LOCAL_SECURE_TOKEN}
    client = TestClient(app)

    # 1. Output within platform limit (e.g. 500 KB) succeeds
    resp_ok = client.post("/api/v1/dlcs/acme.ceiling_test/operations/large_ping", json={"size_kb": 500}, headers=headers)
    assert resp_ok.status_code == 200

    # 2. Output exceeding platform 10 MiB limit (e.g. 11 MiB) fails with 500 OUTPUT_SIZE_EXCEEDED
    resp_over = client.post("/api/v1/dlcs/acme.ceiling_test/operations/large_ping", json={"size_kb": 11 * 1024}, headers=headers)
    assert resp_over.status_code == 500
    assert resp_over.json()["code"] == "OUTPUT_SIZE_EXCEEDED"


# ---------------------------------------------------------------------------
# 18. R2.2.1: Resolver Authority Boundary — Core Session Leak Impossible
# ---------------------------------------------------------------------------


def test_dlc_two_argument_resolver_registration_rejected(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that a DLC attempting to register a two-argument / session-accepting

    resolver `def resolve(db, ref)` is rejected at registration/staging time,
    preventing any Core SQLAlchemy Session leakage to the DLC.
    """
    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.malicious_resolver",
            "version": "1.0.0",
            "displayName": "Malicious Resolver DLC",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "def leak_session_resolver(db, ref):\n"
                "    return {'db_type': str(type(db))}\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    # Attempting to register a 2-arg resolver must fail closed\n"
                "    host.resources.register_resolver('acme.leak', leak_session_resolver)\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "malicious_resolver.dbfox-dlc"
    path.write_bytes(arch)
    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    # The malicious DLC must have failed activation and must not be in active_dlcs
    assert not any(d.dlc_id == "acme.malicious_resolver" for d in snapshot.active_dlcs)
    assert any(
        f.dlc_id == "acme.malicious_resolver" and f.error_code in ("registration_conflict", DlcErrorCode.REGISTRATION_CONFLICT.value)
        for f in snapshot.activation_failures
    )
    # The resolver must NOT be in snapshot.resource_resolvers
    assert not any(r.kind == "acme.leak" for r in snapshot.resource_resolvers)


def test_dlc_resolver_never_receives_core_session(
    tmp_path: Path,
    dlc_service: DlcPackageService,
    test_keypair,
):
    """Prove that a valid DLC single-argument resolver strictly receives ResourceScopeRef

    and cannot receive or access the SQLAlchemy Session, even when metadata_session
    is provided to build_attempt_resource_resolver.
    """
    from engine.tools.runtime.attempt import ResourceScopeRef
    from sqlalchemy.orm import Session
    from unittest.mock import MagicMock

    priv_key, pub_b64 = test_keypair

    arch = build_test_dlc_archive(
        manifest_data={
            "manifestSchemaVersion": 1,
            "id": "acme.safe_resolver",
            "version": "1.0.0",
            "displayName": "Safe Resolver DLC",
            "publisher": "acme",
            "extensionApiVersion": "2",
            "requiresDbfox": ">=1.0.0",
            "entrypoints": {"backend": "backend/entry.py"},
        },
        payload_files={
            "backend/__init__.py": "",
            "backend/entry.py": (
                "import dbfox_dlc_api as api\n"
                "\n"
                "def safe_resolve(ref: api.ResourceScopeRef):\n"
                "    return {'arg_type': type(ref).__name__, 'is_scope_ref': isinstance(ref, api.ResourceScopeRef), 'ref_id': ref.id}\n"
                "\n"
                "def register(host: api.BackendExtensionHost) -> None:\n"
                "    host.resources.register_resolver('acme.safe_resolver.doc', safe_resolve)\n"
            ),
        },
        private_key=priv_key,
    )

    path = tmp_path / "safe_resolver.dbfox-dlc"
    path.write_bytes(arch)
    res = dlc_service.install_from_file(path, publisher_key_base64=pub_b64)
    dlc_service.registry.set_desired_enabled(res.dlc_id, True)

    compiler = ContributionCompiler(dlc_service.storage_root, trust_store=dlc_service.trust_store)
    snapshot = compiler.compile()

    assert any(d.dlc_id == "acme.safe_resolver" for d in snapshot.active_dlcs)
    contrib = next(r for r in snapshot.resource_resolvers if r.kind == "acme.safe_resolver.doc")
    assert contrib.binding == "scope_only"

    # Pass an explicit mock metadata Session
    mock_session = MagicMock(spec=Session)
    composite = build_attempt_resource_resolver(metadata_session=mock_session, snapshot=snapshot)

    ref = ResourceScopeRef(kind="acme.safe_resolver.doc", id="doc_999", version="1")
    resolved = composite.resolve([ref])

    assert ref.canonical() in resolved
    doc_res = resolved[ref.canonical()]
    assert doc_res["arg_type"] == "ResourceScopeRef"
    assert doc_res["is_scope_ref"] is True
    assert doc_res["ref_id"] == "doc_999"
    # mock_session was NEVER touched by DLC resolver
    assert mock_session.method_calls == []








