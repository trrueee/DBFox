import * as THREE from "./vendor/three.js";

// The entire Three graph is disposable derived view state, never durable truth.
export function createViewport(container, callbacks) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(globalThis.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const canvas = renderer.domElement;
  canvas.setAttribute("aria-label", "三维场景视口；拖动旋转，滚轮缩放，F 聚焦，W/E/R 变换");
  canvas.tabIndex = 0;
  container.append(canvas);
  const scene = new THREE.Scene();
  const content = new THREE.Group();
  scene.add(content);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 1e8);
  camera.position.set(6, 5, 8);
  const orbit = new THREE.OrbitControls(camera, canvas);
  orbit.target.set(0, 0.5, 0);
  orbit.update();
  const transform = new THREE.TransformControls(camera, canvas);
  transform.setSpace("local");
  scene.add(transform.getHelper());
  const grid = new THREE.GridHelper(20, 20, 0x526070, 0x303944);
  scene.add(grid);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x596478, 2));
  const fill = new THREE.DirectionalLight(0xffffff, 2);
  fill.position.set(5, 10, 8);
  scene.add(fill);
  const selectionBox = new THREE.Box3Helper(new THREE.Box3(), 0x70b8ff);
  selectionBox.visible = false;
  scene.add(selectionBox);
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let nodes = new Map();
  let resources = new Set();
  let snapshot = null;
  let selectedId = null;
  let frame = 0;
  let disposed = false;
  let enabled = true;
  let dragging = null;
  let pointerDown = null;
  let skipClick = false;
  let helpers = [];
  let viewCameraId = null;
  const geometries = new Map();
  const materials = new Map();
  const markerGeometry = remember(new THREE.SphereGeometry(0.09, 8, 6));
  const markerMaterials = new Map([
    ["light", remember(new THREE.MeshBasicMaterial({ color: 0xffdc7e }))],
    ["camera", remember(new THREE.MeshBasicMaterial({ color: 0x88b8ff }))],
    ["group", remember(new THREE.MeshBasicMaterial({ color: 0xa4adbd }))],
  ]);
  const defaultMaterial = remember(new THREE.MeshStandardMaterial({ color: new THREE.Color().setRGB(0.65, 0.65, 0.65), roughness: 0.6 }));

  function draw() {
    if (disposed || frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      if (disposed) return;
      scene.updateMatrixWorld(true);
      for (const helper of helpers) {
        let shown = true;
        for (let node = helper.camera; node; node = node.parent) if (!node.visible) shown = false;
        helper.visible = shown && helper.camera.userData.sceneObjectId !== viewCameraId;
        if (shown) helper.update?.();
      }
      const node = nodes.get(selectedId);
      if (node && node.visible) {
        selectionBox.box.setFromObject(node);
        selectionBox.visible = !selectionBox.box.isEmpty();
      } else selectionBox.visible = false;
      renderer.render(scene, viewCameraId && nodes.get(viewCameraId)?.isCamera ? nodes.get(viewCameraId) : camera);
    });
  }
  function resize() {
    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    for (const node of nodes.values()) {
      if (node.isCamera) { node.aspect = camera.aspect; node.updateProjectionMatrix(); }
    }
    draw();
  }
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  function remember(resource) { resources.add(resource); return resource; }
  function clearContent() {
    transform.detach();
    content.clear();
    for (const helper of helpers) { scene.remove(helper); helper.dispose(); }
    helpers = [];
    for (const resource of resources) resource.dispose();
    resources = new Set();
    nodes = new Map();
    geometries.clear();
    materials.clear();
  }
  function update(next) {
    snapshot = next;
    scene.background = new THREE.Color().setRGB(...next.settings.background);
    for (const item of next.geometries) if (!geometries.has(item.id)) geometries.set(item.id, remember(THREE.createPrimitive(item.primitive)));
    const materialIds = new Set(next.materials.map((item) => item.id));
    for (const [id, material] of materials) if (!materialIds.has(id)) {
      material.dispose(); resources.delete(material); materials.delete(id);
    }
    for (const item of next.materials) {
      let material = materials.get(item.id);
      if (!material) { material = remember(new THREE.MeshStandardMaterial()); materials.set(item.id, material); }
      const transparent = item.base_color[3] < 1;
      const side = item.double_sided ? THREE.DoubleSide : THREE.FrontSide;
      if (transparent !== material.transparent || side !== material.side) material.needsUpdate = true;
      material.color.setRGB(...item.base_color.slice(0, 3));
      material.opacity = item.base_color[3];
      material.transparent = transparent;
      material.metalness = item.metallic;
      material.roughness = item.roughness;
      material.side = side;
    }
    const byId = new Map(next.objects.map((item) => [item.id, item]));
    for (const [id, node] of nodes) {
      const item = byId.get(id);
      if (!item || node.userData.kind !== item.kind || (item.kind === "light" && node.userData.lightType !== item.light_type)) {
        if (transform.object === node) transform.detach();
        node.removeFromParent();
        nodes.delete(id);
        const helper = helpers.find((entry) => entry.camera === node);
        if (helper) { scene.remove(helper); helper.dispose(); helpers = helpers.filter((entry) => entry !== helper); }
      }
    }
    for (const item of next.objects) {
      let node = nodes.get(item.id);
      if (!node) {
        if (item.kind === "mesh") node = new THREE.Mesh(geometries.get(item.geometry_id), defaultMaterial);
        else if (item.kind === "camera") node = new THREE.PerspectiveCamera();
        else if (item.kind === "light") {
          if (item.light_type === "directional") node = new THREE.DirectionalLight();
          else if (item.light_type === "spot") node = new THREE.SpotLight();
          else node = new THREE.PointLight();
          if (node.target) { node.target.position.set(0, 0, -1); node.add(node.target); }
        } else node = new THREE.Group();
        node.userData.kind = item.kind;
        node.userData.lightType = item.light_type;
        node.userData.sceneObjectId = item.id;
        nodes.set(item.id, node);
        if (item.kind !== "mesh") {
          // Markers share one geometry and three materials across the whole scene.
          const marker = new THREE.Mesh(markerGeometry, markerMaterials.get(item.kind));
          marker.userData.sceneObjectId = item.id;
          node.add(marker);
        }
        if (item.kind === "camera") {
          const helper = new THREE.CameraHelper(node);
          scene.add(helper);
          helpers.push(helper);
        }
      }
      if (item.kind === "mesh") { node.geometry = geometries.get(item.geometry_id); node.material = materials.get(item.material_id) || defaultMaterial; }
      else if (item.kind === "camera") {
        node.fov = item.yfov * 180 / Math.PI; node.aspect = camera.aspect; node.near = item.znear; node.far = item.zfar; node.updateProjectionMatrix();
      } else if (item.kind === "light") {
        node.color.setRGB(...item.color); node.intensity = item.intensity;
        if (item.light_type !== "directional") { node.distance = item.range || 0; node.decay = 2; }
        if (item.light_type === "spot") { node.angle = item.outer_cone_angle; node.penumbra = 1 - item.inner_cone_angle / item.outer_cone_angle; }
      }
      node.name = item.name;
      node.position.fromArray(item.position);
      node.rotation.set(...item.rotation, "XYZ");
      node.scale.fromArray(item.scale);
      node.visible = item.visible;
    }
    for (const item of next.objects) {
      const parent = nodes.get(item.parent_id) || content;
      const node = nodes.get(item.id);
      if (node.parent !== parent) parent.add(node);
    }
    scene.updateMatrixWorld(true);
    if (!nodes.has(viewCameraId)) viewCameraId = null;
    select(selectedId);
    resize();
  }
  function select(id) {
    selectedId = id;
    const node = nodes.get(id);
    if (node && node.visible && enabled && !viewCameraId) transform.attach(node);
    else transform.detach();
    draw();
  }
  function setEnabled(value) {
    enabled = value;
    transform.enabled = value && !viewCameraId;
    select(selectedId);
  }
  function focus(id = selectedId) {
    viewCameraId = null;
    orbit.enabled = true;
    const box = new THREE.Box3().setFromObject(nodes.get(id) || content);
    const center = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3());
    const size = box.isEmpty() ? 4 : Math.max(box.getSize(new THREE.Vector3()).length(), 1);
    orbit.target.copy(center);
    camera.position.copy(center).add(new THREE.Vector3(1, 0.75, 1.3).normalize().multiplyScalar(size * 1.8));
    camera.near = Math.max(0.001, size / 10000);
    camera.far = Math.max(1000, size * 100);
    camera.updateProjectionMatrix();
    orbit.update();
    select(selectedId);
    draw();
  }
  function setCamera(id) {
    viewCameraId = nodes.get(id)?.isCamera ? id : null;
    orbit.enabled = !viewCameraId;
    transform.enabled = enabled && !viewCameraId;
    select(selectedId);
    draw();
  }
  function onDragChanged(event) {
    orbit.enabled = !event.value && !viewCameraId;
    if (event.value) {
      skipClick = true;
      dragging = { id: selectedId, version: snapshot.scene.version };
      callbacks.onDragStart?.();
    } else if (dragging) {
      const prior = dragging;
      dragging = null;
      const node = nodes.get(prior.id);
      if (node) {
        const values = { object_id: prior.id, position: node.position.toArray(), rotation: [node.rotation.x, node.rotation.y, node.rotation.z], scale: node.scale.toArray() };
        // One commit per completed gesture. The caller refreshes canonical state on failure.
        callbacks.onDragEnd(values, prior.version);
      }
    }
    draw();
  }
  function cancelDrag() {
    if (!dragging) return;
    dragging = null;
    transform.reset();
    transform.dragging = false;
    orbit.enabled = true;
    callbacks.onDragCancel?.();
    draw();
  }
  function down(event) {
    if (event.button !== 0) return;
    canvas.focus();
    pointerDown = { x: event.clientX, y: event.clientY };
    if (!transform.dragging) skipClick = false;
  }
  function up(event) {
    if (!pointerDown || event.button !== 0) return;
    const delta = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
    pointerDown = null;
    if (skipClick || delta > 4 || !enabled) return;
    const rect = canvas.getBoundingClientRect();
    pointer.set((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1);
    raycaster.setFromCamera(pointer, viewCameraId ? nodes.get(viewCameraId) : camera);
    const hits = raycaster.intersectObject(content, true);
    const hit = hits.find(({ object }) => {
      for (let node = object; node; node = node.parent) if (!node.visible) return false;
      return !!object.userData.sceneObjectId;
    });
    callbacks.onSelect(hit?.object.userData.sceneObjectId || null);
  }
  function key(event) {
    if (event.key === "Escape") { cancelDrag(); event.preventDefault(); }
    else if (event.key.toLowerCase() === "f") { focus(); event.preventDefault(); }
    else if (!dragging) callbacks.onKey?.(event);
  }
  function lost() { cancelDrag(); }
  function contextLost(event) { event.preventDefault(); callbacks.onError("WebGL 上下文已丢失，请重新打开工作台。"); }
  orbit.addEventListener("change", draw);
  transform.addEventListener("change", draw);
  transform.addEventListener("dragging-changed", onDragChanged);
  canvas.addEventListener("pointerdown", down);
  canvas.addEventListener("pointerup", up);
  canvas.addEventListener("pointercancel", lost);
  canvas.addEventListener("keydown", key);
  canvas.addEventListener("webglcontextlost", contextLost);
  globalThis.addEventListener("blur", lost);
  resize();
  return {
    update, select, setEnabled, focus, setCamera,
    setMode(mode, space) { transform.setMode(mode); transform.setSpace(space); draw(); },
    dispose() {
      if (disposed) return;
      disposed = true;
      dragging = null;
      if (frame) cancelAnimationFrame(frame);
      observer.disconnect();
      canvas.removeEventListener("pointerdown", down);
      canvas.removeEventListener("pointerup", up);
      canvas.removeEventListener("pointercancel", lost);
      canvas.removeEventListener("keydown", key);
      canvas.removeEventListener("webglcontextlost", contextLost);
      globalThis.removeEventListener("blur", lost);
      orbit.removeEventListener("change", draw);
      transform.removeEventListener("change", draw);
      transform.removeEventListener("dragging-changed", onDragChanged);
      orbit.dispose();
      transform.dispose();
      clearContent();
      grid.geometry.dispose();
      grid.material.dispose();
      selectionBox.geometry.dispose();
      selectionBox.material.dispose();
      renderer.renderLists.dispose();
      renderer.dispose();
      renderer.forceContextLoss();
      canvas.remove();
    },
  };
}
