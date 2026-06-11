import React, { useState, useEffect, useRef, useMemo } from "react";
import { Search, CornerDownLeft } from "lucide-react";

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
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mounted, setMounted] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setSearch("");
      setSelectedIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (mounted) {
      const timer = setTimeout(() => setMounted(false), 200);
      return () => clearTimeout(timer);
    }
  }, [open, mounted]);

  const filteredCommands = useMemo(() => {
    if (!search.trim()) return commands;
    const query = search.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.name.toLowerCase().includes(query) ||
        cmd.category.toLowerCase().includes(query),
    );
  }, [search, commands]);

  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const cmd of filteredCommands) {
      const list = map.get(cmd.category) || [];
      list.push(cmd);
      map.set(cmd.category, list);
    }
    return Array.from(map.entries());
  }, [filteredCommands]);

  const flatIndexMap = useMemo(() => {
    const map = new Map<number, { cat: string; idx: number }>();
    let idx = 0;
    for (const [cat, items] of grouped) {
      for (let i = 0; i < items.length; i++) {
        map.set(idx, { cat, idx: i });
        idx += 1;
      }
    }
    return map;
  }, [grouped]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [filteredCommands]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      const size = Math.max(1, flatIndexMap.size);
      if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIndex((p) => (p + 1) % size); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIndex((p) => (p - 1 + size) % size); return; }
      if (e.key === "Enter") {
        e.preventDefault();
        const target = flatIndexMap.get(selectedIndex);
        if (target) {
          const item = grouped.find(([c]) => c === target.cat)?.[1][target.idx];
          if (item) { item.action(); onClose(); }
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, selectedIndex, flatIndexMap, grouped, onClose]);

  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-cmd-index="${selectedIndex}"]`) as HTMLElement | null;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!mounted) return null;

  let runningFlat = 0;

  return (
    <div className="hifi-command-overlay" onClick={onClose} role="presentation">
      <div className="hifi-command-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="命令面板">
        <div className="hifi-command-search">
          <Search size={15} className="hifi-command-search-icon" />
          <input
            ref={inputRef}
            type="text"
            className="hifi-command-input"
            placeholder="输入指令或搜索表、字段、功能…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <kbd className="hifi-command-kbd">Esc</kbd>
        </div>

        <div ref={listRef} className="hifi-command-list">
          {grouped.length === 0 ? (
            <div className="hifi-command-empty">没有找到匹配的指令</div>
          ) : (
            grouped.map(([category, items]) => (
              <div key={category} className="hifi-command-group">
                <div className="hifi-command-category">{category}</div>
                {items.map((cmd) => {
                  const currentFlat = runningFlat;
                  runningFlat += 1;
                  const active = currentFlat === selectedIndex;
                  return (
                    <button
                      key={cmd.id}
                      type="button"
                      data-cmd-index={currentFlat}
                      className={`hifi-command-item${active ? " active" : ""}`}
                      onClick={() => { cmd.action(); onClose(); }}
                    >
                      <span className="hifi-command-item-icon">
                        {cmd.icon || <CornerDownLeft size={13} />}
                      </span>
                      <span className="hifi-command-item-label">{cmd.name}</span>
                      {cmd.shortcut ? (
                        <kbd className="hifi-command-kbd">{cmd.shortcut}</kbd>
                      ) : null}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="hifi-command-footer">
          <span>↑↓ 导航</span>
          <span>↵ 打开</span>
          <span>Esc 关闭</span>
        </div>
      </div>
    </div>
  );
};
