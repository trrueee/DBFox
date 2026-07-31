import { lazy, Suspense } from "react";

import type { AppSettingsSection } from "../../types/settings";
import { getSettingsSection } from "./settingsSections";
import "./settings.css";

const ModelSettingsPanel = lazy(async () => {
  const module = await import("./ModelSettingsPanel");
  return { default: module.ModelSettingsPanel };
});

const DiagnosticsPage = lazy(async () => {
  const module = await import("../../pages/DiagnosticsPage");
  return { default: module.DiagnosticsPage };
});

interface SettingsPageProps {
  section: AppSettingsSection;
  showToast: (message: string, type?: "success" | "error" | "warning" | "info") => void;
}

export function SettingsPage({ section, showToast }: SettingsPageProps) {
  const definition = getSettingsSection(section);

  return (
    <section className="settings-page" aria-labelledby="settings-page-title">
      <div className="settings-page__inner">
        <header className="settings-page__header">
          <h1 id="settings-page-title">{definition.title}</h1>
        </header>
        <div className="settings-page__content">
          <Suspense fallback={<div className="settings-page__loading">正在加载设置…</div>}>
            {section === "model" ? (
              <ModelSettingsPanel showToast={showToast} />
            ) : (
              <DiagnosticsPage onToast={showToast} chrome="workspace" />
            )}
          </Suspense>
        </div>
      </div>
    </section>
  );
}
