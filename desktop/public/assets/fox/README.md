# Fox Small Icon Frontend Assets

这套素材是基于你上传的 SVG 做的 **保真裁剪版小图标**：没有重新手绘狐狸，所以不会因为重画导致比例变形。

## 推荐文件

```txt
svg/fox-icon-tight.svg        # 推荐小图标：16px / 24px / sidebar，不带盒子
svg/fox-icon-ai-tight.svg     # 推荐 AI 入口：狐狸头 + 紫色星芒，不带盒子
svg/fox-icon.svg              # 保守裁剪版，留白更多，适合 32px+
svg/fox-icon-ai.svg           # 保守裁剪 + AI 星芒
svg/fox-icon-app.svg          # 带浅色圆角底的小 App Icon / favicon 候选
svg/fox-icon-source-crop.svg  # 保留原始坐标的裁剪版，给设计软件使用
png/*.png                     # 16 / 24 / 32 / 48 / 64 / 128 / 192 / 256 / 512 PNG 导出
src/FoxIcon.tsx               # React 封装组件，使用 <img> 引用 SVG
src/fox-icon.css              # CSS 尺寸工具类与颜色 token
```

## React 使用

把 `svg` 目录复制到：

```txt
public/assets/fox/svg/
```

```tsx
import { FoxIcon } from "./FoxIcon";

export function HeaderLogo() {
  return <FoxIcon size={24} variant="tight" />;
}

export function AIAssistantEntry() {
  return <FoxIcon size={32} variant="ai-tight" />;
}
```

## 普通 HTML

```html
<img src="/assets/fox/svg/fox-icon-tight.svg" width="24" height="24" alt="Fox icon" />
```

## 重要说明

这个 SVG 是保真自动描摹素材，文件比较大，**不要 inline 到 React JSX 里**。推荐用 `<img>`、CSS `background-image`、Next/Image 或直接作为静态资源引用。

这个版本只做了：

1. 裁剪成正方形小图标；
2. 标准化为 `viewBox="0 0 128 128"`；
3. 不带 DBFox 盒子；
4. 生成 SVG / PNG / React wrapper。

## Desktop App Icon Pipeline

`png/fox-icon-app-transparent-512.png` 是桌面图标的高清透明母版。标题栏直接从这份干净的 alpha 画布缩放到 24px，避免 `fox-icon-tight.svg` 在小尺寸下出现近白边缘像素。Windows、macOS、Linux 及移动端打包资产先由 Tauri 官方图标生成器生成，再用 Pillow 补齐 Windows Shell 的 128px ICO 帧并同步 favicon：

```powershell
cd desktop
npm run tauri -- icon public/assets/fox/png/fox-icon-app-transparent-512.png --output src-tauri/icons
python scripts/finalize_desktop_icons.py
```

不要为 Windows 任务栏母版重复增加透明边距；Windows Shell 本身会预留图标安全区，二次加边会让任务栏图形显得过小。Pillow 脚本会从透明内容边界生成占比至少 80% 的 Windows ICO、补全官方生成器缺少的 Windows 尺寸，并清理 alpha 小于 8 的不可见插值边缘，不改变品牌图形。
