fn main() {
    configure_bundle_resources_for_profile();

    for path in [
        "tauri.conf.json",
        "icons/32x32.png",
        "icons/64x64.png",
        "icons/128x128.png",
        "icons/128x128@2x.png",
        "icons/icon.png",
        "icons/icon.icns",
        "icons/icon.ico",
    ] {
        println!("cargo:rerun-if-changed={path}");
    }

    let app_manifest = tauri_build::AppManifest::new().commands(&[
        "get_engine_config",
        "get_engine_startup_status",
        "restart_python_engine",
        "open_diagnostic_logs",
        "open_external_https_url",
        "save_external_image",
        "pick_dlc_package",
        "export_diagnostic_bundle",
        "pick_project_folder",
        "list_project_folder",
        "read_project_file",
    ]);
    tauri_build::try_build(tauri_build::Attributes::new().app_manifest(app_manifest))
        .expect("failed to build DBFox Tauri application manifest");
}

fn configure_bundle_resources_for_profile() {
    if std::env::var("PROFILE").as_deref() == Ok("release") {
        return;
    }

    // Debug builds launch `python -m engine.main` and never consume the frozen
    // external binary. Keep Tauri's release resource validation fail-closed in
    // release, while allowing cargo test/clippy and tauri dev from a clean clone.
    let mut config = std::env::var("TAURI_CONFIG")
        .ok()
        .map(|value| serde_json::from_str::<serde_json::Value>(&value))
        .transpose()
        .expect("TAURI_CONFIG must be valid JSON")
        .unwrap_or_else(|| serde_json::json!({}));
    let root = config
        .as_object_mut()
        .expect("TAURI_CONFIG root must be an object");
    let bundle = root
        .entry("bundle")
        .or_insert_with(|| serde_json::json!({}))
        .as_object_mut()
        .expect("TAURI_CONFIG.bundle must be an object");
    bundle.insert("externalBin".to_string(), serde_json::Value::Null);
    bundle.insert("resources".to_string(), serde_json::Value::Null);
    std::env::set_var(
        "TAURI_CONFIG",
        serde_json::to_string(&config).expect("debug Tauri config should serialize"),
    );
}
