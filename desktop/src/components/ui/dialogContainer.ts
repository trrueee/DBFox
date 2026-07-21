let dialogContainer: HTMLElement | null = null;

export function setDialogContainer(element: HTMLElement | null) {
  dialogContainer = element;
}

export function getDialogContainer() {
  return dialogContainer;
}
