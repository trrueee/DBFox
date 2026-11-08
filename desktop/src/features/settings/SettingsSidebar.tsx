import {
  ArrowLeftIcon,
  GearIcon,
} from "@/components/icons";

import type { AppSettingsSection } from "../../types/settings";
import { SETTINGS_SECTIONS } from "./settingsSections";
import "./settings.css";

interface SettingsSidebarProps {
  section: AppSettingsSection;
  onSectionChange: (section: AppSettingsSection) => void;
  onClose: () => void;
}

export function SettingsSidebar({
  section,
  onSectionChange,
  onClose,
}: SettingsSidebarProps) {
  return (
    <aside className="settings-sidebar" aria-label="设置导航">
      <button type="button" className="settings-sidebar__back" onClick={onClose}>
        <ArrowLeftIcon size={16} aria-hidden="true" />
        <span>返回工作区</span>
      </button>

      <div className="settings-sidebar__title">
        <GearIcon size={22} aria-hidden="true" />
        <h2>设置</h2>
      </div>

      <nav className="settings-sidebar__nav">
        {SETTINGS_SECTIONS.map((item) => {
          const Icon = item.icon;
          const selected = section === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`settings-sidebar__item${selected ? " is-active" : ""}`}
              aria-current={selected ? "page" : undefined}
              onClick={() => onSectionChange(item.id)}
            >
              <Icon size={20} aria-hidden="true" />
              <span>{item.title}</span>
            </button>
          );
        })}
      </nav>
    </aside>
  );
}
