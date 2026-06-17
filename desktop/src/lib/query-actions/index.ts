/**
 * DBFox SQL Action Engine (DSL & Pipeline Runtime)
 */

import { actionRegistry } from "./registry";
import { LimitProcessor } from "./processors/limit";
import { TimeoutProcessor } from "./processors/timeout";
import { ExplainProcessor } from "./processors/explain";
import { ExportProcessor } from "./processors/export";
import { ChartProcessor } from "./processors/chart";
import type { ActionProcessor } from "./types";

// Register all standard processors into the singleton registry on startup
actionRegistry
  .register(LimitProcessor)
  .register(TimeoutProcessor)
  .register(ExplainProcessor)
  .register(ExportProcessor)
  .register(ChartProcessor);

// Public exports
export * from "./types";
export * from "./registry";
export { LimitProcessor } from "./processors/limit";
export { TimeoutProcessor } from "./processors/timeout";
export { ExplainProcessor } from "./processors/explain";
export { ExportProcessor } from "./processors/export";
export { ChartProcessor } from "./processors/chart";

export function registerActionProcessor(processor: ActionProcessor): void {
  actionRegistry.register(processor);
}
