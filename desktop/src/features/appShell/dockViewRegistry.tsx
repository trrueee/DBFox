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
export { dataDockViews } from "../dock/dataDockViews";
export { workspaceDockViews } from "../dock/workspaceDockViews";
