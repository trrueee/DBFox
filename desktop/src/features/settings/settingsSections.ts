import { Bug, Cpu, type LucideIcon } from "lucide-react";

import type { AppSettingsSection } from "../../types/settings";

export interface SettingsSectionDefinition {
  id: AppSettingsSection;
  title: string;
  icon: LucideIcon;
}

export const SETTINGS_SECTIONS: readonly SettingsSectionDefinition[] = [
  {
    id: "model",
    title: "模型服务",
    icon: Cpu,
  },
  {
    id: "diagnostics",
    title: "诊断与日志",
    icon: Bug,
  },
];

export function getSettingsSection(section: AppSettingsSection): SettingsSectionDefinition {
  return SETTINGS_SECTIONS.find((item) => item.id === section) ?? SETTINGS_SECTIONS[0];
}
