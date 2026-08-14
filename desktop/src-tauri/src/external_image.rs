use reqwest::header::{CONTENT_LENGTH, CONTENT_TYPE, LOCATION};
use reqwest::{redirect::Policy, StatusCode, Url};
use serde::Serialize;
use std::io::Write;
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr, SocketAddr, ToSocketAddrs};
use std::path::Path;
use std::sync::LazyLock;
use std::time::Duration;
use tauri_plugin_dialog::DialogExt;

const MAX_IMAGE_BYTES: usize = 20 * 1024 * 1024;
const MAX_REDIRECTS: usize = 3;
static DOWNLOAD_SLOTS: LazyLock<tokio::sync::Semaphore> =
    LazyLock::new(|| tokio::sync::Semaphore::new(2));

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct SavedExternalImage {
    status: &'static str,
    file_name: Option<String>,
    byte_count: Option<usize>,
}

struct DownloadedImage {
    bytes: Vec<u8>,
    extension: &'static str,
    suggested_name: String,
}

#[tauri::command]
pub(crate) async fn save_external_image(
    app: tauri::AppHandle,
    url: String,
) -> Result<SavedExternalImage, String> {
    let permit = DOWNLOAD_SLOTS
        .acquire()
        .await
        .map_err(|_| "图片下载服务暂不可用".to_string())?;
    let downloaded = download_image(&url).await?;
    drop(permit);
    let selected = app
        .dialog()
        .file()
        .set_title("保存图片副本")
        .set_file_name(&downloaded.suggested_name)
        .add_filter("图片", &[downloaded.extension])
        .blocking_save_file();
    let Some(selected) = selected else {
        return Ok(SavedExternalImage {
            status: "cancelled",
            file_name: None,
            byte_count: None,
        });
    };
    let mut destination = selected
        .into_path()
        .map_err(|_| "所选保存位置不是本地文件路径".to_string())?;
    destination.set_extension(downloaded.extension);
    persist_atomically(&destination, &downloaded.bytes)?;
    Ok(SavedExternalImage {
        status: "saved",
        file_name: destination
            .file_name()
            .map(|name| name.to_string_lossy().into_owned()),
        byte_count: Some(downloaded.bytes.len()),
    })
}

async fn download_image(raw_url: &str) -> Result<DownloadedImage, String> {
    let mut current = validate_download_url(raw_url)?;
    for redirect_count in 0..=MAX_REDIRECTS {
        let client = client_for_url(&current)?;
        let mut response = client
            .get(current.clone())
            .header(
                reqwest::header::ACCEPT,
                "image/avif,image/webp,image/png,image/jpeg,image/gif,image/bmp,image/x-icon",
            )
            .header(reqwest::header::USER_AGENT, "DBFox/1 image-save")
            .send()
            .await
            .map_err(|_| "无法下载图片，请检查网络或图片地址".to_string())?;

        if response.status().is_redirection() {
            if redirect_count == MAX_REDIRECTS {
                return Err("图片地址重定向次数过多".to_string());
            }
            let location = response
                .headers()
                .get(LOCATION)
                .and_then(|value| value.to_str().ok())
                .ok_or_else(|| "图片地址返回了无效重定向".to_string())?;
            let redirected = current
                .join(location)
                .map_err(|_| "图片地址返回了无效重定向".to_string())?;
            current = validate_download_url(redirected.as_str())?;
            continue;
        }

        if response.status() != StatusCode::OK {
            return Err("图片服务器未返回可下载内容".to_string());
        }
        if response
            .headers()
            .get(CONTENT_LENGTH)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.parse::<usize>().ok())
            .is_some_and(|length| length > MAX_IMAGE_BYTES)
        {
            return Err("图片超过 20 MB 保存上限".to_string());
        }
        let media_type = response
            .headers()
            .get(CONTENT_TYPE)
            .and_then(|value| value.to_str().ok())
            .and_then(|value| value.split(';').next())
            .map(str::trim)
            .ok_or_else(|| "图片服务器未提供有效内容类型".to_string())?;
        let extension = extension_for_media_type(media_type)
            .ok_or_else(|| "仅支持保存 PNG、JPEG、GIF、WebP、AVIF、BMP 或 ICO 图片".to_string())?;

        let mut bytes = Vec::new();
        while let Some(chunk) = response
            .chunk()
            .await
            .map_err(|_| "图片下载过程中断".to_string())?
        {
            if bytes.len().saturating_add(chunk.len()) > MAX_IMAGE_BYTES {
                return Err("图片超过 20 MB 保存上限".to_string());
            }
            bytes.extend_from_slice(&chunk);
        }
        if !matches_image_signature(&bytes, extension) {
            return Err("下载内容与图片格式不匹配".to_string());
        }
        return Ok(DownloadedImage {
            suggested_name: suggested_file_name(&current, extension),
            bytes,
            extension,
        });
    }
    unreachable!("redirect loop always returns or continues within a bounded range")
}

fn client_for_url(url: &Url) -> Result<reqwest::Client, String> {
    let host = url
        .host_str()
        .ok_or_else(|| "图片地址缺少主机名".to_string())?
        .to_string();
    let port = url.port_or_known_default().unwrap_or(443);
    let addresses: Vec<SocketAddr> = (host.as_str(), port)
        .to_socket_addrs()
        .map_err(|_| "无法解析图片服务器地址".to_string())?
        .filter(|address| is_public_ip(address.ip()))
        .collect();
    if addresses.is_empty() {
        return Err("图片地址指向本机或私有网络，已拒绝下载".to_string());
    }
    let client = reqwest::Client::builder()
        .no_proxy()
        .redirect(Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(20))
        .resolve_to_addrs(&host, &addresses)
        .build()
        .map_err(|_| "无法初始化安全图片下载器".to_string())?;
    Ok(client)
}

fn validate_download_url(raw_url: &str) -> Result<Url, String> {
    if raw_url.is_empty() || raw_url.trim() != raw_url {
        return Err("图片地址不能为空或包含首尾空格".to_string());
    }
    let url = Url::parse(raw_url).map_err(|_| "图片地址无效".to_string())?;
    if url.scheme() != "https"
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.port_or_known_default() != Some(443)
    {
        return Err("仅允许下载使用标准端口且不含凭据的 HTTPS 图片".to_string());
    }
    if url
        .host_str()
        .is_some_and(|host| host.eq_ignore_ascii_case("localhost") || host.ends_with(".localhost"))
    {
        return Err("图片地址不能指向本机".to_string());
    }
    Ok(url)
}

fn is_public_ip(ip: IpAddr) -> bool {
    match ip {
        IpAddr::V4(ip) => is_public_ipv4(ip),
        IpAddr::V6(ip) => is_public_ipv6(ip),
    }
}

fn is_public_ipv4(ip: Ipv4Addr) -> bool {
    let [a, b, c, _] = ip.octets();
    !(a == 0
        || a == 10
        || a == 127
        || (a == 100 && (64..=127).contains(&b))
        || (a == 169 && b == 254)
        || (a == 172 && (16..=31).contains(&b))
        || (a == 192 && b == 0 && c == 0)
        || (a == 192 && b == 0 && c == 2)
        || (a == 192 && b == 168)
        || (a == 198 && (b == 18 || b == 19))
        || (a == 198 && b == 51 && c == 100)
        || (a == 203 && b == 0 && c == 113)
        || a >= 224)
}

fn is_public_ipv6(ip: Ipv6Addr) -> bool {
    if let Some(mapped) = ip.to_ipv4_mapped() {
        return is_public_ipv4(mapped);
    }
    let segments = ip.segments();
    !(ip.is_unspecified()
        || ip.is_loopback()
        || ip.is_multicast()
        || (segments[0] & 0xfe00) == 0xfc00
        || (segments[0] & 0xffc0) == 0xfe80
        || (segments[0] == 0x2001 && segments[1] == 0x0db8))
}

fn extension_for_media_type(media_type: &str) -> Option<&'static str> {
    match media_type.to_ascii_lowercase().as_str() {
        "image/png" => Some("png"),
        "image/jpeg" => Some("jpg"),
        "image/gif" => Some("gif"),
        "image/webp" => Some("webp"),
        "image/avif" => Some("avif"),
        "image/bmp" => Some("bmp"),
        "image/x-icon" | "image/vnd.microsoft.icon" => Some("ico"),
        _ => None,
    }
}

fn matches_image_signature(bytes: &[u8], extension: &str) -> bool {
    match extension {
        "png" => bytes.starts_with(b"\x89PNG\r\n\x1a\n"),
        "jpg" => bytes.starts_with(&[0xff, 0xd8, 0xff]),
        "gif" => bytes.starts_with(b"GIF87a") || bytes.starts_with(b"GIF89a"),
        "webp" => bytes.len() >= 12 && bytes.starts_with(b"RIFF") && &bytes[8..12] == b"WEBP",
        "bmp" => bytes.starts_with(b"BM"),
        "ico" => bytes.starts_with(&[0, 0, 1, 0]),
        "avif" => {
            bytes.len() >= 12
                && &bytes[4..8] == b"ftyp"
                && (&bytes[8..12] == b"avif" || &bytes[8..12] == b"avis")
        }
        _ => false,
    }
}

fn suggested_file_name(url: &Url, extension: &str) -> String {
    let stem = url
        .path_segments()
        .and_then(|mut segments| segments.next_back())
        .and_then(|name| Path::new(name).file_stem())
        .and_then(|name| name.to_str())
        .unwrap_or("dbfox-image");
    let sanitized: String = stem
        .chars()
        .filter(|character| {
            character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.')
        })
        .take(80)
        .collect();
    format!(
        "{}.{}",
        if sanitized.is_empty() {
            "dbfox-image"
        } else {
            &sanitized
        },
        extension
    )
}

fn persist_atomically(destination: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = destination
        .parent()
        .filter(|path| !path.as_os_str().is_empty())
        .ok_or_else(|| "保存位置无效".to_string())?;
    let mut temporary = tempfile::NamedTempFile::new_in(parent)
        .map_err(|_| "无法在所选目录创建临时文件".to_string())?;
    temporary
        .write_all(bytes)
        .and_then(|_| temporary.as_file_mut().sync_all())
        .map_err(|_| "写入图片时发生错误".to_string())?;
    temporary
        .persist(destination)
        .map_err(|_| "无法完成图片保存".to_string())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_only_credential_free_standard_https_urls() {
        assert!(validate_download_url("https://example.com/a.png").is_ok());
        for value in [
            "http://example.com/a.png",
            "https://user:secret@example.com/a.png",
            "https://localhost/a.png",
            "https://example.com:8443/a.png",
            " https://example.com/a.png",
        ] {
            assert!(validate_download_url(value).is_err(), "{value}");
        }
    }

    #[test]
    fn rejects_non_public_addresses() {
        for value in [
            "127.0.0.1",
            "10.0.0.1",
            "169.254.169.254",
            "192.168.1.1",
            "203.0.113.1",
            "::1",
            "fe80::1",
            "fd00::1",
            "2001:db8::1",
        ] {
            assert!(!is_public_ip(value.parse().unwrap()), "{value}");
        }
        assert!(is_public_ip("1.1.1.1".parse().unwrap()));
        assert!(is_public_ip("2606:4700:4700::1111".parse().unwrap()));
    }

    #[test]
    fn validates_media_types_signatures_and_names() {
        assert_eq!(extension_for_media_type("image/png"), Some("png"));
        assert_eq!(extension_for_media_type("image/svg+xml"), None);
        assert!(matches_image_signature(b"\x89PNG\r\n\x1a\nrest", "png"));
        assert!(!matches_image_signature(b"<html>", "png"));
        let url = Url::parse("https://example.com/a%20bad.png?token=secret").unwrap();
        assert_eq!(suggested_file_name(&url, "png"), "a20bad.png");
    }
}
