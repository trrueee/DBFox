import {
  SunIcon,
  MoonIcon,
} from "@/components/icons";
import { Button } from "./ui/button";
import { useTheme } from "../hooks/themeContext";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      title={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
      aria-label={theme === "dark" ? "切换到浅色模式" : "切换到深色模式"}
    >
      {theme === "dark" ? (
        <SunIcon size={16} className="text-[hsl(var(--primary))] transition-transform hover:rotate-45" />
      ) : (
        <MoonIcon size={16} className="text-[hsl(var(--primary))] transition-transform hover:-rotate-12" />
      )}
    </Button>
  );
}
