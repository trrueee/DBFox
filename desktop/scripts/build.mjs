import { createBuilder } from "vite";

const builder = await createBuilder(
  {
    // Use relative paths so assets load correctly under Tauri's custom
    // protocol.  Without this, absolute /assets/… paths cause a white
    // screen in production builds.
    base: "./",
  },
  true,
);
await builder.buildApp();
