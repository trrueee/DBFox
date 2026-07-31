import { CommandPalette } from "../../components/CommandPalette";
import {
  useAppCommands,
  type UseAppCommandsProps,
} from "./useAppCommands";
import { useConversationStore } from "../../stores/conversationStore";

interface AppCommandPaletteProps extends Omit<UseAppCommandsProps, "conversations"> {
  onClose: () => void;
}

export function AppCommandPalette({
  onClose,
  ...commandSources
}: AppCommandPaletteProps) {
  const conversations = useConversationStore((state) => state.summaries);
  const { commandItems } = useAppCommands({
    ...commandSources,
    conversations,
  });
  return (
    <CommandPalette
      open
      onClose={onClose}
      commands={commandItems}
    />
  );
}
