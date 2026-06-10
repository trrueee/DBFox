import { Sun, Moon } from "lucide-react";
import { Button } from "./ui/button";
import { useTheme } from "../hooks/useTheme";

export function ThemeToggle() {
  const { theme, toggle } = useTheme();

  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      title={theme === "dark" ? "Switch to light" : "Switch to dark"}
    >
      {theme === "dark" ? (
        <Sun size={14} className="text-[hsl(var(--warning))] transition-transform hover:rotate-45" />
      ) : (
        <Moon size={14} className="text-[hsl(var(--primary))] transition-transform hover:-rotate-12" />
      )}
    </Button>
  );
}
