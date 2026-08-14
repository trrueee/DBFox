# DBFox 生产图标资产

本目录只保留 WebView 运行时实际加载的两份 PNG。Windows、macOS、Linux 和移动端安装图标位于 `desktop/src-tauri/icons/`，不由前端静态目录重复承载。

## 运行资产

```text
png/fox-icon-app-transparent-512.png  # 标题栏、工作区和桌面图标生成母版
png/fox-icon-ai-tight-256.png         # 启动状态中的 AI 品牌图形
```

## 桌面图标生成

`png/fox-icon-app-transparent-512.png` 是桌面图标的透明母版。Windows、macOS、Linux 及移动端打包资产先由 Tauri 官方图标生成器生成，再用仓库脚本补齐 Windows Shell 的 ICO 帧并同步 favicon：

```powershell
Set-Location desktop
npm run tauri -- icon public/assets/fox/png/fox-icon-app-transparent-512.png --output src-tauri/icons
python scripts/finalize_desktop_icons.py
```

不要为 Windows 任务栏母版重复增加透明边距；Windows Shell 本身会预留图标安全区。生成脚本会补齐 Windows ICO 尺寸并清理不可见的 alpha 插值边缘，不改变品牌图形。
