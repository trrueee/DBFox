"""Bounded public GitHub REST client owned by the DLC."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import re
import urllib.parse
from typing import Any

from .contracts import GithubFileEntry, GithubRepoOverviewOutput

GITHUB_API_HOST = "api.github.com"
MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_FILE_CHARS = 12_000
MAX_DIRECTORY_ENTRIES = 100
MAX_JSON_RESPONSE_BYTES = 4 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15.0
USER_AGENT = "DBFox-GitHub-DLC/1.0"

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")


class GithubServiceError(Exception):
    pass


class GithubInvalidInputError(GithubServiceError):
    pass


class GithubNotFoundError(GithubServiceError):
    pass


class GithubPrivateRepoError(GithubServiceError):
    pass


class GithubRateLimitedError(GithubServiceError):
    pass


class GithubNetworkUnavailableError(GithubServiceError):
    pass


class GithubFileBinaryError(GithubServiceError):
    pass


class GithubFileTooLargeError(GithubServiceError):
    pass


def normalize_github_repository(repo_input: str) -> tuple[str, str]:
    raw = (repo_input or "").strip()
    if not raw:
        raise GithubInvalidInputError("Repository input cannot be empty")

    if "://" in raw or raw.startswith("//"):
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme.lower() != "https":
            raise GithubInvalidInputError("Only HTTPS GitHub URLs are supported")
        if parsed.hostname != "github.com" or parsed.port is not None or parsed.username:
            raise GithubInvalidInputError("Only the canonical github.com origin is supported")
        if parsed.query or parsed.fragment:
            raise GithubInvalidInputError("GitHub repository URLs cannot contain query or fragment data")
        parts = [part for part in parsed.path.strip("/").split("/") if part]
    else:
        parts = [part.strip() for part in raw.split("/") if part.strip()]

    if len(parts) != 2:
        raise GithubInvalidInputError("Expected a GitHub repository in 'owner/repo' format")
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    for label, value in (("owner", owner), ("repository", repository)):
        if not 1 <= len(value) <= 100 or _NAME_PATTERN.fullmatch(value) is None:
            raise GithubInvalidInputError(f"Invalid repository {label}: {value!r}")
    return owner, repository


def normalize_repository_relative_path(path: str) -> str:
    cleaned = (path or "").strip().replace("\\", "/").strip("/")
    if not cleaned:
        return ""
    parts = cleaned.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise GithubInvalidInputError("Repository path traversal is forbidden")
    if len(cleaned) > 1024 or "\x00" in cleaned:
        raise GithubInvalidInputError("Repository path is invalid or too long")
    return cleaned


def _quote(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _read_response(
    target: str,
    *,
    accept: str = "application/vnd.github+json",
    max_bytes: int = MAX_JSON_RESPONSE_BYTES,
) -> tuple[bytes, dict[str, str]]:
    connection = http.client.HTTPSConnection(GITHUB_API_HOST, timeout=DEFAULT_TIMEOUT_SECONDS)
    try:
        connection.request(
            "GET",
            target,
            headers={
                "Accept": accept,
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        response = connection.getresponse()
        body = response.read(max_bytes + 1)
        headers = {key.lower(): value for key, value in response.getheaders()}
    except (OSError, TimeoutError, http.client.HTTPException) as exc:
        raise GithubNetworkUnavailableError("GitHub API is temporarily unreachable") from exc
    finally:
        connection.close()

    if len(body) > max_bytes:
        raise GithubFileTooLargeError("GitHub response exceeded the configured byte limit")
    if response.status == 404:
        raise GithubNotFoundError("The requested GitHub resource was not found")
    if response.status in (401, 403):
        if headers.get("x-ratelimit-remaining") == "0":
            raise GithubRateLimitedError("GitHub API rate limit exceeded")
        raise GithubPrivateRepoError("Repository is private or requires authentication")
    if response.status >= 400:
        raise GithubServiceError(f"GitHub API returned status {response.status}")
    return body, headers


def _request_json(target: str) -> Any:
    body, _headers = _read_response(target)
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GithubServiceError("GitHub API returned malformed JSON") from exc


class GithubReadService:
    def __init__(
        self,
        *,
        owner: str,
        repository: str,
        revision: str,
        binding_id: str,
        ref_name: str,
    ) -> None:
        self.owner = owner
        self.repository = repository
        self.revision = revision
        self.binding_id = binding_id
        self.ref_name = ref_name

    @property
    def _repository_target(self) -> str:
        return f"/repos/{_quote(self.owner)}/{_quote(self.repository)}"

    def get_repo_overview(self) -> GithubRepoOverviewOutput:
        data = _request_json(self._repository_target)
        if not isinstance(data, dict):
            raise GithubServiceError("GitHub repository response was not an object")
        if data.get("private") is True:
            raise GithubPrivateRepoError("Only public repositories are supported")
        return GithubRepoOverviewOutput(
            owner=self.owner,
            repository=self.repository,
            ref_name=self.ref_name,
            resolved_revision=self.revision,
            description=data.get("description") if isinstance(data.get("description"), str) else None,
            default_branch=data.get("default_branch") if isinstance(data.get("default_branch"), str) else None,
        )

    def list_files(self, path: str = "", limit: int = 50) -> tuple[list[GithubFileEntry], bool]:
        normalized = normalize_repository_relative_path(path)
        suffix = f"/{urllib.parse.quote(normalized, safe='/')}" if normalized else ""
        query = urllib.parse.urlencode({"ref": self.revision})
        data = _request_json(f"{self._repository_target}/contents{suffix}?{query}")
        raw_entries = data if isinstance(data, list) else [data]
        entries: list[GithubFileEntry] = []
        for item in raw_entries:
            if not isinstance(item, dict):
                continue
            raw_type = str(item.get("type") or "file")
            entry_type = (
                "dir"
                if raw_type == "dir"
                else "submodule"
                if raw_type == "submodule" or item.get("submodule_git_url")
                else "file"
            )
            entries.append(
                GithubFileEntry(
                    path=str(item.get("path") or normalized),
                    type=entry_type,
                    size_bytes=int(item.get("size") or 0) if entry_type == "file" else None,
                    sha=str(item.get("sha") or "") or None,
                )
            )
        entries.sort(key=lambda entry: (entry.type != "dir", entry.path.lower()))
        bounded_limit = min(max(1, limit), MAX_DIRECTORY_ENTRIES)
        return entries[:bounded_limit], len(entries) > bounded_limit

    def read_file(self, path: str) -> tuple[str, str, int, str, str, bool, str]:
        normalized = normalize_repository_relative_path(path)
        if not normalized:
            raise GithubInvalidInputError("File path cannot be empty")
        suffix = urllib.parse.quote(normalized, safe="/")
        query = urllib.parse.urlencode({"ref": self.revision})
        target = f"{self._repository_target}/contents/{suffix}?{query}"
        data = _request_json(target)
        if not isinstance(data, dict) or data.get("type") != "file":
            raise GithubNotFoundError(f"Path is not a file: {normalized}")
        blob_sha = str(data.get("sha") or "")
        reported_size = int(data.get("size") or 0)
        if not blob_sha:
            raise GithubServiceError("GitHub file response is missing its blob SHA")
        if reported_size > MAX_FILE_BYTES:
            raise GithubFileTooLargeError("GitHub file exceeds the 2 MiB read limit")

        if data.get("encoding") == "base64" and data.get("content"):
            try:
                encoded = "".join(str(data["content"]).split())
                decoded = base64.b64decode(encoded, validate=True)
            except Exception as exc:
                raise GithubServiceError("GitHub file content was not valid Base64") from exc
        else:
            decoded, _headers = _read_response(
                target,
                accept="application/vnd.github.raw+json",
                max_bytes=MAX_FILE_BYTES,
            )
        if len(decoded) > MAX_FILE_BYTES:
            raise GithubFileTooLargeError("GitHub file exceeds the 2 MiB read limit")
        if b"\x00" in decoded:
            raise GithubFileBinaryError("Binary GitHub files cannot be read as text")
        try:
            content = decoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GithubFileBinaryError("GitHub file is not valid UTF-8 text") from exc
        truncated = len(content) > MAX_FILE_CHARS
        return (
            normalized,
            self.revision,
            len(decoded),
            hashlib.sha256(decoded).hexdigest(),
            content[:MAX_FILE_CHARS],
            truncated,
            blob_sha,
        )


def resolve_public_repository_revision(
    owner: str,
    repository: str,
    ref_name: str,
) -> tuple[str, str, str | None, str | None]:
    repository_target = f"/repos/{_quote(owner)}/{_quote(repository)}"
    data = _request_json(repository_target)
    if not isinstance(data, dict):
        raise GithubServiceError("GitHub repository response was not an object")
    if data.get("private") is True:
        raise GithubPrivateRepoError("Only public repositories are supported")
    default_branch = str(data.get("default_branch") or "main")
    effective_ref = ref_name.strip() or default_branch
    commit = _request_json(f"{repository_target}/commits/{_quote(effective_ref)}")
    if not isinstance(commit, dict) or len(str(commit.get("sha") or "")) < 7:
        raise GithubServiceError(f"Could not resolve GitHub revision for {effective_ref}")
    description = data.get("description") if isinstance(data.get("description"), str) else None
    return str(commit["sha"]), effective_ref, default_branch, description
