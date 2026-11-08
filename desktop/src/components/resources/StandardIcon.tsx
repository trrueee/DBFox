import {
  ArrowDownIcon,
  ArrowUpIcon,
  AtIcon,
  BookOpenIcon,
  CubeIcon,
  FilmSlateIcon,
  ImageIcon,
  MusicNotesIcon,
  PauseIcon,
  PlayIcon,
  PlusIcon,
  ArrowsClockwiseIcon,
  RepeatIcon,
  SquareIcon,
  TerminalWindowIcon,
  TrashIcon,
  XIcon,
  GameControllerIcon,
  LightbulbIcon,
  TableIcon,
  CaretRightIcon,
} from "@/components/icons";
import type { HostIconName } from "../../features/dlc/types";

const ICONS = {
  plus: PlusIcon, x: XIcon, "refresh-cw": ArrowsClockwiseIcon, play: PlayIcon, pause: PauseIcon,
  square: SquareIcon, repeat: RepeatIcon, terminal: TerminalWindowIcon, "at-sign": AtIcon,
  music: MusicNotesIcon, "book-open": BookOpenIcon, box: CubeIcon, image: ImageIcon, clapperboard: FilmSlateIcon,
  "arrow-up": ArrowUpIcon, "arrow-down": ArrowDownIcon, "trash-2": TrashIcon,
  "game-controller": GameControllerIcon, lightbulb: LightbulbIcon, table: TableIcon,
  "caret-right": CaretRightIcon,
} satisfies Record<HostIconName, typeof PlusIcon>;

const FILLED_ICONS = new Set<HostIconName>(["play", "pause", "square"]);

/** The same pinned artwork and roles are shared by Core and isolated DLC frontends. */
export function StandardIcon({ name, size = 20, className = "" }: {
  name: HostIconName; size?: number; className?: string;
}) {
  const Icon = ICONS[name];
  return <Icon size={size} weight={FILLED_ICONS.has(name) ? "fill" : "regular"}
    aria-hidden="true" className={`standard-icon ${className}`} />;
}
