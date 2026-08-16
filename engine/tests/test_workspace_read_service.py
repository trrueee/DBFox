"""P5A backend Workspace read resource contract tests."""

from __future__ import annotations

import pytest

from engine.workspace.read_service import (
    WorkspaceReadError,
    WorkspaceReadService,
)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "node_modules").mkdir()
    (root / "README.md").write_bytes(b"# Demo\n")
    (root / "src" / "main.py").write_bytes(b"print('ok')\n")
    (root / "src" / "blob.bin").write_bytes(bytes([0, 1, 2]))
    return root


def test_lists_sorted_entries_and_skips_heavy_dirs(workspace) -> None:
    service = WorkspaceReadService(workspace)
    entries = service.list_directory()
    assert [entry.name for entry in entries] == ["src", "README.md"]
    assert entries[0].is_dir is True
    assert {entry.name for entry in service.list_directory("src")} == {"main.py", "blob.bin"}


def test_reads_bounded_utf8_text_and_hashes_bytes(workspace) -> None:
    service = WorkspaceReadService(workspace)
    snapshot = service.read_text_file("src/main.py")
    assert snapshot.content == "print('ok')\n"
    assert snapshot.size_bytes == len(snapshot.content.encode())
    assert snapshot.truncated is False
    assert len(snapshot.sha256) == 64


def test_rejects_binary_files(workspace) -> None:
    service = WorkspaceReadService(workspace)
    with pytest.raises(WorkspaceReadError, match="binary"):
        service.read_text_file("src/blob.bin")


def test_rejects_path_escape_and_absolute_paths(workspace) -> None:
    service = WorkspaceReadService(workspace)
    with pytest.raises(WorkspaceReadError, match="'..'"):
        service.read_text_file("../secret.txt")
    with pytest.raises(WorkspaceReadError, match="relative"):
        service.read_text_file(str(workspace / "README.md"))


def test_rejects_symlink_escape(workspace, tmp_path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    link = workspace / "link.txt"
    link.symlink_to(outside)
    service = WorkspaceReadService(workspace)
    with pytest.raises(WorkspaceReadError, match="escapes"):
        service.read_text_file("link.txt")
