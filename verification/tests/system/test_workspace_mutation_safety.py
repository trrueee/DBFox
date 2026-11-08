"""Real filesystem and cross-process regressions for Workspace mutations."""
from __future__ import annotations

import importlib
import multiprocessing
import os
from pathlib import Path
import sys
from types import ModuleType

import pytest


def _modules():
    name = "_workspace_mutation_safety"
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(Path(__file__).resolve().parents[3] / "dlcs/dbfox.workspace/backend")]
        sys.modules[name] = package
    return importlib.import_module(name + ".store"), importlib.import_module(name + ".service")


@pytest.fixture
def workspace(tmp_path):
    store_module, service_module = _modules()
    root = tmp_path / "project"
    root.mkdir()
    store = store_module.WorkspaceBindingStore(tmp_path / "state")
    store.create_binding("project", str(root))
    ref = store.list_resources("project")[0].to_scope_ref()
    return root, store, ref, service_module


@pytest.mark.parametrize("operation", ["delete", "move"])
@pytest.mark.parametrize("directory", [False, True])
def test_link_mutations_preserve_target(workspace, operation, directory):
    root, store, ref, _ = workspace
    target = root / "target"
    if directory:
        target.mkdir()
    else:
        target.write_text("keep", encoding="utf-8")
    alias = root / "alias"
    try:
        alias.symlink_to(target, target_is_directory=directory)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    service = store.resolve(ref)
    try:
        if operation == "delete":
            service.delete_path("alias")
            assert not alias.is_symlink()
        else:
            service.move_path("alias", "moved")
            assert (root / "moved").is_symlink()
            assert (root / "moved").resolve() == target
        assert target.exists()
        if not directory:
            assert target.read_text(encoding="utf-8") == "keep"
    finally:
        for path in (alias, root / "moved"):
            if path.is_symlink():
                path.unlink()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
@pytest.mark.parametrize("operation", ["delete", "move"])
def test_junction_mutations_preserve_target(workspace, operation):
    import _winapi

    root, store, ref, _ = workspace
    target = root / "target"
    target.mkdir()
    alias = root / "alias"
    _winapi.CreateJunction(str(target), str(alias))
    try:
        if operation == "delete":
            store.resolve(ref).delete_path("alias")
            assert not alias.is_junction()
        else:
            store.resolve(ref).move_path("alias", "moved")
            assert (root / "moved").is_junction()
        assert target.is_dir()
    finally:
        for path in (alias, root / "moved"):
            if path.is_junction():
                path.rmdir()


def test_file_discovery_lists_children_and_searches_nested_paths(workspace):
    root, store, ref, _ = workspace
    (root / "src/deep").mkdir(parents=True)
    (root / "src/deep/Pricing.ts").write_text("export const price = 1", encoding="utf-8")
    (root / "README.md").write_text("notes", encoding="utf-8")
    (root / "node_modules").mkdir()
    (root / "node_modules/Pricing.ts").write_text("ignored", encoding="utf-8")
    service = store.resolve(ref)

    assert [entry.relative_path for entry in service.search_files("pricing").entries] == ["src/deep/Pricing.ts"]
    assert [entry.relative_path for entry in service.search_files("SRC/DEEP/pricing").entries] == ["src/deep/Pricing.ts"]
    assert [entry.relative_path for entry in service.search_files("", path_prefix="src").entries] == ["src/deep"]
    (root / "Pricing.txt").write_text("also matches", encoding="utf-8")
    limited = service.search_files("pricing", limit=1)
    assert len(limited.entries) == 1
    assert limited.truncated is True


def test_search_and_grep_share_a_global_directory_entry_budget(workspace, monkeypatch):
    root, store, ref, module = workspace
    for name in ("a", "b", "c", "d", "e"):
        (root / name).mkdir()
    monkeypatch.setattr(module, "MAX_WORKSPACE_DIR_SCAN_ENTRIES", 2)
    service = store.resolve(ref)

    search = service.search_files("missing")
    assert search.entries == ()
    assert search.truncated is True
    grep = service.grep_text_files("missing")
    assert grep.scanned_files == 0
    assert grep.truncated is True


@pytest.mark.skipif(os.name != "nt", reason="Windows junction semantics")
def test_recursive_discovery_does_not_follow_junction_cycles_or_external_files(workspace):
    import _winapi

    root, store, ref, _ = workspace
    outside = root.parent / "outside"
    outside.mkdir()
    (outside / "private.txt").write_text("outside-only-value", encoding="utf-8")
    external = root / "external"
    cycle = root / "cycle"
    _winapi.CreateJunction(str(outside), str(external))
    _winapi.CreateJunction(str(root), str(cycle))
    try:
        service = store.resolve(ref)
        assert service.search_files("private").entries == ()
        result = service.grep_text_files("outside-only-value")
        assert result.matches == ()
        assert result.scanned_files == 0
        assert result.truncated is False
    finally:
        external.rmdir()
        cycle.rmdir()


def _write_process(state_path, expected_hash, text, ready, go, entered, release, result):
    store_module, service_module = _modules()
    store = store_module.WorkspaceBindingStore(state_path)
    service = store.resolve(store.list_resources("project")[0].to_scope_ref())
    if entered is not None:
        original = service_module.tempfile.NamedTemporaryFile

        def held_temporary(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise RuntimeError("test writer was not released")
            return original(*args, **kwargs)

        service_module.tempfile.NamedTemporaryFile = held_temporary
    ready.set()
    if not go.wait(10):
        return
    try:
        value = service.write_text_file("same.txt", text, expected_sha256=expected_hash)
        result.put(("success", value.content))
    except service_module.WorkspaceError as exc:
        result.put(("conflict", str(exc)))


def test_same_hash_writes_from_separate_processes_cannot_both_commit(workspace):
    root, store, ref, _ = workspace
    (root / "same.txt").write_text("original", encoding="utf-8")
    expected = store.resolve(ref).read_text_file("same.txt").sha256
    ctx = multiprocessing.get_context("spawn")
    first_ready, second_ready, first_go, second_go, entered, release = [ctx.Event() for _ in range(6)]
    result = ctx.Queue()
    first = ctx.Process(target=_write_process, args=(store.database_path.parent, expected, "first", first_ready, first_go, entered, release, result))
    second = ctx.Process(target=_write_process, args=(store.database_path.parent, expected, "second", second_ready, second_go, None, release, result))
    first.start()
    second.start()
    try:
        assert first_ready.wait(15) and second_ready.wait(15)
        first_go.set()
        assert entered.wait(5)
        second_go.set()
        # The first writer has already checked the old hash and is held before
        # replace. An unprotected second process commits here; a protected one
        # must wait and then reject the stale hash.
        second.join(timeout=0.3)
        release.set()
        first.join(timeout=10)
        second.join(timeout=10)
        assert first.exitcode == second.exitcode == 0
        responses = [result.get(timeout=3), result.get(timeout=3)]
        assert sorted(value[0] for value in responses) == ["conflict", "success"]
        assert (root / "same.txt").read_text(encoding="utf-8") == "first"
    finally:
        release.set()
        first_go.set()
        second_go.set()
        for child in (first, second):
            if child.is_alive():
                child.terminate()
            child.join(timeout=5)
        result.close()


def test_binary_files_consume_search_budget(workspace, monkeypatch):
    root, store, ref, service_module = workspace
    monkeypatch.setattr(service_module, "MAX_GREP_FILES", 3)
    monkeypatch.setattr(service_module, "MAX_GREP_BYTES", 16)
    for index in range(8):
        (root / f"{index}.bin").write_bytes(b"\0" * 8)
    result = store.resolve(ref).grep_text_files("missing")
    assert result.scanned_files == 2
    assert result.truncated is True
    assert result.matches == ()


def test_existing_file_requires_hash_at_shared_write_boundary(workspace):
    root, store, ref, module = workspace
    path = root / "notes.md"
    path.write_text("human revision", encoding="utf-8")
    with pytest.raises(module.WorkspaceError, match="sha256"):
        store.resolve(ref).write_text_file("notes.md", "unconditional replacement")
    assert path.read_text(encoding="utf-8") == "human revision"


@pytest.mark.parametrize("existing", [False, True])
def test_external_change_while_staging_is_not_overwritten(workspace, monkeypatch, existing):
    root, store, ref, module = workspace
    path = root / "notes.md"
    service = store.resolve(ref)
    expected = None
    if existing:
        path.write_text("original", encoding="utf-8")
        expected = service.read_text_file("notes.md").sha256
    original = module.tempfile.NamedTemporaryFile

    def human_edit(*args, **kwargs):
        # The external editor does not participate in the DLC SQLite lock.
        path.write_text("human revision", encoding="utf-8")
        return original(*args, **kwargs)

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", human_edit)
    with pytest.raises(module.WorkspaceError):
        service.write_text_file("notes.md", "agent revision", expected_sha256=expected)
    assert path.read_text(encoding="utf-8") == "human revision"
    assert list(root.glob(".notes.md.*.tmp")) == []


def test_write_result_describes_committed_bytes_not_a_later_external_edit(workspace, monkeypatch):
    import hashlib

    root, store, ref, module = workspace
    path = root / "notes.md"
    path.write_text("original", encoding="utf-8")
    service = store.resolve(ref)
    expected = service.read_text_file("notes.md").sha256
    original = module.os.replace

    def edited_after_commit(source, destination):
        original(source, destination)
        path.write_text("later human revision", encoding="utf-8")

    monkeypatch.setattr(module.os, "replace", edited_after_commit)
    result = service.write_text_file("notes.md", "agent revision", expected_sha256=expected)
    assert result.content == "agent revision"
    assert result.sha256 == hashlib.sha256(b"agent revision").hexdigest()
    assert result.size_bytes == len(b"agent revision")
    assert path.read_text(encoding="utf-8") == "later human revision"


@pytest.mark.skipif(os.name != "nt", reason="Windows rename is explicitly no-replace")
def test_move_cannot_overwrite_destination_created_after_preflight(workspace, monkeypatch):
    root, store, ref, module = workspace
    source = root / "source.md"
    destination = root / "destination.md"
    source.write_text("agent source", encoding="utf-8")
    original = Path.mkdir

    def created_by_human(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if path == root:
            destination.write_text("human destination", encoding="utf-8")

    monkeypatch.setattr(Path, "mkdir", created_by_human)
    with pytest.raises(module.WorkspaceError):
        store.resolve(ref).move_path("source.md", "destination.md")
    assert source.read_text(encoding="utf-8") == "agent source"
    assert destination.read_text(encoding="utf-8") == "human destination"
