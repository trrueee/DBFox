// Actual Phaser regression, separate from normal-user Electron evidence.
async (page) => {
  const errors = [];
  const record = (error) => errors.push(error.message);
  page.on('pageerror', record);
  try {
    const result = await page.evaluate(async () => {
      const { createRuntime, ENGINE } = await import('/dlcs/dbfox.game/frontend/runtime.js');
      const canonical = { engine: ENGINE, tick_hz: 60, initial_scene_id: 'main',
        scenes: [{ id: 'main', width: 320, height: 240, background: '#152333', gravity_x: 0, gravity_y: 0 }],
        entities: [], behaviors: [], rules: [], variables: [], assets: [] };
      const parent = document.createElement('div');
      document.body.append(parent);
      let cancelled = 0, readyDestroyed = 0;
      try {
        for (const headless of [false, true]) {
          for (let index = 0; index < 6; index++) {
            const controller = new AbortController();
            const pending = createRuntime({ document: canonical, parent, headless, ticks: 1, signal: controller.signal });
            controller.abort();
            await pending.then(() => { throw new Error('Cancelled boot resolved'); }, (error) => {
              if (error.name !== 'AbortError') throw error;
              cancelled++;
            });
            // Phaser owns asynchronous boot and next-frame destruction.
            await new Promise((resolve) => setTimeout(resolve, 120));
            if (parent.querySelector('canvas')) throw new Error('Cancelled boot leaked its canvas');
          }
          const runtime = await createRuntime({ document: canonical, parent, headless, ticks: 1 });
          runtime.step(); runtime.destroy(); runtime.destroy();
          if (parent.querySelector('canvas')) throw new Error('Ready runtime leaked its canvas');
          readyDestroyed++;
        }
        return { cancelledBeforeReady: cancelled, destroyedAfterReady: readyDestroyed, canvases: parent.querySelectorAll('canvas').length };
      } finally { parent.remove(); }
    });
    if (errors.length) throw new Error('Phaser lifecycle raised browser errors: ' + errors.join('; '));
    return result;
  } finally { page.off('pageerror', record); }
}
