import * as RadioGroup from "@radix-ui/react-radio-group";
import {
  Accessibility,
  Check,
  Code2,
  Download,
  Eye,
  MessageSquareText,
  Monitor,
  Moon,
  Palette,
  RotateCcw,
  Rows3,
  SlidersHorizontal,
  Sun,
  Table2,
  Type,
  Upload,
} from "lucide-react";
import { useRef } from "react";

import {
  SettingsContent,
  SettingsField,
  SettingsSection,
  SettingsStatus,
  SettingsToggle,
} from "../../components/settings";
import { Button } from "../../components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../../components/ui/select";
import { useTheme } from "../../hooks/themeContext";
import type {
  AccentColor,
  AppearancePreferences,
  CodeFontFamily,
  ContrastMode,
  DataFontFamily,
  DensityMode,
  MotionMode,
  NeutralTone,
  NullStyle,
  ThemeMode,
  UiFontFamily,
} from "../../lib/appearance";
import {
  APPEARANCE_EXPORT_FILENAME,
  APPEARANCE_RANGES,
  FONT_SIZE_RANGES,
  parseAppearancePreferences,
  serializeAppearancePreferences,
} from "../../lib/appearance";
import "./AppearanceSettingsPanel.css";

const THEME_OPTIONS: readonly {
  value: ThemeMode;
  label: string;
  description: string;
  icon: typeof Monitor;
}[] = [
  { value: "system", label: "跟随系统", description: "随 Windows 外观自动切换", icon: Monitor },
  { value: "light", label: "浅色", description: "适合明亮环境", icon: Sun },
  { value: "dark", label: "深色", description: "降低暗光环境眩光", icon: Moon },
];

const ACCENT_OPTIONS: readonly { value: AccentColor; label: string }[] = [
  { value: "violet", label: "DBFox 紫" },
  { value: "blue", label: "数据蓝" },
  { value: "teal", label: "青绿色" },
  { value: "emerald", label: "翡翠绿" },
  { value: "rose", label: "玫瑰红" },
];

const NEUTRAL_OPTIONS: readonly { value: NeutralTone; label: string; description: string }[] = [
  { value: "cool", label: "冷灰蓝", description: "DBFox 默认" },
  { value: "neutral", label: "中性灰", description: "克制、低色偏" },
  { value: "warm", label: "暖灰", description: "柔和、低眩光" },
];

type FontOption = Readonly<{ value: number; label: string }>;

function createFontOptions(range: Readonly<{ min: number; max: number; defaultValue: number }>): readonly FontOption[] {
  return Array.from({ length: range.max - range.min + 1 }, (_, index) => {
    const value = range.min + index;
    return {
      value,
      label: value === range.defaultValue ? `${value} px（默认）` : `${value} px`,
    };
  });
}

const UI_FONT_OPTIONS = createFontOptions(FONT_SIZE_RANGES.ui);
const DATA_FONT_OPTIONS = createFontOptions(FONT_SIZE_RANGES.data);
const CODE_FONT_OPTIONS = createFontOptions(FONT_SIZE_RANGES.code);
const AGENT_FONT_OPTIONS = createFontOptions(FONT_SIZE_RANGES.agent);

const DENSITY_OPTIONS: readonly { value: DensityMode; label: string }[] = [
  { value: "compact", label: "紧凑" },
  { value: "standard", label: "标准" },
  { value: "comfortable", label: "舒适" },
];

const UI_FONT_FAMILY_OPTIONS: readonly { value: UiFontFamily; label: string }[] = [
  { value: "system", label: "系统界面字体" },
  { value: "humanist", label: "清晰人文" },
  { value: "compact", label: "紧凑界面" },
];

const DATA_FONT_FAMILY_OPTIONS: readonly { value: DataFontFamily; label: string }[] = [
  { value: "system", label: "系统字体" },
  { value: "dense", label: "高密度数据字体" },
  { value: "mono", label: "等宽数据字体" },
];

const CODE_FONT_FAMILY_OPTIONS: readonly { value: CodeFontFamily; label: string }[] = [
  { value: "system", label: "系统等宽字体" },
  { value: "cascadia", label: "Cascadia / Consolas" },
  { value: "jetbrains", label: "JetBrains Mono 优先" },
];

const NULL_STYLE_OPTIONS: readonly { value: NullStyle; label: string }[] = [
  { value: "muted", label: "弱化文本" },
  { value: "badge", label: "中性标签" },
  { value: "plain", label: "普通文本" },
];

function createRangeOptions(range: Readonly<{ min: number; max: number; defaultValue: number; step: number }>, suffix: string) {
  const length = Math.round((range.max - range.min) / range.step) + 1;
  return Array.from({ length }, (_, index) => {
    const value = Number((range.min + index * range.step).toFixed(2));
    return { value, label: value === range.defaultValue ? `${value}${suffix}（默认）` : `${value}${suffix}` };
  });
}

const AGENT_LINE_HEIGHT_OPTIONS = createRangeOptions(APPEARANCE_RANGES.agentLineHeight, " 倍");
const CODE_LINE_HEIGHT_OPTIONS = createRangeOptions(APPEARANCE_RANGES.codeLineHeight, " 倍");
const TABLE_ROW_HEIGHT_OPTIONS = createRangeOptions(APPEARANCE_RANGES.tableRowHeight, " px");
const SIDEBAR_WIDTH_OPTIONS = createRangeOptions(APPEARANCE_RANGES.sidebarWidth, " px");
const ARTIFACT_DOCK_WIDTH_OPTIONS = createRangeOptions(APPEARANCE_RANGES.artifactDockWidth, "%");

interface AppearanceSettingsPanelProps {
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}

export function AppearanceSettingsPanel({ showToast }: AppearanceSettingsPanelProps) {
  const { appearance, theme, setThemeMode, updateAppearance, replaceAppearance, resetAppearance } = useTheme();
  const importInputRef = useRef<HTMLInputElement>(null);

  const updateFontSize = (
    key: "uiFontSize" | "dataFontSize" | "codeFontSize" | "agentFontSize",
    value: string,
  ) => {
    updateAppearance({ [key]: Number(value) } as Pick<AppearancePreferences, typeof key>);
  };

  const reset = () => {
    resetAppearance();
    showToast("外观设置已恢复默认值", "success");
  };

  const exportSettings = () => {
    const blob = new Blob([serializeAppearancePreferences(appearance)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = APPEARANCE_EXPORT_FILENAME;
    anchor.click();
    URL.revokeObjectURL(url);
    showToast("外观设置已导出，不包含凭据和业务数据", "success");
  };

  const importSettings = async (file: File | undefined) => {
    if (!file) return;
    if (file.size > 64 * 1024) {
      showToast("设置文件超过 64 KiB，已拒绝导入", "error");
      return;
    }
    try {
      replaceAppearance(parseAppearancePreferences(await file.text()));
      showToast("外观设置已导入并应用", "success");
    } catch {
      showToast("设置文件格式或版本无效，未修改当前设置", "error");
    } finally {
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };

  return (
    <SettingsContent>
      <SettingsStatus
        tone="info"
        label="即时预览，自动保存"
        description="设置只保存在本机，不会进入项目内容、会话或模型上下文。"
        meta={theme === "dark" ? "当前：深色" : "当前：浅色"}
      />

      <SettingsSection
        icon={Palette}
        title="主题与色彩"
        description="使用受控色板保持文本、状态色和焦点环在浅色与深色模式下都清晰可辨。"
        trailing={(
          <Button variant="outline" size="sm" onClick={reset}>
            <RotateCcw size={14} aria-hidden="true" />
            恢复默认
          </Button>
        )}
      >
        <fieldset className="appearance-field">
          <legend className="appearance-field__legend">主题模式</legend>
          <p className="appearance-field__hint">“跟随系统”会监听系统颜色模式变化。</p>
          <RadioGroup.Root
            className="appearance-theme-grid"
            value={appearance.themeMode}
            onValueChange={(value) => setThemeMode(value as ThemeMode)}
            aria-label="主题模式"
          >
            {THEME_OPTIONS.map((option) => {
              const Icon = option.icon;
              return (
                <RadioGroup.Item
                  key={option.value}
                  value={option.value}
                  className="appearance-theme-option"
                >
                  <Icon size={16} aria-hidden="true" />
                  <span className="appearance-theme-option__copy">
                    <strong>{option.label}</strong>
                    <span>{option.description}</span>
                  </span>
                  <RadioGroup.Indicator className="appearance-choice-indicator">
                    <Check size={14} aria-hidden="true" />
                  </RadioGroup.Indicator>
                </RadioGroup.Item>
              );
            })}
          </RadioGroup.Root>
        </fieldset>

        <fieldset className="appearance-field">
          <legend className="appearance-field__legend">强调色</legend>
          <p className="appearance-field__hint">用于选中、主操作、焦点和图表主序列，不改变成功或危险等语义色。</p>
          <RadioGroup.Root
            className="appearance-accent-grid"
            value={appearance.accentColor}
            onValueChange={(value) => updateAppearance({ accentColor: value as AccentColor })}
            aria-label="强调色"
          >
            {ACCENT_OPTIONS.map((option) => (
              <RadioGroup.Item
                key={option.value}
                value={option.value}
                className="appearance-accent-option"
                data-accent-value={option.value}
                aria-label={option.label}
                title={option.label}
              >
                <span className="appearance-accent-option__swatch" aria-hidden="true" />
                <span>{option.label}</span>
                <RadioGroup.Indicator className="appearance-accent-option__indicator">
                  <Check size={14} aria-hidden="true" />
                </RadioGroup.Indicator>
              </RadioGroup.Item>
            ))}
          </RadioGroup.Root>
        </fieldset>

        <fieldset className="appearance-field">
          <legend className="appearance-field__legend">中性色调</legend>
          <p className="appearance-field__hint">控制窗口、侧栏、面板和边框的底色倾向。</p>
          <RadioGroup.Root
            className="appearance-neutral-grid"
            value={appearance.neutralTone}
            onValueChange={(value) => updateAppearance({ neutralTone: value as NeutralTone })}
            aria-label="中性色调"
          >
            {NEUTRAL_OPTIONS.map((option) => (
              <RadioGroup.Item
                key={option.value}
                value={option.value}
                className="appearance-neutral-option"
                data-neutral-value={option.value}
              >
                <span className="appearance-neutral-option__preview" aria-hidden="true">
                  <span />
                  <span />
                </span>
                <span>
                  <strong>{option.label}</strong>
                  <small>{option.description}</small>
                </span>
                <RadioGroup.Indicator className="appearance-choice-indicator">
                  <Check size={14} aria-hidden="true" />
                </RadioGroup.Indicator>
              </RadioGroup.Item>
            ))}
          </RadioGroup.Root>
        </fieldset>
      </SettingsSection>

      <SettingsSection
        icon={SlidersHorizontal}
        title="密度与字体"
        description="密度统一调整工具栏、按钮、侧栏和面板留白；字体预设只使用本机字体栈，离线也可稳定回退。"
      >
        <SettingsField label="界面密度" htmlFor="appearance-density" hint="紧凑适合宽表和高信息密度，舒适适合高 DPI 与触控板操作。">
          <Select value={appearance.density} onValueChange={(value) => updateAppearance({ density: value as DensityMode })}>
            <SelectTrigger id="appearance-density" aria-describedby="appearance-density-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DENSITY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="界面字体" htmlFor="appearance-ui-family" hint="侧栏、工具栏、标签页和设置页面。">
          <Select value={appearance.uiFontFamily} onValueChange={(value) => updateAppearance({ uiFontFamily: value as UiFontFamily })}>
            <SelectTrigger id="appearance-ui-family" aria-describedby="appearance-ui-family-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {UI_FONT_FAMILY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="数据字体" htmlFor="appearance-data-family" hint="高密度数据预设使用表格数字对齐和较窄的本机字体栈。">
          <Select value={appearance.dataFontFamily} onValueChange={(value) => updateAppearance({ dataFontFamily: value as DataFontFamily })}>
            <SelectTrigger id="appearance-data-family" aria-describedby="appearance-data-family-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DATA_FONT_FAMILY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="代码字体" htmlFor="appearance-code-family" hint="未安装首选字体时自动落到系统等宽字体，不从网络下载字体。">
          <Select value={appearance.codeFontFamily} onValueChange={(value) => updateAppearance({ codeFontFamily: value as CodeFontFamily })}>
            <SelectTrigger id="appearance-code-family" aria-describedby="appearance-code-family-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CODE_FONT_FAMILY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
      </SettingsSection>

      <SettingsSection
        icon={Rows3}
        title="行高与数据表"
        description="保持专业工具的信息密度，同时允许按屏幕与阅读习惯调整。"
      >
        <SettingsField label="Agent 对话行高" htmlFor="appearance-agent-line-height">
          <Select value={String(appearance.agentLineHeight)} onValueChange={(value) => updateAppearance({ agentLineHeight: Number(value) })}>
            <SelectTrigger id="appearance-agent-line-height"><SelectValue /></SelectTrigger>
            <SelectContent>
              {AGENT_LINE_HEIGHT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="SQL 与代码行高" htmlFor="appearance-code-line-height">
          <Select value={String(appearance.codeLineHeight)} onValueChange={(value) => updateAppearance({ codeLineHeight: Number(value) })}>
            <SelectTrigger id="appearance-code-line-height"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CODE_LINE_HEIGHT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="数据表默认行高" htmlFor="appearance-table-row-height">
          <Select value={String(appearance.tableRowHeight)} onValueChange={(value) => updateAppearance({ tableRowHeight: Number(value) })}>
            <SelectTrigger id="appearance-table-row-height"><SelectValue /></SelectTrigger>
            <SelectContent>
              {TABLE_ROW_HEIGHT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="NULL 显示" htmlFor="appearance-null-style">
          <Select value={appearance.tableNullStyle} onValueChange={(value) => updateAppearance({ tableNullStyle: value as NullStyle })}>
            <SelectTrigger id="appearance-null-style"><SelectValue /></SelectTrigger>
            <SelectContent>
              {NULL_STYLE_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <div className="appearance-toggle-grid">
          <SettingsToggle checked={appearance.tableGridLines} onCheckedChange={(tableGridLines) => updateAppearance({ tableGridLines })} label="显示表格网格线" description="同时控制横向和纵向分隔线。" compact />
          <SettingsToggle checked={appearance.tableZebraStripes} onCheckedChange={(tableZebraStripes) => updateAppearance({ tableZebraStripes })} label="使用斑马纹" description="隔行使用轻微的中性色背景。" compact />
          <SettingsToggle checked={appearance.freezePrimaryKey} onCheckedChange={(freezePrimaryKey) => updateAppearance({ freezePrimaryKey })} label="冻结主键列" description="宽表横向滚动时保持第一主键列可见。" compact />
        </div>
      </SettingsSection>

      <SettingsSection
        icon={Accessibility}
        title="辅助功能"
        description="系统缩放始终由 Electron 和操作系统处理；这里提供额外的对比度与动效控制。"
      >
        <SettingsField label="对比度" htmlFor="appearance-contrast">
          <Select value={appearance.contrastMode} onValueChange={(value) => updateAppearance({ contrastMode: value as ContrastMode })}>
            <SelectTrigger id="appearance-contrast"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="system">跟随系统</SelectItem>
              <SelectItem value="high">增强对比度</SelectItem>
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="动效" htmlFor="appearance-motion" hint="跟随系统时仍会尊重 prefers-reduced-motion。">
          <Select value={appearance.motionMode} onValueChange={(value) => updateAppearance({ motionMode: value as MotionMode })}>
            <SelectTrigger id="appearance-motion" aria-describedby="appearance-motion-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="system">跟随系统</SelectItem>
              <SelectItem value="reduce">减少动效</SelectItem>
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsStatus tone="neutral" label="系统缩放：自动" description="Windows 125%、150%、200% 缩放由 WebView 按实际 DPI 应用，不通过 CSS zoom 二次缩放。" />
      </SettingsSection>

      <SettingsSection
        icon={Monitor}
        title="工作区尺寸"
        description="窗口尺寸由原生窗口状态恢复；下列选项只控制应用内部面板。"
      >
        <SettingsField label="主导航宽度" htmlFor="appearance-sidebar-width">
          <Select value={String(appearance.sidebarWidth)} onValueChange={(value) => updateAppearance({ sidebarWidth: Number(value) })}>
            <SelectTrigger id="appearance-sidebar-width"><SelectValue /></SelectTrigger>
            <SelectContent>
              {SIDEBAR_WIDTH_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="Agent 工件面板宽度" htmlFor="appearance-artifact-width" hint="当前产品使用右侧工件面板，不存在独立底部面板，因此不提供无效的“底部高度”设置。">
          <Select value={String(appearance.artifactDockWidth)} onValueChange={(value) => updateAppearance({ artifactDockWidth: Number(value) })}>
            <SelectTrigger id="appearance-artifact-width" aria-describedby="appearance-artifact-width-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ARTIFACT_DOCK_WIDTH_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
      </SettingsSection>

      <SettingsSection
        icon={Download}
        title="导入与导出"
        description="JSON 文件只包含本页设置；严格校验版本与字段，不包含 Token、API Key、连接凭据、SQL、会话或日志。"
      >
        <div className="appearance-transfer-actions">
          <Button variant="outline" onClick={exportSettings}><Download size={16} aria-hidden="true" />导出设置</Button>
          <Button variant="outline" onClick={() => importInputRef.current?.click()}><Upload size={16} aria-hidden="true" />导入设置</Button>
          <input
            ref={importInputRef}
            className="appearance-file-input"
            type="file"
            accept="application/json,.json"
            aria-label="选择 DBFox 外观设置文件"
            onChange={(event) => void importSettings(event.target.files?.[0])}
          />
        </div>
      </SettingsSection>

      <SettingsSection
        icon={Type}
        title="分区字号（px）"
        description="按实际像素分别调整高密度界面、数据内容、SQL/代码和 Agent 对话；标题与辅助文字仍保持既有层级。"
      >
        <SettingsField
          label="界面基准字号"
          htmlFor="appearance-ui-font-size"
          hint="以侧栏、标签和工具栏文字为基准，标题和正文按同一档位同步调整。"
        >
          <Select
            value={String(appearance.uiFontSize)}
            onValueChange={(value) => updateFontSize("uiFontSize", value)}
          >
            <SelectTrigger id="appearance-ui-font-size" aria-describedby="appearance-ui-font-size-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {UI_FONT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField
          label="数据字号"
          htmlFor="appearance-data-font-size"
          hint="数据预览表格、字段名和单元格内容。"
        >
          <Select
            value={String(appearance.dataFontSize)}
            onValueChange={(value) => updateFontSize("dataFontSize", value)}
          >
            <SelectTrigger id="appearance-data-font-size" aria-describedby="appearance-data-font-size-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DATA_FONT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField
          label="SQL 与代码字号"
          htmlFor="appearance-code-font-size"
          hint="SQL 编辑器、代码块和格式化数据预览。"
        >
          <Select
            value={String(appearance.codeFontSize)}
            onValueChange={(value) => updateFontSize("codeFontSize", value)}
          >
            <SelectTrigger id="appearance-code-font-size" aria-describedby="appearance-code-font-size-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CODE_FONT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField
          label="Agent 对话字号"
          htmlFor="appearance-agent-font-size"
          hint="回答正文、输入框、运行时间线和工具详情。"
        >
          <Select
            value={String(appearance.agentFontSize)}
            onValueChange={(value) => updateFontSize("agentFontSize", value)}
          >
            <SelectTrigger id="appearance-agent-font-size" aria-describedby="appearance-agent-font-size-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {AGENT_FONT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
      </SettingsSection>

      <SettingsSection
        icon={Eye}
        title="实时预览"
        description="预览使用与工作区相同的语义 token；切换选项时立即更新。"
      >
        <div className="appearance-preview" aria-label="当前外观预览">
          <div className="appearance-preview__toolbar">
            <span className="appearance-preview__brand">DBFox</span>
            <span>数据预览</span>
            <span className="appearance-preview__active">已选择</span>
          </div>
          <div className="appearance-preview__grid">
            <div className="appearance-preview__sample">
              <div className="appearance-preview__sample-title"><Table2 size={14} aria-hidden="true" /> 数据表</div>
              <table>
                <thead><tr><th>id</th><th>status</th><th>amount</th></tr></thead>
                <tbody><tr><td>1024</td><td>completed</td><td>¥ 328.00</td></tr></tbody>
              </table>
            </div>
            <div className="appearance-preview__sample appearance-preview__agent">
              <div className="appearance-preview__sample-title"><MessageSquareText size={14} aria-hidden="true" /> Agent</div>
              <p>已完成查询，共找到 18 条符合条件的记录。</p>
            </div>
            <div className="appearance-preview__sample appearance-preview__code">
              <div className="appearance-preview__sample-title"><Code2 size={14} aria-hidden="true" /> SQL</div>
              <code>SELECT status, COUNT(*) FROM orders GROUP BY status;</code>
            </div>
          </div>
        </div>
      </SettingsSection>
    </SettingsContent>
  );
}
