export type {
  DockRenderContext,
  DockShowToast,
  DockViewContext,
  DockViewContribution,
} from "../dock/types";
export {
  createDockViewRegistry,
  dockViewTitle,
  getDockView,
  productDockViews,
} from "../dock/dockViewComposition";
export { coreDockViews } from "../dock/coreDockViews";
export { dataDockViews } from "../dock/dataDockViews";
export { workspaceDockViews } from "../dock/workspaceDockViews";
