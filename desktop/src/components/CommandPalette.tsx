import React, { useState, useEffect, useRef, useMemo } from "react";
import { Search, Terminal } from "lucide-react";
import gsap from "gsap";

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
  const backdropRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const tlRef = useRef<gsap.core.Timeline | null>(null);

  // Enter/exit animation
  useEffect(() => {
    if (open) {
      setMounted(true);
      tlRef.current?.kill();
      const tl = gsap.timeline();
      tl.fromTo(backdropRef.current, { opacity: 0 }, { opacity: 1, duration: 0.15, ease: "power1.out" })
        .fromTo(
          cardRef.current,
          { opacity: 0, y: -16, scale: 0.96 },
          { opacity: 1, y: 0, scale: 1, duration: 0.35, ease: "back.out(1.4)" },
          "-=0.05",
        );
      tlRef.current = tl;
    } else if (!open && mounted) {
      tlRef.current?.kill();
      const tl = gsap.timeline({
        onComplete: () => setMounted(false),
      });
      tl.to(cardRef.current, { opacity: 0, y: -8, scale: 0.97, duration: 0.18, ease: "power2.in" })
        .to(backdropRef.current, { opacity: 0, duration: 0.12, ease: "power1.in" }, "-=0.08");
      tlRef.current = tl;
    }
  }, [open, mounted]);

  // Reset states when opened
  useEffect(() => {
    if (open) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSearch("");
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect
  }, [open]);

  // Fuzzy filter commands
  const filteredCommands = useMemo(() => {
    if (!search.trim()) return commands;
    const query = search.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.name.toLowerCase().includes(query) ||
        cmd.category.toLowerCase().includes(query)
    );
  }, [search, commands]);

  // Adjust selectedIndex boundary on filter changes
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedIndex(0);
  }, [filteredCommands]);

  // Keyboard navigation inside list
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!open) return;

      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev + 1) % Math.max(1, filteredCommands.length));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev - 1 + filteredCommands.length) % Math.max(1, filteredCommands.length));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          filteredCommands[selectedIndex].action();
          onClose();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, filteredCommands, selectedIndex, onClose]);

  // Scroll active item into view
  useEffect(() => {
    if (!listRef.current) return;
    const activeEl = listRef.current.children[selectedIndex] as HTMLElement | null;
    if (activeEl) {
      activeEl.scrollIntoView({ block: "nearest" });
    }
  }, [selectedIndex]);

  if (!mounted) return null;

  return (
    <div
      ref={backdropRef}
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: "rgba(15, 23, 42, 0.4)",
        backdropFilter: "blur(4px)",
        zIndex: 2000,
        display: "flex",
        justifyContent: "center",
        paddingTop: "12vh",
      }}
      onClick={onClose}
    >
      <div
        ref={cardRef}
        className="lab-card"
        style={{
          background: "var(--bg-surface)",
          width: "min(540px, 94vw)",
          maxHeight: "360px",
          borderRadius: 10,
          border: "1px solid var(--border-medium)",
          boxShadow: "var(--shadow-xl)",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Area */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            padding: "10px 14px",
            borderBottom: "1px solid var(--border-light)",
            gap: 10,
            background: "var(--bg-secondary)",
          }}
        >
          <Search size={15} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            className="input-field"
            placeholder="输入指令或进行模糊检索... (Esc 退出)"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              flex: 1,
              border: "none",
              background: "transparent",
              outline: "none",
              fontSize: "0.85rem",
              padding: 0,
              color: "var(--text-primary)",
              boxShadow: "none",
            }}
          />
        </div>

        {/* Action Commands List */}
        <div
          ref={listRef}
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "6px 8px",
            display: "flex",
            flexDirection: "column",
            gap: 1,
          }}
        >
          {filteredCommands.length === 0 ? (
            <div style={{ padding: "20px", fontSize: "0.78rem", color: "var(--text-muted)", textAlign: "center" }}>
              没有找到匹配的快捷指令
            </div>
          ) : (
            filteredCommands.map((cmd, idx) => {
              const isSelected = selectedIndex === idx;
              return (
                <button
                  key={cmd.id}
                  onClick={() => {
                    cmd.action();
                    onClose();
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    width: "100%",
                    border: "none",
                    background: isSelected ? "var(--bg-active)" : "transparent",
                    borderRadius: 6,
                    padding: "7px 12px",
                    cursor: "pointer",
                    textAlign: "left",
                    gap: 10,
                    transition: "background 0.1s",
                  }}
                >
                  <span
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: isSelected ? "var(--accent-indigo)" : "var(--text-muted)",
                      flexShrink: 0,
                    }}
                  >
                    {cmd.icon || <Terminal size={13} />}
                  </span>

                  <div style={{ flex: 1, display: "flex", flexDirection: "column" }}>
                    <span
                      style={{
                        fontSize: "0.78rem",
                        fontWeight: isSelected ? 600 : 500,
                        color: isSelected ? "var(--accent-indigo)" : "var(--text-primary)",
                      }}
                    >
                      {cmd.name}
                    </span>
                    <span
                      style={{
                        fontSize: "0.68rem",
                        color: "var(--text-muted)",
                      }}
                    >
                      {cmd.category}
                    </span>
                  </div>

                  {cmd.shortcut && (
                    <kbd
                      style={{
                        background: isSelected ? "var(--bg-surface)" : "var(--bg-secondary)",
                        border: "1px solid var(--border-medium)",
                        borderRadius: 3,
                        padding: "1px 5px",
                        fontSize: "0.65rem",
                        fontFamily: "var(--font-mono)",
                        color: "var(--text-secondary)",
                        userSelect: "none",
                      }}
                    >
                      {cmd.shortcut}
                    </kbd>
                  )}
                </button>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
};
