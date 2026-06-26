import React, { useMemo } from "react";
import { CornerDownLeft, Search } from "lucide-react";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandItemIcon,
  CommandItemLabel,
  CommandKbd,
  CommandList,
  CommandSearch,
} from "./ui";
import "./CommandPalette.css";

export interface CommandItem {
  id: string;
  name: string;
  category: string;
  shortcut?: string;
  icon?: React.ReactNode;
  action: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  commands: CommandItem[];
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose, commands }) => {
  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const command of commands) {
      const list = map.get(command.category) || [];
      list.push(command);
      map.set(command.category, list);
    }
    return Array.from(map.entries());
  }, [commands]);

  const runCommand = (command: CommandItem) => {
    command.action();
    onClose();
  };

  if (!open) return null;

  return (
    <div className="dbfox-command-overlay" onClick={onClose} role="presentation">
      <Command
        label="命令面板"
        loop
        onClick={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onClose();
          }
        }}
      >
        <CommandSearch>
          <Search size={15} className="dbfox-command-search-icon" />
          <CommandInput
            autoFocus
            placeholder="输入指令或搜索表、字段、功能..."
          />
          <CommandKbd>Esc</CommandKbd>
        </CommandSearch>

        <CommandList>
          <CommandEmpty>没有找到匹配的指令</CommandEmpty>
          {grouped.map(([category, items]) => (
            <CommandGroup
              key={category}
              heading={<span className="dbfox-command-category">{category}</span>}
            >
              {items.map((command) => (
                <CommandItem
                  key={command.id}
                  value={`${command.name} ${command.category} ${command.shortcut || ""}`}
                  onSelect={() => runCommand(command)}
                >
                  <CommandItemIcon>
                    {command.icon || <CornerDownLeft size={13} />}
                  </CommandItemIcon>
                  <CommandItemLabel>{command.name}</CommandItemLabel>
                  {command.shortcut ? (
                    <CommandKbd>{command.shortcut}</CommandKbd>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>

        <div className="dbfox-command-footer">
          <span>↑↓ 导航</span>
          <span>↵ 打开</span>
          <span>Esc 关闭</span>
        </div>
      </Command>
    </div>
  );
};
