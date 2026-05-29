import { useState, useCallback, useEffect, useRef } from "react";
import { HardDrive } from "lucide-react";

export interface MenuItemDef {
  label: string;
  shortcut?: string;
  action?: () => void;
  disabled?: boolean;
  separator?: boolean;
}

export interface MenuDef {
  id: string;
  label: string;
  items: MenuItemDef[];
}

interface MenuBarProps {
  menus: MenuDef[];
}

export const MenuBar: React.FC<MenuBarProps> = ({ menus }) => {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [highlightIndex, setHighlightIndex] = useState(0);
  const menuRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const closeMenu = useCallback(() => {
    setOpenMenuId(null);
    setHighlightIndex(0);
  }, []);

  const openMenu = useCallback((id: string) => {
    setOpenMenuId(id);
    setHighlightIndex(0);
  }, []);

  const toggleMenu = useCallback(
    (id: string) => {
      setOpenMenuId((prev) => (prev === id ? null : id));
      setHighlightIndex(0);
    },
    [],
  );

  // Click outside to close
  useEffect(() => {
    if (!openMenuId) return;
    const handleClick = (e: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(e.target as Node)
      ) {
        closeMenu();
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [openMenuId, closeMenu]);

  // Keyboard navigation
  useEffect(() => {
    if (!openMenuId) return;
    const currentMenu = menus.find((m) => m.id === openMenuId);
    if (!currentMenu) return;

    const visibleItems = currentMenu.items.filter((item) => !item.separator);

    const handleKeyDown = (e: KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setHighlightIndex((prev) =>
            prev >= visibleItems.length - 1 ? 0 : prev + 1,
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setHighlightIndex((prev) =>
            prev <= 0 ? visibleItems.length - 1 : prev - 1,
          );
          break;
        case "ArrowRight": {
          e.preventDefault();
          const idx = menus.findIndex((m) => m.id === openMenuId);
          const nextIdx = idx >= menus.length - 1 ? 0 : idx + 1;
          setOpenMenuId(menus[nextIdx].id);
          setHighlightIndex(0);
          break;
        }
        case "ArrowLeft": {
          e.preventDefault();
          const idx = menus.findIndex((m) => m.id === openMenuId);
          const prevIdx = idx <= 0 ? menus.length - 1 : idx - 1;
          setOpenMenuId(menus[prevIdx].id);
          setHighlightIndex(0);
          break;
        }
        case "Enter":
          e.preventDefault();
          if (visibleItems[highlightIndex]?.action) {
            const action = visibleItems[highlightIndex].action!;
            closeMenu();
            // Delay action to let the menu close first
            setTimeout(() => action(), 0);
          }
          break;
        case "Escape":
          e.preventDefault();
          closeMenu();
          break;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [openMenuId, menus, highlightIndex, closeMenu]);

  // Alt+key to open menu
  useEffect(() => {
    const handleAltKey = (e: KeyboardEvent) => {
      if (!e.altKey || e.ctrlKey || e.metaKey) return;
      const key = e.key.toLowerCase();
      const matched = menus.find(
        (m) => m.label.charAt(0).toLowerCase() === key || m.label.startsWith(key),
      );
      if (matched && matched.id !== openMenuId) {
        e.preventDefault();
        openMenu(matched.id);
      }
    };
    window.addEventListener("keydown", handleAltKey);
    return () => window.removeEventListener("keydown", handleAltKey);
  }, [menus, openMenuId, openMenu]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (!dropdownRef.current || !openMenuId) return;
    const items = dropdownRef.current.querySelectorAll('[data-menu-item]');
    if (items[highlightIndex]) {
      (items[highlightIndex] as HTMLElement).scrollIntoView({
        block: "nearest",
      });
    }
  }, [highlightIndex, openMenuId]);

  // Window controls
  const handleMinimize = useCallback(() => {
    try {
      // Dynamic import to avoid issues when Tauri API is unavailable
      import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
        getCurrentWindow().minimize();
      }).catch(() => {});
    } catch { /* non-Tauri env */ }
  }, []);

  const handleMaximize = useCallback(() => {
    try {
      import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
        getCurrentWindow().toggleMaximize();
      }).catch(() => {});
    } catch { /* non-Tauri env */ }
  }, []);

  const handleClose = useCallback(() => {
    try {
      import("@tauri-apps/api/window").then(({ getCurrentWindow }) => {
        getCurrentWindow().close();
      }).catch(() => {});
    } catch { /* non-Tauri env */ }
  }, []);

  const openMenuDef = menus.find((m) => m.id === openMenuId);
  const visibleItems = openMenuDef
    ? openMenuDef.items.filter((item) => !item.separator)
    : [];

  return (
    <div
      ref={menuRef}
      data-tauri-drag-region
      className="menu-bar"
      style={{
        display: "flex",
        alignItems: "center",
        height: 30,
        background: "var(--bg-secondary)",
        borderBottom: "1px solid var(--border-light)",
        userSelect: "none",
        WebkitUserSelect: "none",
        flexShrink: 0,
        zIndex: 100,
      }}
    >
      {/* Brand */}
      <span
        style={{
          fontSize: "0.78rem",
          fontWeight: 800,
          color: "var(--accent-indigo)",
          letterSpacing: "-0.01em",
          display: "flex",
          alignItems: "center",
          gap: 4,
          padding: "0 10px",
          height: "100%",
          flexShrink: 0,
        }}
      >
        <HardDrive size={12} style={{ color: "var(--accent-indigo)" }} />
        DataBox
      </span>

      {/* Menu items */}
      <div style={{ display: "flex", alignItems: "center", height: "100%" }}>
        {menus.map((menu) => {
          const isOpen = openMenuId === menu.id;
          return (
            <div
              key={menu.id}
              style={{ position: "relative", height: "100%" }}
            >
              <button
                className="menu-bar-item"
                onClick={(e) => {
                  e.stopPropagation();
                  toggleMenu(menu.id);
                }}
                onMouseEnter={() => {
                  if (openMenuId && openMenuId !== menu.id) {
                    openMenu(menu.id);
                  }
                }}
                style={{
                  padding: "3px 8px",
                  fontSize: "0.78rem",
                  color: "var(--text-primary)",
                  background: isOpen ? "var(--bg-hover)" : "transparent",
                  border: "none",
                  borderRadius: 3,
                  cursor: "pointer",
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  fontFamily: "var(--font-body)",
                }}
              >
                {menu.label}
              </button>

              {/* Dropdown */}
              {isOpen && (
                <div
                  ref={dropdownRef}
                  className="menu-dropdown"
                  style={{
                    position: "absolute",
                    top: "100%",
                    left: -4,
                    minWidth: 210,
                    background: "var(--bg-surface)",
                    border: "1px solid var(--border-light)",
                    borderRadius: 4,
                    padding: "4px 0",
                    boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
                    zIndex: 2000,
                    maxHeight: "calc(100vh - 40px)",
                    overflowY: "auto",
                  }}
                >
                  {menu.items.map((item, i) => {
                    if (item.separator) {
                      return (
                        <div
                          key={`sep-${i}`}
                          style={{
                            height: 1,
                            background: "var(--border-light)",
                            margin: "4px 0",
                          }}
                        />
                      );
                    }
                    const itemIndex = visibleItems.indexOf(item);
                    const isHighlighted = itemIndex === highlightIndex;
                    return (
                      <button
                        key={i}
                        data-menu-item
                        disabled={item.disabled}
                        className="menu-dropdown-item"
                        onClick={() => {
                          if (item.action) {
                            const action = item.action;
                            closeMenu();
                            setTimeout(() => action(), 0);
                          }
                        }}
                        onMouseEnter={() => {
                          if (itemIndex >= 0) setHighlightIndex(itemIndex);
                        }}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          width: "100%",
                          height: 26,
                          padding: "0 10px 0 22px",
                          fontSize: "0.76rem",
                          fontFamily: "var(--font-body)",
                          color: item.disabled
                            ? "var(--text-muted)"
                            : isHighlighted
                              ? "var(--accent-indigo)"
                              : "var(--text-primary)",
                          background: isHighlighted
                            ? "var(--bg-active)"
                            : "transparent",
                          border: "none",
                          cursor: item.disabled ? "default" : "pointer",
                          textAlign: "left" as const,
                          whiteSpace: "nowrap" as const,
                        }}
                      >
                        <span>{item.label}</span>
                        {item.shortcut && (
                          <span
                            style={{
                              marginLeft: 24,
                              fontSize: "0.68rem",
                              color: "var(--text-muted)",
                              fontFamily: "var(--font-mono)",
                            }}
                          >
                            {item.shortcut}
                          </span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Spacer (drag region) */}
      <div style={{ flex: 1, height: "100%" }} data-tauri-drag-region />

      {/* Window controls */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          height: "100%",
          flexShrink: 0,
        }}
      >
        <button
          className="win-control-btn"
          onClick={handleMinimize}
          title="最小化"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 34,
            height: "100%",
            border: "none",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: "0.85rem",
            cursor: "pointer",
            fontFamily: "var(--font-body)",
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10">
            <rect x="1" y="8" width="8" height="1" fill="currentColor" />
          </svg>
        </button>
        <button
          className="win-control-btn"
          onClick={handleMaximize}
          title="最大化"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 34,
            height: "100%",
            border: "none",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: "0.85rem",
            cursor: "pointer",
            fontFamily: "var(--font-body)",
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10">
            <rect
              x="1.5"
              y="1.5"
              width="7"
              height="7"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
            />
          </svg>
        </button>
        <button
          className="win-control-btn win-control-close"
          onClick={handleClose}
          title="关闭"
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            width: 34,
            height: "100%",
            border: "none",
            background: "transparent",
            color: "var(--text-secondary)",
            fontSize: "0.85rem",
            cursor: "pointer",
            fontFamily: "var(--font-body)",
          }}
        >
          <svg width="10" height="10" viewBox="0 0 10 10">
            <line
              x1="1"
              y1="1"
              x2="9"
              y2="9"
              stroke="currentColor"
              strokeWidth="1.2"
            />
            <line
              x1="9"
              y1="1"
              x2="1"
              y2="9"
              stroke="currentColor"
              strokeWidth="1.2"
            />
          </svg>
        </button>
      </div>
    </div>
  );
};
