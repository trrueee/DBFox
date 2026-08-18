type Listener = () => void;

let openDatabaseDialogListener: Listener | null = null;

export function onOpenDatabaseDialog(listener: Listener): () => void {
  openDatabaseDialogListener = listener;
  return () => {
    if (openDatabaseDialogListener === listener) {
      openDatabaseDialogListener = null;
    }
  };
}

export function emitOpenDatabaseDialog(): void {
  openDatabaseDialogListener?.();
}
