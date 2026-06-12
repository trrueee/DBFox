# DataBox Mascot v3 — Premium Snow Fox

> white, clean, cute but professional · less pig-like · more product-logo quality

![DataBox Mascot v3 — Premium Snow Fox](./assets/databox-mascot-v3-premium-snow-fox-board.svg)

## 设计目标

这版页面用于定义 DataBox 的产品化 Mascot / Icon 方向：用一只更可爱、更柔和的北极狐作为 DataBox 的品牌识别，但不能做成普通表情包、玩偶贴纸或过度卡通的头像。

核心目标是：**可爱但克制，轻盈但专业，像真实软件产品里的品牌资产**。

## 关键词

- **Premium Snow Fox**：雪白、干净、轻盈、冷静
- **Cute but professional**：有亲和力，但不是幼稚玩偶
- **DataBox tray**：下方保留数据盒 / 数据托盘符号，强化产品语义
- **AI accent**：紫色星形 / 光点作为 AI 分析状态提示
- **Ice blue UI**：浅冰蓝、白色、轻微玻璃感，形成清爽产品气质

## 页面结构

### 1. Header

顶部标题使用：

```text
DataBox Mascot v3 — Premium Snow Fox
```

副标题表达设计方向：

```text
white, clean, cute but professional · less pig-like · more product-logo quality
```

Header 的作用不是解释太多，而是快速给出视觉判断标准。

### 2. App Icon

主图标需要放在左侧大卡片中，保持清晰的产品 icon 展示方式。

设计要求：

- 使用圆角方形 icon tile
- 主体是白色北极狐
- 狐狸表情柔和、闭眼微笑、轻微治愈感
- 头部可以更圆润可爱，但整体不能变成猪脸或纯圆脸
- 保留两个尖耳朵，让用户一眼能识别为狐狸
- 下方加入 DataBox 托盘符号，用紫色描边强调
- 右上角加入蓝紫色星形，作为 AI / snow sparkle 识别点

### 3. In Product UI

右侧展示该 mascot 如何进入真实产品界面。

用途：

- 验证图标在产品内是否自然
- 验证浅色 UI 中是否有足够识别度
- 形成 DataBox 的 AI analyzing 状态视觉记忆点

建议场景：

```text
AI is analyzing
schema / SQL / chart
```

该区域应使用浅色面板、圆角、轻阴影和非常低噪声的信息块。

### 4. Asset Set

底部资产组用于定义 mascot 在不同状态下的延展方式。

推荐资产：

| Asset | 用途 | 设计重点 |
|---|---|---|
| Rail Mark | 左侧导航 / favicon | 极简，16px 仍能识别 |
| No Datasource | 空数据源状态 | 狐狸 + 数据盒，表达等待连接 |
| Agent Running | Agent 执行中 | 紫色星形 + 青色 loading 圈 |
| No Result | 无结果状态 | 搜索 / 分析失败，但保持轻松 |

### 5. Bottom Key

底部保留一条 key bar，用于把设计语言压缩成一句话：

```text
Key: cute angular fox face / shield silhouette / ice blue-white / purple AI accent / DataBox tray / legible down to 16px
```

## 视觉规范

### 色彩

| Token | 用途 | 建议 |
|---|---|---|
| Snow White | 狐狸主体 / 卡片 | `#FFFFFF` |
| Ice Blue | 阴影 / 背景 | `#EAF6FF` |
| Soft Border | 卡片边框 | `#DDEAF8` |
| AI Violet | AI 星形 / 数据盒描边 | `#7667F2` |
| Data Cyan | 状态点 / loading | `#55D4CF` |
| Text Dark | 标题文字 | `#162033` |
| Text Muted | 说明文字 | `#7C8798` |

### 形状

- 大容器：36px 圆角
- 卡片：22–28px 圆角
- App icon tile：50–60px 圆角
- 狐狸脸：介于圆润和盾形之间，不要纯圆
- 星形：四角柔和，避免尖锐攻击感

### 阴影

整体使用轻阴影，避免重拟物。

```css
box-shadow: 0 18px 36px rgba(201, 216, 234, 0.45);
```

## 生成提示词

```text
Design a cute premium concept board for “DataBox Mascot v3 — Premium Snow Fox”. Create a soft, clean, organized design presentation sheet with a large rounded white board, pastel ice-blue background, and rounded cards. The mascot is a cute arctic fox for a local-first AI database workbench. The fox should be white, clean, soft, friendly, and professional, with pointed ears, gentle closed happy eyes, a small smile, a subtle DataBox tray on the lower face, and a blue-violet AI sparkle near one ear. Include sections: App Icon, In Product UI, Asset Set, Rail Mark, No Datasource, Agent Running, and No Result. Use snow white, ice blue, soft violet, and cyan accents. Keep it cute but productized, less plush toy, more premium SaaS brand asset.
```

负面提示词：

```text
messy, ugly, cluttered, dark, heavy shadow, low quality, pig-like face, too childish, plush toy, random sticker, overly complex, realistic animal, anime, sharp aggressive fox, bad typography, low contrast, noisy gradient
```

## 落地建议

1. 先固定主 icon：App Icon 和 Rail Mark 要最先定稿。
2. 再延展状态图：No Datasource、Agent Running、No Result 保持同一套形状语言。
3. 最后进入产品 UI：确认在 16px、24px、32px、64px 下都可读。
4. 所有 asset 保持白色主体、冰蓝阴影、紫色 AI 点缀、青色数据状态点。