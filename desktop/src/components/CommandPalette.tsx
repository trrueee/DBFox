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
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
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
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="dbfox-command-dialog">
        <DialogHeader className="sr-only">
          <DialogTitle>全局搜索</DialogTitle>
          <DialogDescription>搜索任务、项目、对话和应用操作。</DialogDescription>
        </DialogHeader>
      <Command
        label="全局搜索"
        loop
      >
        <CommandSearch>
          <Search size={16} className="dbfox-command-search-icon" />
          <CommandInput
            autoFocus
            placeholder="搜索任务、项目和操作…"
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
                  value={command.id}
                  keywords={[
                    command.name,
                    command.category,
                    command.description || "",
                    command.shortcut || "",
                  ]}
                  onSelect={() => runCommand(command)}
                >
                  <CommandItemIcon>
                    {command.icon || <Search size={14} />}
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
      </DialogContent>
    </Dialog>
  );
};
