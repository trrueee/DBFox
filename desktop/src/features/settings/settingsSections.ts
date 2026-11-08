import {
  PulseIcon,
  BrainIcon,
  PuzzlePieceIcon,
  PaletteIcon,
  type IconComponent,
} from "@/components/icons";

import type { AppSettingsSection } from "../../types/settings";

export interface SettingsSectionDefinition {
  id: AppSettingsSection;
  title: string;
  icon: IconComponent;
}

export const SETTINGS_SECTIONS: readonly SettingsSectionDefinition[] = [
  {
    id: "appearance",
    title: "外观与字号",
    icon: PaletteIcon,
  },
  {
    id: "model",
    title: "模型服务",
    icon: BrainIcon,
  },
  {
    id: "dlc",
    title: "扩展",
    icon: PuzzlePieceIcon,
  },
  {
    id: "diagnostics",
    title: "诊断与日志",
    icon: PulseIcon,
  },
];

export function getSettingsSection(section: AppSettingsSection): SettingsSectionDefinition {
  return SETTINGS_SECTIONS.find((item) => item.id === section) ?? SETTINGS_SECTIONS[0];
}
