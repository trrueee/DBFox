const ReactDOM = window.__DBFOX_EXTENSION_HOST__?.ReactDOM;
if (!ReactDOM) throw new Error("DBFox frontend ReactDOM SDK is unavailable");
export default ReactDOM;
export const { createPortal, flushSync, unstable_batchedUpdates } = ReactDOM;
