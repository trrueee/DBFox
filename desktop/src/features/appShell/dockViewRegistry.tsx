export type {
  DockRenderContext,
  DockShowToast,
  DockViewContext,
  DockViewContribution,
} from "../dock/types";
export type { DockViewRegistry } from "../dock/dockViewComposition";
export {
  createDockViewRegistry,
  DEFAULT_REGISTRY,
  dockViewTitle,
  getDockView,
  productDockViews,
} from "../dock/dockViewComposition";
export { coreDockViews } from "../dock/coreDockViews";
