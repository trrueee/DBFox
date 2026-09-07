import React from '../../../desktop/node_modules/react/index.js';
import { createRoot } from '../../../desktop/node_modules/react-dom/client.js';
import { Tree } from '../../../desktop/src/components/ui/tree.tsx';
import '../../../desktop/src/styles/tokens.css';
import { register, deactivate } from '../../../dlcs/dbfox.game/frontend/index.js';
globalThis.__DBFOX_EXTENSION_HOST__ = { React };
const root = createRoot(document.getElementById('root'));
let dock;
const context = { activeProjectId: 'game-author-browser', workbenchScopeId: 'author-studio', onAsk: (reference) => { window.lastReference = reference; } };
const host = {
  ui: { Tree },
  operations: { async invoke(name, input, { signal } = {}) { const response = await fetch('/operation', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name,input}), signal}); const result=await response.json(); if(!response.ok)throw new Error(result.message); return result; } },
  connectors: { register() {} }, artifactViews: { register() {} },
  dockViews: { register(value) { dock=value; }, open(view) { root.render(dock.render(view, context)); } },
  workbench: { currentScopeId: () => context.workbenchScopeId },
};
register(host);
host.dockViews.open({ projectId: context.activeProjectId, viewKey: 'author-studio' });
window.unmountGame = () => { root.unmount(); deactivate(); };
