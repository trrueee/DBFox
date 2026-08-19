"""Public read-only GitHub API service with strict security boundaries and bounded limits."""

from __future__ import annotations

import base64
import hashlib
import re
import urllib.parse
from typing import Any

import httpx

from engine.github.contracts import (
    GithubFileBinaryError,
    GithubFileEntry,
    GithubFileNotFoundError,
    GithubFileTooLargeError,
    GithubInvalidInputError,
    GithubNetworkUnavailableError,
    GithubNotFoundError,
    GithubPrivateRepoError,
    GithubRateLimitedError,
    GithubRepoOverviewOutput,
    GithubRevisionUnavailableError,
    GithubServiceError,
)

GITHUB_API_ORIGIN = "https://api.github.com"
MAX_FILE_BYTES = 2 * 1024 * 1024  # 2 MiB hard limit for raw response/body
MAX_FILE_CHARS = 12_000
MAX_DIRECTORY_ENTRIES = 100
DEFAULT_DIRECTORY_ENTRIES = 50
DEFAULT_TIMEOUT_SECONDS = 15.0
USER_AGENT = "DBFox-Engine/1.0"

_REPO_NAME_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")
_OWNER_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+$")


def normalize_github_repository(repo_input: str) -> tuple[str, str]:
    """Parse and normalize a GitHub repository string into (owner, repository).

    Rejects non-github hosts, custom ports, local IPs, SSRF patterns, and invalid characters.
    """
    raw = (repo_input or "").strip()
    if not raw:
        raise GithubInvalidInputError("Repository input cannot be empty.")

    # URL format: https://github.com/owner/repo
    if "://" in raw or raw.startswith("//"):
        parsed = urllib.parse.urlparse(raw)
        if parsed.scheme.lower() not in ("https", "http"):
            raise GithubInvalidInputError(f"Unsupported URL scheme: {parsed.scheme}")
        hostname = (parsed.hostname or "").lower()
        if hostname != "github.com":
            raise GithubInvalidInputError(f"Only 'github.com' is supported, got: {hostname}")
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) < 2:
            raise GithubInvalidInputError("GitHub URL must contain owner and repository name.")
        owner, repo = path_parts[0], path_parts[1]
    else:
        # Shorthand format: owner/repo
        parts = [p.strip() for p in raw.split("/") if p.strip()]
        if len(parts) != 2:
            raise GithubInvalidInputError("Expected GitHub repository in 'owner/repo' format.")
        owner, repo = parts[0], parts[1]

    if repo.endswith(".git"):
        repo = repo[:-4]

    if not (1 <= len(owner) <= 100) or not _OWNER_REGEX.match(owner):
        raise GithubInvalidInputError(f"Invalid repository owner: {owner!r}")
    if not (1 <= len(repo) <= 100) or not _REPO_NAME_REGEX.match(repo):
        raise GithubInvalidInputError(f"Invalid repository name: {repo!r}")

    return owner, repo


def normalize_repository_relative_path(path: str) -> str:
    """Normalize and validate a repository-relative path to prevent directory traversal."""
    cleaned = (path or "").strip().replace("\\", "/").strip("/")
    if not cleaned:
        return ""
    parts = cleaned.split("/")
    for p in parts:
        if p in ("..", "."):
            raise GithubInvalidInputError("Directory traversal ('..' or '.') is forbidden.")
    if len(cleaned) > 1024:
        raise GithubInvalidInputError("Path exceeds maximum length of 1024 characters.")
    return cleaned


class GithubReadService:
    """Bounded, read-only client for a specific GitHub repository at a resolved revision."""

    def __init__(
        self,
        owner: str,
        repository: str,
        revision: str,
        binding_id: str = "",
        ref_name: str = "main",
        *,
        http_client: httpx.Client | None = None,
        custom_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.owner = owner
        self.repository = repository
        self.revision = revision
        self.binding_id = binding_id
        self.ref_name = ref_name
        self._custom_transport = custom_transport
        self._http_client = http_client

    def _get_client(self) -> httpx.Client:
        if self._http_client is not None:
            return self._http_client
        return httpx.Client(
            base_url=GITHUB_API_ORIGIN,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=DEFAULT_TIMEOUT_SECONDS,
            transport=self._custom_transport,
            follow_redirects=True,
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        client = self._get_client()
        try:
            resp = client.request(method, endpoint, params=params, headers=headers)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GithubNetworkUnavailableError("GitHub API is temporarily unreachable.") from exc
        except Exception as exc:
            raise GithubNetworkUnavailableError("Network error contacting GitHub API.") from exc

        if resp.status_code == 404:
            raise GithubNotFoundError(f"Resource not found on GitHub: {self.owner}/{self.repository}")
        if resp.status_code in (401, 403):
            # Check rate limiting
            remaining = resp.headers.get("x-ratelimit-remaining")
            if remaining == "0":
                raise GithubRateLimitedError("GitHub API rate limit exceeded. Please try again later.")
            raise GithubPrivateRepoError("Repository is private or requires authentication.")
        if resp.status_code >= 400:
            raise GithubServiceError(f"GitHub API returned error status {resp.status_code}")

        return resp

    def get_repo_overview(self, ref_name: str | None = None) -> GithubRepoOverviewOutput:
        """Fetch repository overview and metadata."""
        effective_ref = ref_name or self.ref_name
        resp = self._request("GET", f"/repos/{self.owner}/{self.repository}")
        data = resp.json()
        if data.get("private", False):
            raise GithubPrivateRepoError("Only public repositories are supported.")

        return GithubRepoOverviewOutput(
            owner=self.owner,
            repository=self.repository,
            ref_name=effective_ref,
            resolved_revision=self.revision,
            description=data.get("description"),
            default_branch=data.get("default_branch"),
            visibility="public",
        )

    def list_files(
        self,
        path: str = "",
        limit: int = DEFAULT_DIRECTORY_ENTRIES,
    ) -> tuple[list[GithubFileEntry], bool]:
        """List files and folders at the given repository-relative directory path."""
        norm_path = normalize_repository_relative_path(path)
        clamped_limit = min(max(1, limit), MAX_DIRECTORY_ENTRIES)

        endpoint = f"/repos/{self.owner}/{self.repository}/contents/{norm_path}"
        resp = self._request("GET", endpoint, params={"ref": self.revision})
        data = resp.json()

        if isinstance(data, dict) and data.get("type") == "file":
            # Single file requested as directory
            return [
                GithubFileEntry(
                    path=data.get("path", norm_path),
                    type="file",
                    size_bytes=data.get("size"),
                    sha=data.get("sha"),
                )
            ], False

        if not isinstance(data, list):
            return [], False

        entries: list[GithubFileEntry] = []
        for item in data:
            item_type = item.get("type")
            if item_type == "dir":
                entry_type = "dir"
            elif item_type == "submodule":
                entry_type = "submodule"
            else:
                entry_type = "file"

            entries.append(
                GithubFileEntry(
                    path=str(item.get("path") or ""),
                    type=entry_type,
                    size_bytes=item.get("size") if entry_type == "file" else None,
                    sha=str(item.get("sha") or ""),
                )
            )

        # Sort: directories first, then files alphabetically
        entries.sort(key=lambda e: (0 if e.type == "dir" else 1, e.path.lower()))

        truncated = len(entries) > clamped_limit
        return entries[:clamped_limit], truncated

    def read_file(
        self,
        path: str,
    ) -> tuple[str, str, int, str, str, bool, str]:
        """Read text file contents at the authorized revision.

        Enforces hard byte limit (2 MiB), rejects binary files (NUL bytes),
        and strictly validates UTF-8 decoding without silent replacement.

        Returns (path, revision, size_bytes, content_sha256, content, truncated, blob_sha).
        """
        norm_path = normalize_repository_relative_path(path)
        if not norm_path:
            raise GithubInvalidInputError("File path cannot be empty.")

        endpoint = f"/repos/{self.owner}/{self.repository}/contents/{norm_path}"
        resp = self._request("GET", endpoint, params={"ref": self.revision})
        data = resp.json()

        if not isinstance(data, dict) or data.get("type") != "file":
            raise GithubFileNotFoundError(f"Path is not a file: {norm_path}")

        blob_sha = str(data.get("sha") or "")
        reported_size = int(data.get("size") or 0)
        if reported_size > MAX_FILE_BYTES:
            raise GithubFileTooLargeError(
                f"File '{norm_path}' ({reported_size} bytes) exceeds maximum size limit of {MAX_FILE_BYTES} bytes."
            )

        encoding = str(data.get("encoding") or "")
        raw_content = str(data.get("content") or "")

        if encoding == "base64":
            try:
                decoded_bytes = base64.b64decode(raw_content)
            except Exception as exc:
                raise GithubServiceError("Failed to decode file base64 content.") from exc
        else:
            decoded_bytes = raw_content.encode("utf-8")

        actual_size = len(decoded_bytes)
        if actual_size > MAX_FILE_BYTES:
            raise GithubFileTooLargeError(
                f"File '{norm_path}' ({actual_size} bytes) exceeds maximum size limit of {MAX_FILE_BYTES} bytes."
            )

        # Reject binary files
        if b"\x00" in decoded_bytes:
            raise GithubFileBinaryError(f"Binary file cannot be read as text: {norm_path}")

        # Strict UTF-8 validation (reject non-UTF-8 content without silent replacement)
        try:
            text_content = decoded_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise GithubFileBinaryError(f"File contains non-UTF-8 or binary content: {norm_path}") from exc

        content_sha256 = hashlib.sha256(decoded_bytes).hexdigest()
        size_bytes = actual_size or reported_size

        truncated = len(text_content) > MAX_FILE_CHARS
        bounded_content = text_content[:MAX_FILE_CHARS]

        return norm_path, self.revision, size_bytes, content_sha256, bounded_content, truncated, blob_sha  # type: ignore[return-value]


def resolve_public_repository_revision(
    owner: str,
    repository: str,
    ref_name: str = "",
    *,
    custom_transport: httpx.BaseTransport | None = None,
    http_client: httpx.Client | None = None,
) -> tuple[str, str, str | None, str | None]:
    """Resolve repository validity, effective ref, default branch, description, and canonical commit revision.

    Returns (resolved_revision_sha, effective_ref_name, default_branch, description).
    """
    service = GithubReadService(
        owner=owner,
        repository=repository,
        revision=ref_name or "HEAD",
        custom_transport=custom_transport,
        http_client=http_client,
    )

    # 1. Verify repo exists and is public
    resp = service._request("GET", f"/repos/{owner}/{repository}")
    repo_data = resp.json()
    if repo_data.get("private", False):
        raise GithubPrivateRepoError("Private repositories are not supported.")

    default_branch = str(repo_data.get("default_branch") or "main")
    description = repo_data.get("description")
    effective_ref = ref_name.strip() if ref_name and ref_name.strip() else default_branch

    # 2. Resolve commit SHA for the target effective ref
    commit_resp = service._request("GET", f"/repos/{owner}/{repository}/commits/{effective_ref}")
    commit_data = commit_resp.json()
    sha = str(commit_data.get("sha") or "")
    if not sha or len(sha) < 7:
        raise GithubRevisionUnavailableError(f"Could not resolve commit revision for ref: {effective_ref}")

    return sha, effective_ref, default_branch, description
