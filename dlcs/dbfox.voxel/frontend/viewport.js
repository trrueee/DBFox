import * as THREE from "./vendor/three.js";
import { surfaceInstances } from "./world-data.js";

/** Owns its GPU resources. This view can always be reconstructed from chunks. */
export function createVoxelViewport(element, report, onPick) {
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch {
    report("三维预览暂不可用。仍可使用切片画布和选区工具编辑。", "error");
    return null;
  }
  let disposed = false;
  let buildAbort = null;
  let frame = 0;
  let mesh = null;
  let instancePositions = null;
  let pointer = null;
  let framed = false;
  let worldSize = [64, 64, 64];
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 4000);
  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = false;
  controls.minDistance = 2;
  controls.maxDistance = 1500;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.tabIndex = 0;
  renderer.domElement.setAttribute("aria-label", "体素三维视口：点击选择方块，拖动旋转、滚轮缩放、右键平移，方向键平移");
  controls.listenToKeyEvents(renderer.domElement);
  element.appendChild(renderer.domElement);
  const cube = new THREE.BoxGeometry(1, 1, 1);
  const material = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0.05 });
  const grid = new THREE.GridHelper(256, 32, 0x637187, 0x465062);
  grid.material.transparent = true;
  grid.material.opacity = 0.3;
  scene.add(grid);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x697389, 2.6));
  const keyLight = new THREE.DirectionalLight(0xffffff, 2.5);
  keyLight.position.set(70, 150, 110);
  scene.add(keyLight);
  const worldBox = new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(), new THREE.Vector3(64, 64, 64)), 0x78879d);
  worldBox.material.transparent = true;
  worldBox.material.opacity = 0.4;
  scene.add(worldBox);
  const selectionBox = new THREE.Box3Helper(new THREE.Box3(new THREE.Vector3(), new THREE.Vector3(1, 1, 1)), 0x22d3ee);
  selectionBox.material.depthTest = false;
  selectionBox.renderOrder = 2;
  scene.add(selectionBox);

  function draw() {
    if (disposed || frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (!disposed) renderer.render(scene, camera);
    });
  }

  function fit(bounds = null) {
    const min = bounds?.min || [0, 0, 0];
    const max = bounds?.max || worldSize;
    const center = min.map((value, i) => (value + max[i]) / 2);
    const distance = Math.max(...max.map((value, i) => value - min[i]), 3) * 1.55;
    camera.position.set(center[0] + distance, center[1] + distance * 0.8, center[2] + distance);
    controls.target.set(...center);
    controls.update();
    draw();
  }

  function resize() {
    const width = Math.max(element.clientWidth, 1);
    const height = Math.max(element.clientHeight, 1);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    draw();
  }

  function lost(event) {
    event.preventDefault();
    report("三维图形上下文已断开，切片编辑仍可使用。", "error");
  }
  function restored() {
    report("三维预览已恢复。", "ready");
    draw();
  }
  function pointerDown(event) {
    if (event.button === 0) pointer = { id: event.pointerId, x: event.clientX, y: event.clientY, mesh, moved: false };
    else pointer = null;
  }
  function pointerMove(event) {
    if (pointer && Math.hypot(event.clientX - pointer.x, event.clientY - pointer.y) > 4) pointer.moved = true;
  }
  function pointerUp(event) {
    const started = pointer;
    pointer = null;
    if (!started || started.id !== event.pointerId || started.moved || started.mesh !== mesh
      || !mesh || !instancePositions || !onPick || disposed) return;
    const rect = renderer.domElement.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const raycaster = new THREE.Raycaster();
    camera.updateMatrixWorld(); mesh.updateMatrixWorld();
    raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1,
      1 - (event.clientY - rect.top) / rect.height * 2), camera);
    const hit = raycaster.intersectObject(mesh, false)[0];
    if (hit?.instanceId != null) onPick(Array.from(instancePositions.subarray(hit.instanceId * 3, hit.instanceId * 3 + 3)));
  }
  function pointerCancel() { pointer = null; }
  controls.addEventListener("change", draw);
  renderer.domElement.addEventListener("pointerdown", pointerDown);
  renderer.domElement.addEventListener("pointermove", pointerMove);
  renderer.domElement.addEventListener("pointerup", pointerUp);
  renderer.domElement.addEventListener("pointercancel", pointerCancel);
  renderer.domElement.addEventListener("webglcontextlost", lost);
  renderer.domElement.addEventListener("webglcontextrestored", restored);
  const observer = new ResizeObserver(resize);
  observer.observe(element);
  resize();
  fit();

  return {
    fit,
    setSelection(bounds) {
      selectionBox.visible = Boolean(bounds);
      if (bounds) {
        selectionBox.box.min.set(...bounds.min);
        selectionBox.box.max.set(...bounds.max);
      }
      draw();
    },
    async update(composite, palette, crop = null) {
      buildAbort?.abort();
      buildAbort = new AbortController();
      const signal = buildAbort.signal;
      report("正在构建三维预览…", "loading");
      try {
        const instances = await surfaceInstances(composite, crop, signal);
        if (signal.aborted || disposed) return;
        const next = new THREE.InstancedMesh(cube, material, Math.max(instances.count, 1));
        const matrix = new THREE.Matrix4();
        const colors = new Map(palette.map((entry) => [entry.index, new THREE.Color(entry.color)]));
        for (let index = 0; index < instances.count; index += 1) {
          const offset = index * 3;
          matrix.makeTranslation(instances.positions[offset] + 0.5, instances.positions[offset + 1] + 0.5, instances.positions[offset + 2] + 0.5);
          next.setMatrixAt(index, matrix);
          next.setColorAt(index, colors.get(instances.colors[index]));
          if (index % 2048 === 2047) {
            await new Promise((resolve) => setTimeout(resolve, 0));
            if (signal.aborted || disposed) { next.dispose(); return; }
          }
        }
        next.count = instances.count;
        next.instanceMatrix.needsUpdate = true;
        if (next.instanceColor) next.instanceColor.needsUpdate = true;
        next.computeBoundingBox();
        next.computeBoundingSphere();
        if (mesh) { scene.remove(mesh); mesh.dispose(); }
        mesh = next;
        instancePositions = instances.positions;
        scene.add(mesh);
        worldSize = composite.size;
        worldBox.box.max.set(...worldSize);
        grid.scale.set(worldSize[0] / 256, 1, worldSize[2] / 256);
        grid.position.set(worldSize[0] / 2, -0.015, worldSize[2] / 2);
        if (!framed) { framed = true; fit(); }
        report(instances.truncated
          ? "预览已截断：达到 60,000 个表面方块上限。启用“仅预览选区”检查局部，或使用完整切片编辑。"
          : `${instances.count.toLocaleString()} 个表面方块`, instances.truncated ? "limited" : "ready");
        draw();
      } catch (error) {
        if (error.name !== "AbortError" && !disposed) report("三维预览未完成，请刷新或缩小选区。", "error");
      }
    },
    dispose() {
      if (disposed) return;
      disposed = true;
      buildAbort?.abort();
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.removeEventListener("change", draw);
      controls.dispose();
      renderer.domElement.removeEventListener("pointerdown", pointerDown);
      renderer.domElement.removeEventListener("pointermove", pointerMove);
      renderer.domElement.removeEventListener("pointerup", pointerUp);
      renderer.domElement.removeEventListener("pointercancel", pointerCancel);
      pointer = null; instancePositions = null;
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      renderer.domElement.removeEventListener("webglcontextrestored", restored);
      mesh?.dispose();
      cube.dispose();
      material.dispose();
      grid.geometry.dispose();
      grid.material.dispose();
      worldBox.geometry.dispose();
      worldBox.material.dispose();
      selectionBox.geometry.dispose();
      selectionBox.material.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      renderer.domElement.remove();
    },
  };
}
