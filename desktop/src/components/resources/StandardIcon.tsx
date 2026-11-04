import { ArrowDown, ArrowUp, AtSign, BookOpen, Box, Clapperboard, Image, Music2, Pause, Play, Plus, RefreshCw, Repeat2, Square, Terminal, Trash2, X } from "lucide-react";
import type { HostIconName } from "../../features/dlc/types";

const ICONS = {
  plus: Plus, x: X, "refresh-cw": RefreshCw, play: Play, pause: Pause,
  square: Square, repeat: Repeat2, terminal: Terminal, "at-sign": AtSign,
  music: Music2, "book-open": BookOpen, box: Box, image: Image, clapperboard: Clapperboard,
  "arrow-up": ArrowUp, "arrow-down": ArrowDown, "trash-2": Trash2,
} satisfies Record<HostIconName, typeof Plus>;

/** A small, static Lucide subset shared with isolated DLC frontends. */
export function StandardIcon({ name, size = 16, className = "" }: {
  name: HostIconName; size?: number; className?: string;
}) {
  const Icon = ICONS[name];
  return <Icon size={size} strokeWidth={1.75} aria-hidden="true" className={`standard-icon ${className}`} />;
}
