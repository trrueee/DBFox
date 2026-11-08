import * as RadioGroup from "@radix-ui/react-radio-group";
import {
  PersonArmsSpreadIcon,
  CheckIcon,
  CaretDownIcon,
  DownloadSimpleIcon,
  MonitorIcon,
  MoonIcon,
  PaletteIcon,
  ArrowCounterClockwiseIcon,
  RowsIcon,
  SlidersHorizontalIcon,
  SunIcon,
  TextAaIcon,
  UploadSimpleIcon,
} from "@/components/icons";
import { useRef } from "react";

import {
  SettingsContent,
  SettingsField,
  SettingsSection,
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
import { AppearancePreview } from "./AppearancePreview";

const THEME_OPTIONS: readonly {
  value: ThemeMode;
  label: string;
  description: string;
  icon: typeof MonitorIcon;
}[] = [
  { value: "system", label: "跟随系统", description: "随系统外观自动切换", icon: MonitorIcon },
  { value: "light", label: "浅色", description: "适合明亮环境", icon: SunIcon },
  { value: "dark", label: "深色", description: "降低暗光环境眩光", icon: MoonIcon },
];

const ACCENT_OPTIONS: readonly { value: AccentColor; label: string }[] = [
  { value: "violet", label: "紫色" },
  { value: "blue", label: "蓝色" },
  { value: "teal", label: "青绿色" },
  { value: "emerald", label: "翡翠绿" },
  { value: "rose", label: "玫瑰红" },
];

const NEUTRAL_OPTIONS: readonly { value: NeutralTone; label: string; description: string }[] = [
  { value: "cool", label: "柔和灰", description: "默认" },
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
  const { appearance, setThemeMode, updateAppearance, replaceAppearance, resetAppearance } = useTheme();
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
    <SettingsContent className="appearance-layout">
      <div className="appearance-controls">
      <p className="appearance-save-status"><CheckIcon size={16} aria-hidden="true" />自动保存</p>

      <SettingsSection
        icon={PaletteIcon}
        title="显示与布局"
        trailing={(
          <Button variant="outline" size="sm" onClick={reset}>
            <ArrowCounterClockwiseIcon size={16} aria-hidden="true" />
            恢复默认
          </Button>
        )}
      >
        <fieldset className="appearance-field">
          <legend className="appearance-field__legend">主题模式</legend>
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
                    <CheckIcon size={16} aria-hidden="true" />
                  </RadioGroup.Indicator>
                </RadioGroup.Item>
              );
            })}
          </RadioGroup.Root>
        </fieldset>

        <SettingsField label="界面密度" htmlFor="appearance-density">
          <Select value={appearance.density} onValueChange={(value) => updateAppearance({ density: value as DensityMode })}>
            <SelectTrigger id="appearance-density"><SelectValue /></SelectTrigger>
            <SelectContent>
              {DENSITY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="界面基准字号" htmlFor="appearance-ui-font-size">
          <Select value={String(appearance.uiFontSize)} onValueChange={(value) => updateFontSize("uiFontSize", value)}>
            <SelectTrigger id="appearance-ui-font-size"><SelectValue /></SelectTrigger>
            <SelectContent>{UI_FONT_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}</SelectContent>
          </Select>
        </SettingsField>


      </SettingsSection>

      <details className="appearance-advanced">
      <summary><SlidersHorizontalIcon size={16} aria-hidden="true" /><span>高级外观设置</span><span className="appearance-advanced__hint">颜色、字体与辅助功能</span><CaretDownIcon className="appearance-advanced__chevron" size={16} aria-hidden="true" /></summary>
      <SettingsSection icon={PaletteIcon} title="颜色">
        <fieldset className="appearance-field">
          <legend className="appearance-field__legend">强调色</legend>
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
                  <CheckIcon size={16} aria-hidden="true" />
                </RadioGroup.Indicator>
              </RadioGroup.Item>
            ))}
          </RadioGroup.Root>
        </fieldset>

        <fieldset className="appearance-field">
          <legend className="appearance-field__legend">中性色调</legend>
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
                  <CheckIcon size={16} aria-hidden="true" />
                </RadioGroup.Indicator>
              </RadioGroup.Item>
            ))}
          </RadioGroup.Root>
        </fieldset>
      </SettingsSection>

      <SettingsSection
        icon={SlidersHorizontalIcon}
        title="字体"
        description="分别选择界面、数据和代码的字体。"
      >
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
        <SettingsField label="代码字体" htmlFor="appearance-code-family" hint="使用本机已安装的字体。">
          <Select value={appearance.codeFontFamily} onValueChange={(value) => updateAppearance({ codeFontFamily: value as CodeFontFamily })}>
            <SelectTrigger id="appearance-code-family" aria-describedby="appearance-code-family-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {CODE_FONT_FAMILY_OPTIONS.map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
      </SettingsSection>

      <SettingsSection
        icon={RowsIcon}
        title="行高与数据表"
        description="调整阅读与表格的信息密度。"
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
        icon={PersonArmsSpreadIcon}
        title="辅助功能"
        description="按阅读与操作习惯调整。"
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
        <SettingsField label="动效" htmlFor="appearance-motion">
          <Select value={appearance.motionMode} onValueChange={(value) => updateAppearance({ motionMode: value as MotionMode })}>
            <SelectTrigger id="appearance-motion" aria-describedby="appearance-motion-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="system">跟随系统</SelectItem>
              <SelectItem value="reduce">减少动效</SelectItem>
            </SelectContent>
          </Select>
        </SettingsField>
      </SettingsSection>

      <SettingsSection
        icon={MonitorIcon}
        title="工作区尺寸"
        description="也可以拖动面板边缘调整尺寸。"
      >
        <SettingsField label="主导航宽度" htmlFor="appearance-sidebar-width">
          <Select value={String(appearance.sidebarWidth)} onValueChange={(value) => updateAppearance({ sidebarWidth: Number(value) })}>
            <SelectTrigger id="appearance-sidebar-width"><SelectValue /></SelectTrigger>
            <SelectContent>
              {SIDEBAR_WIDTH_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
        <SettingsField label="Dock 默认宽度" htmlFor="appearance-artifact-width">
          <Select value={String(appearance.artifactDockWidth)} onValueChange={(value) => updateAppearance({ artifactDockWidth: Number(value) })}>
            <SelectTrigger id="appearance-artifact-width" aria-describedby="appearance-artifact-width-description"><SelectValue /></SelectTrigger>
            <SelectContent>
              {ARTIFACT_DOCK_WIDTH_OPTIONS.map((option) => <SelectItem key={option.value} value={String(option.value)}>{option.label}</SelectItem>)}
            </SelectContent>
          </Select>
        </SettingsField>
      </SettingsSection>

      <SettingsSection
        icon={DownloadSimpleIcon}
        title="导入与导出"
        description="备份或迁移你的外观偏好。"
      >
        <div className="appearance-transfer-actions">
          <Button variant="outline" onClick={exportSettings}><DownloadSimpleIcon size={16} aria-hidden="true" />导出设置</Button>
          <Button variant="outline" onClick={() => importInputRef.current?.click()}><UploadSimpleIcon size={16} aria-hidden="true" />导入设置</Button>
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
        icon={TextAaIcon}
        title="分区字号（px）"
        description="分别调整数据、代码和对话文字。"
      >
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

      </details>
      </div>
      <AppearancePreview />
    </SettingsContent>
  );
}
