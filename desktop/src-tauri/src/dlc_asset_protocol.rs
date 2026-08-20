use serde::{Deserialize, Serialize};
use std::borrow::Cow;
use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};
use tauri::http::{header, Request, Response, StatusCode};

pub const MAX_DLC_ASSET_BYTES: usize = 20 * 1024 * 1024; // 20 MiB
const PROTOCOL_SCHEME: &str = "dlc-asset";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ActiveDlcProjectionItem {
    pub dlc_id: String,
    pub package_version: String,
    pub package_digest: String,
    pub frontend_entrypoint: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct RuntimeDlcActivationProjection {
    pub snapshot_id: String,
    pub active_dlcs: Vec<ActiveDlcProjectionItem>,
}

#[derive(Debug, Default, Clone)]
pub struct DlcAssetHostState {
    inner: Arc<RwLock<Option<RuntimeDlcActivationProjection>>>,
}

impl DlcAssetHostState {
    pub fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(None)),
        }
    }

    pub fn update_projection(&self, projection: RuntimeDlcActivationProjection) {
        if let Ok(mut lock) = self.inner.write() {
            *lock = Some(projection);
        }
    }

    pub fn clear(&self) {
        if let Ok(mut lock) = self.inner.write() {
            *lock = None;
        }
    }

    pub fn is_digest_active(&self, digest: &str) -> bool {
        let lock = match self.inner.read() {
            Ok(guard) => guard,
            Err(_) => return false,
        };
        let Some(projection) = lock.as_ref() else {
            return false;
        };
        let normalized = normalize_digest(digest);
        projection.active_dlcs.iter().any(|d| {
            normalize_digest(&d.package_digest).eq_ignore_ascii_case(&normalized)
        })
    }

    #[allow(dead_code)]
    pub fn current_projection(&self) -> Option<RuntimeDlcActivationProjection> {
        self.inner.read().ok().and_then(|guard| guard.clone())
    }
}

pub fn normalize_digest(digest: &str) -> String {
    digest
        .strip_prefix("sha256:")
        .or_else(|| digest.strip_prefix("sha256-"))
        .unwrap_or(digest)
        .to_ascii_lowercase()
}

#[derive(Debug, PartialEq, Eq)]
pub struct ParsedDlcAssetRequest {
    pub package_digest: String,
    pub subpath: String,
}

pub fn parse_dlc_asset_url(raw_url: &str) -> Result<ParsedDlcAssetRequest, String> {
    let url = tauri::Url::parse(raw_url).map_err(|e| format!("Invalid URL: {e}"))?;
    if url.scheme() != PROTOCOL_SCHEME {
        return Err(format!("Invalid scheme '{}': expected '{PROTOCOL_SCHEME}'", url.scheme()));
    }
    if let Some(host) = url.host_str() {
        if !host.is_empty() && !host.eq_ignore_ascii_case("localhost") && host != "127.0.0.1" {
            return Err("Invalid host: only localhost is permitted".to_string());
        }
    }
    let mut segments = url
        .path_segments()
        .ok_or_else(|| "Missing path segments in dlc-asset URL".to_string())?;

    let raw_digest = segments
        .next()
        .ok_or_else(|| "Missing package digest in dlc-asset URL".to_string())?;
    let normalized_digest = normalize_digest(raw_digest);
    if normalized_digest.len() != 64 || !normalized_digest.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("Invalid package digest format: expected 64 hex characters".to_string());
    }

    let mut remaining: Vec<&str> = Vec::new();
    for segment in segments {
        if segment.is_empty() || segment == "." {
            continue;
        }
        if segment == ".."
            || segment.contains('\\')
            || segment.contains('\0')
            || segment.contains('/')
        {
            return Err("Path traversal segment rejected".to_string());
        }
        remaining.push(segment);
    }

    if remaining.is_empty() {
        return Err("Missing asset subpath".to_string());
    }

    // Strip leading "frontend" if present in URL path (since base dir is already /frontend/)
    let subpath = if remaining.first().copied() == Some("frontend") {
        remaining[1..].join("/")
    } else {
        remaining.join("/")
    };

    if subpath.is_empty() {
        return Err("Missing frontend asset subpath".to_string());
    }

    Ok(ParsedDlcAssetRequest {
        package_digest: normalized_digest,
        subpath,
    })
}

pub fn resolve_dlc_packages_root() -> PathBuf {
    if let Ok(override_dir) = std::env::var("DBFOX_RUNTIME_DIR") {
        if !override_dir.trim().is_empty() {
            return PathBuf::from(override_dir).join("dlcs").join("packages");
        }
    }

    #[cfg(target_os = "windows")]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return PathBuf::from(appdata)
                .join("DBFox")
                .join("dlcs")
                .join("packages");
        }
    }

    #[cfg(target_os = "macos")]
    {
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home)
                .join("Library")
                .join("Application Support")
                .join("DBFox")
                .join("dlcs")
                .join("packages");
        }
    }

    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        if let Ok(xdg) = std::env::var("XDG_DATA_HOME") {
            return PathBuf::from(xdg).join("dbfox").join("dlcs").join("packages");
        }
        if let Ok(home) = std::env::var("HOME") {
            return PathBuf::from(home)
                .join(".local")
                .join("share")
                .join("dbfox")
                .join("dlcs")
                .join("packages");
        }
    }

    PathBuf::from("dlcs").join("packages")
}

pub fn mime_for_path(path: &Path) -> &'static str {
    match path.extension().and_then(|s| s.to_str()).unwrap_or("").to_ascii_lowercase().as_str() {
        "js" | "mjs" => "text/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json; charset=utf-8",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "ico" => "image/x-icon",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "ttf" => "font/ttf",
        "otf" => "font/otf",
        "html" => "text/html; charset=utf-8",
        _ => "application/octet-stream",
    }
}

fn make_text_response(status: StatusCode, body: &'static str) -> Response<Cow<'static, [u8]>> {
    Response::builder()
        .status(status)
        .header(header::CONTENT_TYPE, "text/plain; charset=utf-8")
        .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, "*")
        .header(header::CACHE_CONTROL, "no-cache")
        .header("X-Content-Type-Options", "nosniff")
        .body(Cow::Borrowed(body.as_bytes()))
        .unwrap_or_else(|_| Response::new(Cow::Borrowed(&[] as &'static [u8])))
}

pub fn handle_dlc_asset_request(
    state: &DlcAssetHostState,
    request: Request<Vec<u8>>,
) -> Response<Cow<'static, [u8]>> {
    let uri_str = request.uri().to_string();

    // Handle CORS preflight
    if request.method() == "OPTIONS" {
        return Response::builder()
            .status(StatusCode::NO_CONTENT)
            .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, "*")
            .header(header::ACCESS_CONTROL_ALLOW_METHODS, "GET, HEAD, OPTIONS")
            .header(header::ACCESS_CONTROL_ALLOW_HEADERS, "*")
            .body(Cow::Borrowed(&[] as &'static [u8]))
            .unwrap_or_else(|_| Response::new(Cow::Borrowed(&[] as &'static [u8])));
    }

    if request.method() != "GET" && request.method() != "HEAD" {
        return make_text_response(StatusCode::METHOD_NOT_ALLOWED, "Method not allowed");
    }

    let parsed = match parse_dlc_asset_url(&uri_str) {
        Ok(parsed) => parsed,
        Err(_) => {
            return make_text_response(StatusCode::BAD_REQUEST, "Invalid DLC asset URL");
        }
    };

    // 1. Verify active projection allowlist (Snapshot is active truth)
    if !state.is_digest_active(&parsed.package_digest) {
        return make_text_response(
            StatusCode::FORBIDDEN,
            "DLC package is not active in the current runtime snapshot",
        );
    }

    // 2. Resolve package directory and enforce containment
    let packages_root = resolve_dlc_packages_root();
    let base_dir = packages_root
        .join(format!("sha256-{}", parsed.package_digest))
        .join("frontend");

    let canonical_base = match base_dir.canonicalize() {
        Ok(path) => path,
        Err(_) => {
            return make_text_response(StatusCode::NOT_FOUND, "DLC package frontend assets not found");
        }
    };

    let target_path = base_dir.join(&parsed.subpath);
    let canonical_target = match target_path.canonicalize() {
        Ok(path) => path,
        Err(_) => {
            return make_text_response(StatusCode::NOT_FOUND, "Asset file not found");
        }
    };

    if !canonical_target.starts_with(&canonical_base) {
        return make_text_response(StatusCode::FORBIDDEN, "Path traversal forbidden");
    }

    if !canonical_target.is_file() {
        return make_text_response(StatusCode::NOT_FOUND, "Requested path is not a file");
    }

    // 3. Check bounded size limit
    let metadata = match std::fs::metadata(&canonical_target) {
        Ok(meta) => meta,
        Err(_) => {
            return make_text_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                "Failed to read asset metadata",
            );
        }
    };

    if metadata.len() > MAX_DLC_ASSET_BYTES as u64 {
        return make_text_response(
            StatusCode::PAYLOAD_TOO_LARGE,
            "Asset file exceeds 20 MiB maximum size",
        );
    }

    // 4. Read bytes
    let bytes = match std::fs::read(&canonical_target) {
        Ok(data) => data,
        Err(_) => {
            return make_text_response(
                StatusCode::INTERNAL_SERVER_ERROR,
                "Failed to read asset file",
            );
        }
    };

    let mime_type = mime_for_path(&canonical_target);

    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, mime_type)
        .header(header::ACCESS_CONTROL_ALLOW_ORIGIN, "*")
        .header(header::CACHE_CONTROL, "public, max-age=31536000, immutable")
        .header("X-Content-Type-Options", "nosniff")
        .body(Cow::Owned(bytes))
        .unwrap_or_else(|_| Response::new(Cow::Borrowed(&[] as &'static [u8])))
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    #[test]
    fn parses_valid_dlc_asset_urls() {
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let url = format!("dlc-asset://localhost/{digest}/frontend/index.js");
        let parsed = parse_dlc_asset_url(&url).unwrap();
        assert_eq!(parsed.package_digest, digest);
        assert_eq!(parsed.subpath, "index.js");

        let url_no_frontend_prefix = format!("dlc-asset://localhost/{digest}/assets/icon.png");
        let parsed2 = parse_dlc_asset_url(&url_no_frontend_prefix).unwrap();
        assert_eq!(parsed2.package_digest, digest);
        assert_eq!(parsed2.subpath, "assets/icon.png");
    }

    #[test]
    fn rejects_invalid_schemes_and_hosts() {
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        assert!(parse_dlc_asset_url(&format!("http://localhost/{digest}/index.js")).is_err());
        assert!(parse_dlc_asset_url(&format!("dlc-asset://evil.com/{digest}/index.js")).is_err());
        assert!(parse_dlc_asset_url(&format!("dlc-asset://localhost/short_digest/index.js")).is_err());
    }

    #[test]
    fn rejects_path_traversal_segments() {
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        assert!(parse_dlc_asset_url(&format!("dlc-asset://localhost/{digest}/../manifest.json")).is_err());
        assert!(parse_dlc_asset_url(&format!("dlc-asset://localhost/{digest}/frontend/../../backend/entry.py")).is_err());
    }

    #[test]
    fn host_state_enforces_active_projection_allowlist() {
        let state = DlcAssetHostState::new();
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";

        // Uninitialized state rejects
        assert!(!state.is_digest_active(digest));

        // Update with active projection
        state.update_projection(RuntimeDlcActivationProjection {
            snapshot_id: "snap_test".to_string(),
            active_dlcs: vec![ActiveDlcProjectionItem {
                dlc_id: "acme.test".to_string(),
                package_version: "1.0.0".to_string(),
                package_digest: format!("sha256:{digest}"),
                frontend_entrypoint: Some("frontend/index.js".to_string()),
            }],
        });

        assert!(state.is_digest_active(digest));
        assert!(state.is_digest_active(&format!("sha256:{digest}")));
        assert!(!state.is_digest_active("ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"));

        // Clear invalidates
        state.clear();
        assert!(!state.is_digest_active(digest));
    }

    #[test]
    fn resolves_correct_mime_types() {
        assert_eq!(mime_for_path(Path::new("index.js")), "text/javascript; charset=utf-8");
        assert_eq!(mime_for_path(Path::new("index.mjs")), "text/javascript; charset=utf-8");
        assert_eq!(mime_for_path(Path::new("style.css")), "text/css; charset=utf-8");
        assert_eq!(mime_for_path(Path::new("icon.svg")), "image/svg+xml");
        assert_eq!(mime_for_path(Path::new("icon.png")), "image/png");
        assert_eq!(mime_for_path(Path::new("data.json")), "application/json; charset=utf-8");
        assert_eq!(mime_for_path(Path::new("font.woff2")), "font/woff2");
        assert_eq!(mime_for_path(Path::new("unknown.bin")), "application/octet-stream");
    }

    #[test]
    fn serves_asset_when_active_and_contained() {
        let temp = tempdir().unwrap();
        let digest = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
        let pkg_frontend = temp
            .path()
            .join("dlcs")
            .join("packages")
            .join(format!("sha256-{digest}"))
            .join("frontend");
        std::fs::create_dir_all(&pkg_frontend).unwrap();
        let js_file = pkg_frontend.join("index.js");
        std::fs::write(&js_file, b"console.log('hello from dlc');").unwrap();

        std::env::set_var("DBFOX_RUNTIME_DIR", temp.path().to_str().unwrap());

        let state = DlcAssetHostState::new();
        state.update_projection(RuntimeDlcActivationProjection {
            snapshot_id: "snap_1".to_string(),
            active_dlcs: vec![ActiveDlcProjectionItem {
                dlc_id: "test.dlc".to_string(),
                package_version: "1.0.0".to_string(),
                package_digest: digest.to_string(),
                frontend_entrypoint: Some("frontend/index.js".to_string()),
            }],
        });

        // Request active asset
        let req = Request::builder()
            .method("GET")
            .uri(format!("dlc-asset://localhost/{digest}/frontend/index.js"))
            .body(Vec::new())
            .unwrap();

        let resp = handle_dlc_asset_request(&state, req);
        assert_eq!(resp.status(), StatusCode::OK);
        assert_eq!(
            resp.headers().get(header::CONTENT_TYPE).unwrap(),
            "text/javascript; charset=utf-8"
        );
        assert_eq!(resp.body().as_ref(), b"console.log('hello from dlc');");

        // Request non-active asset -> 403 Forbidden
        let req_inactive = Request::builder()
            .method("GET")
            .uri("dlc-asset://localhost/ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff/frontend/index.js")
            .body(Vec::new())
            .unwrap();

        let resp_inactive = handle_dlc_asset_request(&state, req_inactive);
        assert_eq!(resp_inactive.status(), StatusCode::FORBIDDEN);
    }
}
