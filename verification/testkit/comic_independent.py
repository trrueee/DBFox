"""Independent signed-package setup, shared by Comic red team and composition."""
import hashlib
from pathlib import Path
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import ed25519
from sqlalchemy.orm import sessionmaker

from dbfox_dlc_api import DlcOperationContext, RequestedResourceRef, ToolKey
from engine.dlc import DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.models import Project
from engine.runtime_composition import (active_runtime_snapshot, authorize_project_resources,
    build_dlc_action_runs_host, build_product_tool_registry, initialize_runtime_snapshot, set_active_runtime_snapshot)
from engine.tools.runtime import ToolRuntime
from verification.support.metadata import create_migrated_metadata_engine

ROOT = Path(__file__).resolve().parents[2]


class InstalledComic:
    def __init__(self, directory, owners=("dbfox.comic",)):
        self.previous = active_runtime_snapshot()
        self.service = DlcPackageService(directory / "dlcs")
        self.digests = {}
        key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Comic independent fixture publisher").digest())
        for owner in owners:
            package = build_dlc_package_from_source(ROOT / "dlcs" / owner, private_key=key)
            archive = directory / (owner + ".dbfox-dlc")
            archive.write_bytes(package.archive_bytes)
            self.service.trust_publisher_from_file(archive, expected_package_digest=package.package_digest,
                expected_publisher_key_id=package.publisher_fingerprint)
            self.service.install_from_file(archive)
            self.service.set_desired_enabled(owner, True)
            self.digests[owner] = package.package_digest
        self.engine = create_migrated_metadata_engine(directory / "metadata.sqlite")
        self.factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.reload()
        self.project = "comic-independent"
        with self.factory() as db:
            db.add(Project(id=self.project, name="Independent Comic"))
            db.add(Project(id="foreign-project", name="Not admitted"))
            db.commit()

    def reload(self):
        self.snapshot = initialize_runtime_snapshot(storage_root=self.service.storage_root)
        assert not self.snapshot.activation_failures
        self.registry = build_product_tool_registry(self.snapshot)

    def close(self):
        set_active_runtime_snapshot(self.previous)
        self.engine.dispose()

    def op(self, name, data, owner="dbfox.comic", project=None):
        project = project or self.project
        spec = self.snapshot.get_operation(owner, name).spec
        return spec.handler(spec.input_model.model_validate(data), DlcOperationContext(dlc_id=owner,
            operation_name=name, project_id=project, action_runs=build_dlc_action_runs_host(
                dlc_id=owner, project_id=project, snapshot=self.snapshot, session_factory=self.factory)))

    def create(self):
        return self.op("comics.create", {"title": "独立红队", "request_id": uuid4().hex}).comic

    def refs(self, kind, identity, project=None):
        with self.factory() as db:
            return authorize_project_resources(db, project or self.project,
                (RequestedResourceRef(kind=kind, id=identity),), snapshot=self.snapshot)

    def invoke(self, name, data, refs, identity=None, cancel=None, reconcile=False, owner="dbfox.comic"):
        identity = identity or uuid4().hex
        resources = {ref.canonical(): next(r.resolver for r in self.snapshot.resource_resolvers if r.kind == ref.kind)(ref) for ref in refs}
        runtime = ToolRuntime(self.registry)
        execute = runtime.reconcile if reconcile else runtime.invoke
        return execute(tool_name=self.registry.provider_name_for_key(ToolKey(owner, name)),
            raw_input=data, request=None, idempotency_key=identity, invocation_id=identity,
            scope_refs=refs, resources=resources, cancellation_probe=cancel)
