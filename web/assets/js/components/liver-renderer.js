import * as THREE from "../../vendor/three/three.module.js";
import { GLTFLoader } from "../../vendor/three/GLTFLoader.js";

/** Locally hosted CC0 anatomical assets; all colors describe synthetic run-relative values. */
export function createLiverRenderer(canvas) {
  const stage = canvas.parentElement;
  const badge = document.querySelector("#renderer-badge");
  const message = document.querySelector("#liver-model-message");
  const fallback = document.querySelector("#liver-static-fallback");
  const showFallback = (errorLabel, details) => {
    canvas.hidden = true;
    if (fallback) fallback.hidden = false;
    badge.textContent = errorLabel;
    message.textContent = details;
  };
  const markers = [...stage.querySelectorAll("[data-zone-marker]")];
  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" });
  } catch (error) {
    showFallback("2D ANATOMY FALLBACK", `Interactive 3D is unavailable. A static liver illustration is shown; model calculations and analysis remain available. (${error.message})`);
    return { ready: Promise.resolve(false), setSignals() {}, setZoneValues() {}, setZone() {}, setViewMode() {}, setZoom() {}, resetCamera() {}, onLiverClick: null };
  }
  let contextAvailable = true;
  canvas.addEventListener("webglcontextlost", (event) => {
    event.preventDefault(); contextAvailable = false;
    badge.textContent = "3D CONTEXT LOST";
    showFallback("2D ANATOMY FALLBACK", "The browser paused WebGL rendering. The static liver illustration and simulation results remain available; reload to retry 3D.");
  });
  canvas.addEventListener("webglcontextrestored", () => {
    contextAvailable = true;
    canvas.hidden = false;
    if (fallback) fallback.hidden = true;
    badge.textContent = "3D · RESTORED";
    resize();
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.6));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.15;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(32, 1, 0.01, 20);
  const cameraTarget = new THREE.Vector3(0, 0.9, 0);
  const bodyCenter = new THREE.Vector3(0, 0.9, 0);
  scene.add(new THREE.HemisphereLight(0xa9ddff, 0x102237, 2.0));
  const key = new THREE.DirectionalLight(0xd1edff, 3.2); key.position.set(-2, 3, 4); scene.add(key);
  const rim = new THREE.DirectionalLight(0x299cff, 2.3); rim.position.set(2, 1, -3); scene.add(rim);
  const root = new THREE.Group(); scene.add(root);
  const bodyGroup = new THREE.Group(), liverPivot = new THREE.Group();
  root.add(bodyGroup, liverPivot);
  const liverRaycast = [];
  const zoneMeshes = [];
  const liverMaterials = [];
  const clock = new THREE.Clock();
  const signalValues = { triglyceride: 0, ros: 0, ecm: 0 };
  const signalTargets = { ...signalValues };
  const zoneValues = Array(5).fill(0.5), zoneTargets = Array(5).fill(0.5);
  const signalColors = {
    triglyceride: new THREE.Color(0xd5a344), ros: new THREE.Color(0xd8755d), ecm: new THREE.Color(0x739eac),
  };
  const tint = new THREE.Color(0x5d4838);
  const zoneColors = [0xffb63d, 0xff8c38, 0xff584b, 0x9a76ff, 0x45d5ef];
  const raycaster = new THREE.Raycaster(), pointer = new THREE.Vector2();
  let zoom = 1, viewMode = "body", selectedZone = -1, drag = false, moved = false, previous = null;
  const loader = new GLTFLoader();
  const ready = Promise.all([
    loader.loadAsync("/assets/models/body.glb"),
    loader.loadAsync("/assets/models/liver.glb"),
  ]).then(([bodyGltf, liverGltf]) => {
    const body = bodyGltf.scene;
    body.traverse((object) => {
      if (!object.isMesh) return;
      object.material = new THREE.MeshPhysicalMaterial({
        color: 0x86c9ee, emissive: 0x103754, emissiveIntensity: 0.7,
        transparent: true, opacity: object.name.toLowerCase().includes("eye") ? 0.25 : 0.17,
        roughness: 0.48, metalness: 0.12, side: THREE.DoubleSide, depthWrite: false,
      });
      object.renderOrder = 1;
    });
    bodyGroup.add(body);
    bodyGroup.traverse((object) => { if (object.isBone) object.visible = true; });
    const bodyBounds = new THREE.Box3().setFromObject(body);
    const bodySize = bodyBounds.getSize(new THREE.Vector3());
    bodyCenter.copy(bodyBounds.getCenter(new THREE.Vector3()));

    const liverScene = liverGltf.scene;
    const liverBounds = new THREE.Box3().setFromObject(liverScene);
    const liverSize = liverBounds.getSize(new THREE.Vector3());
    const liverCenter = liverBounds.getCenter(new THREE.Vector3());
    // Normalize model origin and place it in the anatomical right upper abdomen (viewer-left).
    liverScene.position.sub(liverCenter);
    const liverScale = bodySize.x * 0.205 / Math.max(liverSize.x, 0.001);
    // Keep the reference liver close to organ-scale proportions in the body model.
    const verticalScale = liverScale * 1.18;
    liverScene.scale.set(liverScale, verticalScale, liverScale);
    // The reference body is Y-up and its face is toward +Z. Put the liver within the
    // torso's depth envelope (the old +0.23 body-depth offset placed it in front of the skin).
    liverPivot.position.set(bodyCenter.x - bodySize.x * 0.055, bodyBounds.min.y + bodySize.y * 0.625, bodyBounds.min.z + bodySize.z * 0.29);
    liverPivot.rotation.set(0.08, 0, -0.035);
    liverPivot.add(liverScene);
    liverScene.traverse((object) => {
      if (!object.isMesh) return;
      const sourceMaterials = Array.isArray(object.material) ? object.material : [object.material];
      const materials = sourceMaterials.map((source) => new THREE.MeshPhysicalMaterial({
        color: 0xe1a084,
        map: source.map || null,
        normalMap: source.normalMap || null,
        roughnessMap: source.roughnessMap || null,
        aoMap: source.aoMap || null,
        emissiveMap: source.emissiveMap || null,
        alphaMap: source.alphaMap || null,
        roughness: 0.39,
        metalness: 0,
        clearcoat: 0.24,
        clearcoatRoughness: 0.32,
        side: source.side,
        emissive: 0x120603,
        emissiveIntensity: 0.04,
      }));
      sourceMaterials.forEach((source) => source.dispose());
      object.material = Array.isArray(object.material) ? materials : materials[0];
      liverMaterials.push(...materials);
      object.castShadow = false; object.receiveShadow = false;
      liverRaycast.push(object);
    });
    const min = liverBounds.min, max = liverBounds.max;
    for (let index = 0; index < 5; index += 1) {
      const x = min.x + (max.x - min.x) * (0.13 + index * 0.18);
      const y = min.y + (max.y - min.y) * (0.55 + 0.06 * Math.sin(index * 1.1));
      const nx = (x - liverCenter.x) / Math.max(liverSize.x * 0.52, 0.001);
      const ny = (y - liverCenter.y) / Math.max(liverSize.y * 0.58, 0.001);
      const z = liverCenter.z + liverSize.z * 0.49 * Math.sqrt(Math.max(0.12, 1 - nx * nx - ny * ny));
      const material = new THREE.MeshBasicMaterial({ color: zoneColors[index], transparent: true, opacity: 0.48, depthTest: true });
      const marker = new THREE.Mesh(new THREE.SphereGeometry(liverSize.x * liverScale * 0.052, 20, 16), material);
      marker.position.set((x - liverCenter.x) * liverScale, (y - liverCenter.y) * verticalScale, (z - liverCenter.z + liverSize.z * 0.015) * liverScale);
      marker.userData.zone = index;
      liverPivot.add(marker); zoneMeshes.push(marker);
    }
    camera.position.set(bodyCenter.x, bodyCenter.y, bodyCenter.z + bodySize.y * 2.05);
    badge.textContent = "CC0 ANATOMY · LIVE PROXY OVERLAY";
    canvas.hidden = false;
    if (fallback) fallback.hidden = true;
    message.textContent = "CC0 reference anatomy loaded. Geometry stays fixed; tint and hotspot intensity show smoothed, run-normalized synthetic values, not clinical severity.";
    resize();
    fitCamera();
    return true;
  }).catch((error) => {
    showFallback("2D ANATOMY FALLBACK", `The local 3D anatomy could not load. Static anatomy and the API remain available. (${error.message})`);
    return false;
  });

  function fitCamera() {
    const targetObject = viewMode === "body" ? bodyGroup : liverPivot;
    const bounds = new THREE.Box3().setFromObject(targetObject);
    const size = bounds.getSize(new THREE.Vector3());
    const height = Math.max(size.y, size.x / Math.max(camera.aspect, 0.35)) * 1.15;
    cameraTarget.copy(viewMode === "body" ? bodyCenter : liverPivot.position);
    const distance = height / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) / zoom;
    camera.position.set(cameraTarget.x, cameraTarget.y, cameraTarget.z + distance);
    camera.lookAt(cameraTarget);
  }
  function resize() {
    const { width, height } = canvas.getBoundingClientRect();
    if (!width || !height) return;
    renderer.setSize(width, height, false); camera.aspect = width / height; camera.updateProjectionMatrix();
  }
  function updateMarkerPositions() {
    const rect = stage.getBoundingClientRect();
    zoneMeshes.forEach((object, index) => {
      const marker = markers[index];
      if (!marker) return;
      const point = object.getWorldPosition(new THREE.Vector3()).project(camera);
      const x = (point.x * 0.5 + 0.5) * rect.width;
      const y = (-point.y * 0.5 + 0.5) * rect.height;
      marker.style.left = `${x}px`; marker.style.top = `${y}px`;
      marker.hidden = viewMode === "body" || point.z > 1 || x < 5 || x > rect.width - 5 || y < 5 || y > rect.height - 5;
    });
  }
  function projectedLiverContains(x, y, rect) {
    const bounds = new THREE.Box3().setFromObject(liverPivot);
    if (bounds.isEmpty()) return false;
    const min = new THREE.Vector2(Infinity, Infinity), max = new THREE.Vector2(-Infinity, -Infinity);
    for (const ix of [bounds.min.x, bounds.max.x]) for (const iy of [bounds.min.y, bounds.max.y]) for (const iz of [bounds.min.z, bounds.max.z]) {
      const point = new THREE.Vector3(ix, iy, iz).project(camera);
      if (point.z < -1 || point.z > 1) continue;
      const px = (point.x * 0.5 + 0.5) * rect.width, py = (-point.y * 0.5 + 0.5) * rect.height;
      min.x = Math.min(min.x, px); min.y = Math.min(min.y, py); max.x = Math.max(max.x, px); max.y = Math.max(max.y, py);
    }
    return x >= min.x && x <= max.x && y >= min.y && y <= max.y;
  }
  function animate() {
    requestAnimationFrame(animate);
    const easing = 1 - Math.exp(-Math.min(clock.getDelta(), 0.1) * 5.5);
    for (const key of Object.keys(signalValues)) signalValues[key] = THREE.MathUtils.lerp(signalValues[key], signalTargets[key], easing);
    const signalTotal = signalValues.triglyceride + signalValues.ros + signalValues.ecm;
    const targetTint = new THREE.Color(0x5d4838);
    if (signalTotal > 1e-6) {
      targetTint.setRGB(0, 0, 0);
      targetTint.setRGB(
        signalColors.triglyceride.r * signalValues.triglyceride / signalTotal + signalColors.ros.r * signalValues.ros / signalTotal + signalColors.ecm.r * signalValues.ecm / signalTotal,
        signalColors.triglyceride.g * signalValues.triglyceride / signalTotal + signalColors.ros.g * signalValues.ros / signalTotal + signalColors.ecm.g * signalValues.ecm / signalTotal,
        signalColors.triglyceride.b * signalValues.triglyceride / signalTotal + signalColors.ros.b * signalValues.ros / signalTotal + signalColors.ecm.b * signalValues.ecm / signalTotal,
      );
    }
    tint.lerp(targetTint, easing);
    const intensity = Math.max(signalValues.triglyceride, signalValues.ros, signalValues.ecm);
    liverMaterials.forEach((material) => {
      material.emissive.copy(tint);
      material.emissiveIntensity = THREE.MathUtils.lerp(material.emissiveIntensity, 0.025 + intensity * 0.19, easing);
    });
    zoneMeshes.forEach((marker, index) => {
      zoneValues[index] = THREE.MathUtils.lerp(zoneValues[index], zoneTargets[index], easing);
      const selected = selectedZone === index;
      const opacity = selected ? 0.96 : 0.12 + zoneValues[index] * 0.62;
      const scale = (0.82 + zoneValues[index] * 0.55) * (selected ? 1.18 : 1);
      marker.material.opacity = THREE.MathUtils.lerp(marker.material.opacity, opacity, easing);
      marker.scale.setScalar(THREE.MathUtils.lerp(marker.scale.x, scale, easing));
    });
    if (contextAvailable) {
      try { renderer.render(scene, camera); if (zoneMeshes.length) updateMarkerPositions(); }
      catch (error) { contextAvailable = false; badge.textContent = "3D RENDER ERROR"; message.textContent = `WebGL rendering stopped: ${error.message}`; }
    }
  }
  requestAnimationFrame(animate);
  window.addEventListener("resize", resize);
  const observer = new ResizeObserver(resize); observer.observe(stage);
  canvas.addEventListener("pointerdown", (event) => { drag = true; moved = false; previous = [event.clientX, event.clientY]; canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener("pointermove", (event) => {
    if (!drag || !previous) return;
    const dx = event.clientX - previous[0], dy = event.clientY - previous[1];
    moved ||= Math.abs(dx) + Math.abs(dy) > 3;
    if (viewMode === "body") { root.rotation.y += dx * 0.008; root.rotation.x = THREE.MathUtils.clamp(root.rotation.x + dy * 0.004, -0.3, 0.3); }
    else { liverPivot.rotation.y += dx * 0.008; liverPivot.rotation.x = THREE.MathUtils.clamp(liverPivot.rotation.x + dy * 0.004, -0.35, 0.35); }
    previous = [event.clientX, event.clientY];
  });
  canvas.addEventListener("pointerup", (event) => {
    if (!moved) {
      const bounds = canvas.getBoundingClientRect();
      pointer.set(((event.clientX - bounds.left) / bounds.width) * 2 - 1, -((event.clientY - bounds.top) / bounds.height) * 2 + 1);
      raycaster.setFromCamera(pointer, camera);
      const localX = event.clientX - bounds.left, localY = event.clientY - bounds.top;
      if (raycaster.intersectObjects(liverRaycast, true).length || projectedLiverContains(localX, localY, bounds)) api.onLiverClick?.();
    }
    drag = false; previous = null;
  });
  canvas.addEventListener("pointercancel", () => { drag = false; previous = null; });
  canvas.addEventListener("wheel", (event) => { event.preventDefault(); api.setZoom(zoom * (event.deltaY > 0 ? 0.92 : 1.08)); }, { passive: false });

  const api = {
    ready,
    onLiverClick: null,
    setViewMode(mode) {
      viewMode = mode;
      bodyGroup.visible = mode === "body";
      liverPivot.scale.setScalar(mode === "body" ? 1 : 3.5);
      zoneMeshes.forEach((marker) => { marker.visible = mode === "zones"; });
      fitCamera();
    },
    setZoom(value) { zoom = THREE.MathUtils.clamp(Number(value) || 1, 0.8, 2.8); fitCamera(); },
    resetCamera() {
      root.rotation.set(0, 0, 0);
      liverPivot.rotation.set(0, 0, 0);
      zoom = 1;
      fitCamera();
    },
    setZone(index) {
      selectedZone = index;
    },
    setZoneValues(values) {
      zoneTargets.forEach((_, index) => { zoneTargets[index] = THREE.MathUtils.clamp(Number(values[index]) || 0.08, 0.08, 1); });
    },
    setSignals(signals) {
      for (const key of Object.keys(signalTargets)) signalTargets[key] = THREE.MathUtils.clamp(Number(signals[key]) || 0, 0, 1);
    },
  };
  return api;
}
