import { createExecutor, packageDigestFromUrl } from './executor.js';
import { studioComponents } from './studio.js';
import { artifactComponents, parseLocator } from './artifacts.js';

const clientId = crypto.randomUUID();
let registrationCounter = 0;
let active = null;

export function register(host) {
  deactivate();
  const runtime = window.__DBFOX_EXTENSION_HOST__;
  if (!runtime?.React) throw new Error('Shader Studio requires the public React runtime SDK.');
  const React = runtime.React;
  const h = React.createElement;
  const controller = new AbortController();
  const styles = document.createElement('link');
  styles.rel = 'stylesheet'; styles.href = new URL('./studio.css', import.meta.url).href;
  document.head.append(styles);
  const activation = { signal: controller.signal, controller, styles, drafts: new Map(), executor: null };
  active = activation;
  try {
    const packageDigest = packageDigestFromUrl(import.meta.url);
    activation.executor = createExecutor(host, { clientId, packageDigest, nextCounter: () => ++registrationCounter });
  } catch (error) {
    const status = Object.freeze({ state: 'unavailable', message: error.message });
    activation.executor = { subscribe: () => () => {}, getSnapshot: () => status, reconnect() {}, dispose() {} };
  }
  const components = studioComponents(React, host, activation);
  const { View } = artifactComponents(React, host, activation, components);
  const icon = h('svg', { viewBox: '0 0 24 24', width: 16, height: 16, fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, 'aria-hidden': true }, h('path', { d: 'M8 6 2 12l6 6m8-12 6 6-6 6M14 3l-4 18' }));
  host.connectors.register({ id: 'dbfox.shader', title: 'Shader Studio', icon, render: ({ projectId }) => h(components.Connector, { projectId }), addLabel: 'Open Shader Studio', onAdd: ({ projectId }) => components.open(projectId), listResources: async ({ projectId }) => [{ kind: 'dbfox.shader.studio', id: projectId, name: 'Shader Studio', detail: 'Procedural GLSL documents' }] });
  host.dockViews.register({ viewType: 'dbfox.shader.studio', icon: () => icon, resolveTitle: (view) => view.title || 'Shader Studio', isVisible: (view, context) => view.projectId === context.activeProjectId, render: (view, context) => h(components.Studio, { view, context, key: `${view.viewKey}:${context.workbenchScopeId}` }) });
  for (const [suffix, type, title] of [['document', 'document-revision', 'Shader document'], ['report', 'compile-report', 'Shader compile report'], ['preview', 'preview', 'Shader preview']]) {
    host.artifactViews.register({ id: `dbfox.shader.${suffix}`, title, surfaces: ['inline', 'workspace'], priority: 100, artifactTypes: [{ type: `dbfox.shader.${type}`, schemaVersions: [1] }], parsePayload: parseLocator, render: (artifact, payload, context) => h(View, { artifact, payload, context, key: artifact.id }) });
  }
}

export function deactivate() {
  const old = active;
  active = null;
  if (!old) return;
  old.controller.abort(); old.executor?.dispose(); old.styles.remove(); old.drafts.clear();
}
