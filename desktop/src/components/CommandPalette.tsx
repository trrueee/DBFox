import React, { useMemo } from "react";
import { Search } from "lucide-react";
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
  description?: string;
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
        label="全局搜索"
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
            placeholder="搜索对话、数据表、字段和操作…"
          />
          <CommandKbd>Esc</CommandKbd>
        </CommandSearch>

        <CommandList>
          <CommandEmpty>没有找到相关内容</CommandEmpty>
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
                    {command.icon || <Search size={13} />}
                  </CommandItemIcon>
                  <CommandItemLabel>
                    <span>{command.name}</span>
                    {command.description ? (
                      <small>{command.description}</small>
                    ) : null}
                  </CommandItemLabel>
                  {command.shortcut ? (
                    <CommandKbd>{command.shortcut}</CommandKbd>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>

      </Command>
    </div>
  );
};
