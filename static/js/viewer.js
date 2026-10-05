/**
 * viewer.js – Three.js 360 panorama viewer (ES module, no global THREE)
 */
import {
  WebGLRenderer, Scene, PerspectiveCamera,
  SphereGeometry, MeshBasicMaterial, Mesh,
  TextureLoader, SRGBColorSpace, BackSide, MathUtils, RepeatWrapping
} from "/static/js/three.module.js";

const THREE = { MathUtils };

// Auto-synced from core/scene_calibration.json - LOCKED
export const SCENE_CALIBRATION = Object.freeze({
  "static_nodes": {
    "16_Entrance_from_out_side": {
      "yaw": 90.3,
      "pitch": 11.1
    },
    "01_main_entrance_floor1": {
      "yaw": 89.0,
      "pitch": -1.1
    },
    "02_lab1": {
      "yaw": 192.5,
      "pitch": 0.0
    },
    "03_lab2": {
      "yaw": 338.0,
      "pitch": 0.0
    },
    "04_lab3": {
      "yaw": 270.0,
      "pitch": 0.0
    },
    "05_corridor_floor1": {
      "yaw": 98.5,
      "pitch": 0.0
    },
    "08_corridor_floor2": {
      "yaw": 67.5,
      "pitch": 0.0
    },
    "09_lab9": {
      "yaw": 270.0,
      "pitch": 0.0
    },
    "17_Mitsubishi_Lab": {
      "yaw": 0.0,
      "pitch": 0.0
    },
    "11_Bosch_lab": {
      "yaw": 0.0,
      "pitch": 0.0
    },
    "12_corridor_floor3": {
      "yaw": 81.5,
      "pitch": -3.4
    },
    "13_lab10": {
      "yaw": 299.5,
      "pitch": 0.0
    },
    "14_corridor_floor3": {
      "yaw": 62.5,
      "pitch": 0.0
    },
    "15_Robotics_Lab": {
      "yaw": 0.0,
      "pitch": 0.0
    }
  },
  "dynamic_landing_nodes": {
    "06_stairs_floor1": {
      "default_yaw": 46.6,
      "default_pitch": -8.0,
      "branches": {
        "to_stairs": {
          "target_id": "07_stairs_floor2",
          "yaw": 170.0,
          "pitch": 10.0
        },
        "to_washroom": {
          "target_id": "wr_boys_gf",
          "yaw": 233.6,
          "pitch": -1.1
        }
      }
    },
    "07_stairs_floor2": {
      "default_yaw": 272.2,
      "default_pitch": 1.0,
      "branches": {
        "to_stairs": {
          "target_id": "10_stairs_floor3",
          "yaw": 7.6,
          "pitch": -2.4
        },
        "to_corridor": {
          "target_id": "08_corridor_floor2",
          "yaw": 89.9,
          "pitch": -8.0
        },
        "to_washroom": {
          "target_id": "wr_girls_1f",
          "yaw": 154.3,
          "pitch": -4.1
        }
      }
    },
    "10_stairs_floor3": {
      "default_yaw": 327.4,
      "default_pitch": -4.3,
      "branches": {
        "to_bosch": {
          "target_id": "11_Bosch_lab",
          "yaw": 212.4,
          "pitch": -0.8
        },
        "to_corridor": {
          "target_id": "12_corridor_floor3",
          "yaw": 91.9,
          "pitch": -4.7
        },
        "to_washroom": {
          "target_id": "wr_boys_2f",
          "yaw": 153.6,
          "pitch": -6.4
        }
      }
    }
  }
});

// Step C: Single Deterministic Staircase Resolver backed by SCENE_CALIBRATION
export function getHeadingForScene(sceneId, destinationQuery = "") {
    const q = (destinationQuery || "").toLowerCase();

    // 1. Dynamic landing nodes (staircases & landings)
    const landing = SCENE_CALIBRATION?.dynamic_landing_nodes?.[sceneId];
    if (landing && landing.branches) {
        const branches = landing.branches;

        // Ground Floor Stairs (06_stairs_floor1)
        if (sceneId === "06_stairs_floor1") {
            if ((q.includes("washroom") || q.includes("toilet") || q.includes("bathroom")) && !q.includes("girls") && !q.includes("1f") && !q.includes("2f")) {
                if (branches.to_washroom) return { yaw: branches.to_washroom.yaw, pitch: branches.to_washroom.pitch };
            }
            if (branches.to_stairs) return { yaw: branches.to_stairs.yaw, pitch: branches.to_stairs.pitch };
            return { yaw: landing.default_yaw ?? 0, pitch: landing.default_pitch ?? 0 };
        }

        // 1st Floor Landing (07_stairs_floor2)
        if (sceneId === "07_stairs_floor2") {
            if ((q.includes("washroom") || q.includes("toilet") || q.includes("bathroom") || q.includes("girls")) && (q.includes("girls") || q.includes("1f") || q.includes("floor1") || q.includes("wr_girls"))) {
                if (branches.to_washroom) return { yaw: branches.to_washroom.yaw, pitch: branches.to_washroom.pitch };
            }
            if (["mitsubishi", "17_", "lab9", "lab_09", "09_", "08_", "lab5", "lab6", "lab7", "lab8", "207", "208", "209", "210", "floor1", "first floor", "1f", "corridor"].some(k => q.includes(k))) {
                if (branches.to_corridor) return { yaw: branches.to_corridor.yaw, pitch: branches.to_corridor.pitch };
            }
            if (branches.to_stairs) return { yaw: branches.to_stairs.yaw, pitch: branches.to_stairs.pitch };
            return { yaw: landing.default_yaw ?? 0, pitch: landing.default_pitch ?? 0 };
        }

        // 2nd Floor Landing (10_stairs_floor3)
        if (sceneId === "10_stairs_floor3") {
            if (q.includes("washroom") || q.includes("toilet") || q.includes("bathroom")) {
                if (branches.to_washroom) return { yaw: branches.to_washroom.yaw, pitch: branches.to_washroom.pitch };
            }
            if (q.includes("bosch") || q.includes("11_")) {
                if (branches.to_bosch) return { yaw: branches.to_bosch.yaw, pitch: branches.to_bosch.pitch };
            }
            if (branches.to_corridor) return { yaw: branches.to_corridor.yaw, pitch: branches.to_corridor.pitch };
            return { yaw: landing.default_yaw ?? 0, pitch: landing.default_pitch ?? 0 };
        }
    }

    // 2. Static scenes from admin SCENE_CALIBRATION
    if (SCENE_CALIBRATION?.static_nodes?.[sceneId]) {
        return {
            yaw: SCENE_CALIBRATION.static_nodes[sceneId].yaw ?? 0.0,
            pitch: SCENE_CALIBRATION.static_nodes[sceneId].pitch ?? 0.0
        };
    }

    // 3. Fallback dynamic landing node default view
    if (landing) {
        return {
            yaw: landing.default_yaw ?? 0.0,
            pitch: landing.default_pitch ?? 0.0
        };
    }

    // 4. Fallback direct mapping
    if (SCENE_CALIBRATION?.[sceneId]) {
        const direct = SCENE_CALIBRATION[sceneId];
        return {
            yaw: direct.yaw ?? direct.default?.yaw ?? 0.0,
            pitch: direct.pitch ?? direct.default?.pitch ?? 0.0
        };
    }

    return { yaw: 0.0, pitch: 0.0 };
}

// Wrapper for backward compatibility
export function getStaircaseBranchYaw(stairNodeId, finalDestinationId, isWashroom = false) {
    const q = isWashroom ? ((finalDestinationId || "") + " washroom") : finalDestinationId;
    return getHeadingForScene(stairNodeId, q);
}

/**
 * Resolves camera heading for a panorama node, checking for contextual tour branches.
 * Strictly enforces locked SCENE_CALIBRATION: all dynamic/automated calculations are disabled.
 */
export function getCalibratedHeading(panoId, nextNodeId = null, targetBranch = null, finalDestinationId = null) {
  // 1. Check destination-aware staircase branch resolution if applicable
  if (finalDestinationId && (panoId === "06_stairs_floor1" || panoId === "07_stairs_floor2" || panoId === "10_stairs_floor3")) {
    const isWashroom = targetBranch === "to_washroom" || (finalDestinationId && (finalDestinationId.toLowerCase().includes("washroom") || finalDestinationId.toLowerCase().includes("toilet")));
    const branchRes = getStaircaseBranchYaw(panoId, finalDestinationId, isWashroom);
    if (branchRes) {
      return { yaw: branchRes.yaw, pitch: branchRes.pitch };
    }
  }

  // 2. Static nodes
  if (SCENE_CALIBRATION.static_nodes && SCENE_CALIBRATION.static_nodes[panoId]) {
    const s = SCENE_CALIBRATION.static_nodes[panoId];
    return { yaw: s.yaw ?? 0, pitch: s.pitch ?? 0 };
  }

  // 3. Dynamic landing nodes
  if (SCENE_CALIBRATION.dynamic_landing_nodes && SCENE_CALIBRATION.dynamic_landing_nodes[panoId]) {
    const landing = SCENE_CALIBRATION.dynamic_landing_nodes[panoId];
    const branches = landing.branches || {};

    if (targetBranch) {
      for (const bKey in branches) {
        if (bKey === targetBranch || branches[bKey].target_id === targetBranch) {
          return { yaw: branches[bKey].yaw, pitch: branches[bKey].pitch };
        }
      }
    }

    if (nextNodeId) {
      for (const bKey in branches) {
        const b = branches[bKey];
        if (b.target_id === nextNodeId || (b.next_nodes && b.next_nodes.includes(nextNodeId))) {
          return { yaw: b.yaw, pitch: b.pitch };
        }
      }
    }

    return { yaw: landing.default_yaw ?? 0, pitch: landing.default_pitch ?? 0 };
  }

  // 4. Fallback direct map lookup
  const direct = SCENE_CALIBRATION[panoId];
  if (direct) {
    if (direct.branches && nextNodeId) {
      for (const bKey in direct.branches) {
        const b = direct.branches[bKey];
        if (b.target_id === nextNodeId || (b.next_nodes && b.next_nodes.includes(nextNodeId))) {
          return { yaw: b.yaw, pitch: b.pitch };
        }
      }
    }
    if (direct.default) {
      return { yaw: direct.default.yaw, pitch: direct.default.pitch };
    }
    return { yaw: direct.yaw ?? 0, pitch: direct.pitch ?? 0 };
  }

  return { yaw: 0, pitch: 0 };
}

// ── State ─────────────────────────────────────────────────────────────────
let renderer, scene, camera;
let matA, matB;
let activeIdx = 0;      // 0 = matA is live
let fading    = false;
let firstLoad = true;

let targetYaw   = 90, currentYaw   = 90;
let targetPitch = 0,  currentPitch = 0;
const drag = { on: false, x: 0, y: 0 };

let showcasing     = false;
let showcaseTimer  = null;
let orbitStart     = 0;
let orbitStartTime = 0;
const SHOWCASE_S   = 15;

const loader = new TextureLoader();
const _headingCallbacks = [];

// ── Heading listener ──────────────────────────────────────────────────────
export function onHeadingChange(cb) {
  if (typeof cb === "function") _headingCallbacks.push(cb);
}

export function getCameraHeading() {
  const normYaw = ((currentYaw % 360) + 360) % 360;
  return {
    yaw: Number(normYaw.toFixed(1)),
    pitch: Number(currentPitch.toFixed(1)),
    rawYaw: Number(currentYaw.toFixed(1)),
    targetYaw: Number(targetYaw.toFixed(1)),
    targetPitch: Number(targetPitch.toFixed(1))
  };
}

// ── Init ──────────────────────────────────────────────────────────────────
export function initViewer(canvas) {
  try {
    renderer = new WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(canvas.clientWidth || innerWidth, canvas.clientHeight || innerHeight);

    scene  = new Scene();
    camera = new PerspectiveCamera(75, (canvas.clientWidth || innerWidth) / (canvas.clientHeight || innerHeight), 0.1, 1100);

    const geo = new SphereGeometry(500, 64, 40);
    matA = new MeshBasicMaterial({ side: BackSide, transparent: true, opacity: 0 });
    matB = new MeshBasicMaterial({ side: BackSide, transparent: true, opacity: 0 });

    scene.add(new Mesh(geo, matA));
    scene.add(new Mesh(geo, matB));

    window.addEventListener("resize", () => {
      const w = canvas.clientWidth || innerWidth;
      const h = canvas.clientHeight || innerHeight;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    });

    _setupInput(canvas);
    _loop();
    console.log("[Viewer] OK");
  } catch(e) {
    console.error("[Viewer] initViewer failed:", e);
  }
}

// ── Camera heading override (Step B: Unbreakable Hard-Lock Heading Setter) ───
let currentPanoId = "16_Entrance_from_out_side";

export function setCameraHeading(yawDeg, pitchDeg = 0.0) {
    const y = Number(yawDeg);
    const p = Number(pitchDeg);

    // 1. Force state variables
    currentYaw = y;
    currentPitch = p;
    targetYaw = y;
    targetPitch = p;

    if (this && typeof this === "object") {
        this.yaw = y;
        this.pitch = p;
        this.targetYaw = y;
        this.targetPitch = p;
    }

    if (viewerInstance && viewerInstance !== this) {
        viewerInstance.yaw = y;
        viewerInstance.pitch = p;
        viewerInstance.targetYaw = y;
        viewerInstance.targetPitch = p;
    }

        // 2. Kill any active camera animation or tween
        stopShowcase();
        if (this && typeof this === "object" && this.activeTween) {
            try { this.activeTween.stop(); } catch(e) {}
            this.activeTween = null;
        }
        if (viewerInstance?.activeTween) {
            try { viewerInstance.activeTween.stop(); } catch(e) {}
            viewerInstance.activeTween = null;
        }

        // 3. Immediately apply to Three.js camera in Radians
        const cam = (this && typeof this === "object" && this.camera) ? this.camera : camera;
        if (cam) {
            cam.rotation.order = 'YXZ';
            cam.rotation.y = THREE.MathUtils.degToRad(y);
            cam.rotation.x = THREE.MathUtils.degToRad(p);
            cam.rotation.z = 0;
        }

        const sceneId = (this && typeof this === "object" && this.currentPanoId) ? this.currentPanoId : (viewerInstance?.currentPanoId || currentPanoId || "scene");
        console.warn(`>>> [CAMERA LOCKED] Scene: ${sceneId} | Applied Yaw: ${y}° | Applied Pitch: ${p}°`);
        _notifyHeading();
}

export function setYaw(yawDeg, pitchDeg = 0.0) {
    setCameraHeading.call(this, yawDeg, pitchDeg);
}

function _notifyHeading() {
  const h = getCameraHeading();
  for (let i = 0; i < _headingCallbacks.length; i++) {
    try { _headingCallbacks[i](h); } catch(err) { console.error(err); }
  }
}

// ── Load panorama & Crossfade ─────────────────────────────────────────────
let currentFadeToken = 0;

export function crossFadeTo(nodeId, yaw = null, pitch = null) {
  const url = (typeof nodeId === "string" && (nodeId.startsWith("/") || nodeId.includes(".")))
    ? nodeId 
    : `/static/panos/${nodeId}.jpg`;
  return loadPano(url, yaw, pitch);
}

export function loadPano(url, yaw = null, pitch = null) {
  // Hard-kill any active showcase immediately
  stopShowcase();

  // Extract panoId from url
  const match = url.match(/(?:panos\/)?([^\/]+)\.jpg/);
  const panoId = match ? match[1] : url;
  currentPanoId = panoId;
  if (viewerInstance) viewerInstance.currentPanoId = panoId;

  let effectiveYaw = yaw;
  let effectivePitch = pitch;

  if (effectiveYaw === null || effectiveYaw === undefined) {
    const dest = viewerInstance?.activeTourDestination || "";
    const h = getHeadingForScene(panoId, dest);
    effectiveYaw = h.yaw;
    effectivePitch = h.pitch;
  }

  const y = Number(effectiveYaw);
  const p = Number(effectivePitch);

  // 1. Force the heading immediately
  setCameraHeading(y, p);

  const myFadeToken = ++currentFadeToken;
  fading = true;

  const live = activeIdx === 0 ? matA : matB;
  const next = activeIdx === 0 ? matB : matA;

  return new Promise((resolve) => {
    loader.load(url,
      (tex) => {
        // If a newer loadPano was called while texture was fetching, cancel this fade
        if (myFadeToken !== currentFadeToken) { resolve(); return; }

        tex.colorSpace = SRGBColorSpace;
        tex.wrapS = RepeatWrapping;
        tex.repeat.x = -1;
        tex.offset.x = 1;

        // 3. Re-force the heading immediately after texture swaps (prevents texture-load resets)
        setCameraHeading(y, p);

        if (firstLoad) {
          live.map = tex;
          live.needsUpdate = true;
          live.opacity = 1;
          firstLoad = false;
          fading    = false;
          resolve();
          return;
        }

        next.map = tex;
        next.needsUpdate = true;

        const t0 = performance.now();
        (function tick() {
          if (myFadeToken !== currentFadeToken) { resolve(); return; }
          const p = Math.min((performance.now() - t0) / 400, 1);
          const ease = p * p * (3 - 2 * p);
          next.opacity = ease;
          live.opacity = 1 - ease;
          if (p < 1) { requestAnimationFrame(tick); return; }
          activeIdx = 1 - activeIdx;
          live.opacity = 0;
          next.opacity = 1;
          fading = false;
          setCameraHeading(y, p);
          resolve();
        })();
      },
      undefined,
      (err) => {
        console.error("[Viewer] load error:", url, err);
        fading = false;
        resolve();
      }
    );
  });
}

// ── Showcase ──────────────────────────────────────────────────────────────
export function startShowcase(cb) {
  showcasing     = true;
  orbitStart     = currentYaw;
  orbitStartTime = performance.now();
  clearTimeout(showcaseTimer);
  showcaseTimer = setTimeout(() => { showcasing = false; cb && cb(); }, SHOWCASE_S * 1000);
}

export function startDestinationShowcase(durationSeconds = 15) {
  return new Promise((resolve) => {
    showcasing = true;
    orbitStart = currentYaw;
    orbitStartTime = performance.now();
    targetPitch = 0;
    currentPitch = 0;
    clearTimeout(showcaseTimer);
    showcaseTimer = setTimeout(() => {
      showcasing = false;
      resolve();
    }, durationSeconds * 1000);
  });
}

export function startShowcaseOrbit() {
  showcasing = true;
  orbitStart = currentYaw;
  orbitStartTime = performance.now();
  targetPitch = 0;
  currentPitch = 0;
  clearTimeout(showcaseTimer);
  showcaseTimer = null;
}

export function getTargetOrientation(nodeId, query = "") {
  return getHeadingForScene(nodeId, query);
}

export function stopShowcase() {
  showcasing = false;
  clearTimeout(showcaseTimer);
  showcaseTimer = null;
}
export function setCamera(y, p)  { setCameraHeading(y, p); }

// ── Input ─────────────────────────────────────────────────────────────────
function _setupInput(el) {
  el.addEventListener("mousedown",  e => { drag.on = true;  drag.x = e.clientX; drag.y = e.clientY; });
  window.addEventListener("mouseup",() => { drag.on = false; });
  window.addEventListener("mousemove", e => {
    if (!drag.on || showcasing) return;
    targetYaw   += (e.clientX - drag.x) * 0.18;
    targetPitch  = Math.max(-85, Math.min(85, targetPitch - (e.clientY - drag.y) * 0.12));
    drag.x = e.clientX; drag.y = e.clientY;
  });
  let lt = null;
  el.addEventListener("touchstart", e => { lt = e.touches[0]; }, { passive: true });
  el.addEventListener("touchmove",  e => {
    if (!lt || showcasing) return;
    targetYaw   += (e.touches[0].clientX - lt.clientX) * 0.18;
    targetPitch  = Math.max(-85, Math.min(85, targetPitch - (e.touches[0].clientY - lt.clientY) * 0.12));
    lt = e.touches[0];
  }, { passive: true });
}

// ── Render loop ───────────────────────────────────────────────────────────
function _loop() {
  requestAnimationFrame(_loop);
  if (showcasing) {
    const secs = (performance.now() - orbitStartTime) / 1000;
    targetYaw   = orbitStart + secs * (360 / SHOWCASE_S);
    targetPitch = 0;
  }
  const prevYaw = currentYaw;
  const prevPitch = currentPitch;

  const diffYaw = targetYaw - currentYaw;
  const diffPitch = targetPitch - currentPitch;

  if (Math.abs(diffYaw) < 0.01) {
    currentYaw = targetYaw;
  } else {
    currentYaw += diffYaw * 0.08;
  }

  if (Math.abs(diffPitch) < 0.01) {
    currentPitch = targetPitch;
  } else {
    currentPitch += diffPitch * 0.08;
  }

  if (camera) {
    camera.rotation.order = 'YXZ';
    camera.rotation.y = MathUtils.degToRad(currentYaw);
    camera.rotation.x = MathUtils.degToRad(currentPitch);
    camera.rotation.z = 0;
  }
  renderer.render(scene, camera);

  if (Math.abs(prevYaw - currentYaw) > 0.01 || Math.abs(prevPitch - currentPitch) > 0.01) {
    _notifyHeading();
  }
}

// Expose global viewer instance for debugging, test commands, and external tour coordination
export const viewerInstance = {
  activeTourDestination: "",
  currentPanoId: "16_Entrance_from_out_side",
  activeTween: null,
  yaw: 90.0,
  pitch: 0.0,
  targetYaw: 90.0,
  targetPitch: 0.0,
  setCameraHeading: function(yawDeg, pitchDeg = 0.0) {
    return setCameraHeading.call(this, yawDeg, pitchDeg);
  },
  setYaw: function(yawDeg, pitchDeg = 0.0) {
    return setCameraHeading.call(this, yawDeg, pitchDeg);
  },
  setCamera: function(yawDeg, pitchDeg = 0.0) {
    return setCameraHeading.call(this, yawDeg, pitchDeg);
  },
  crossFadeTo: function(nodeId, yaw, pitch) {
    return crossFadeTo(nodeId, yaw, pitch);
  },
  loadPano: function(url, yaw, pitch) {
    return loadPano(url, yaw, pitch);
  },
  getYaw: () => getCameraHeading().yaw,
  getPitch: () => getCameraHeading().pitch,
  getCameraHeading,
  getCalibratedHeading,
  getStaircaseBranchYaw,
  startShowcase,
  stopShowcase,
  startShowcaseOrbit,
  startDestinationShowcase,
  getTargetOrientation,
  initViewer,
  SCENE_CALIBRATION,
  get camera() { return camera; },
  get renderer() { return renderer; },
  get scene() { return scene; },
  get currentYaw() { return currentYaw; }
};

if (typeof window !== "undefined") {
  window.viewer = viewerInstance;
  window.KIOSK_VIEWER = viewerInstance;
  window.StreetViewControllerInstance = viewerInstance;
  window.setCameraHeading = (y, p) => setCameraHeading(y, p);
  window.setYaw = (y, p) => setCameraHeading(y, p);
  window.getCameraHeading = getCameraHeading;
  window.getCalibratedHeading = getCalibratedHeading;
  window.getStaircaseBranchYaw = getStaircaseBranchYaw;
  window.getHeadingForScene = getHeadingForScene;
  window.getTargetOrientation = getTargetOrientation;
  window.startShowcaseOrbit = startShowcaseOrbit;
  window.startDestinationShowcase = startDestinationShowcase;
  window.loadPano = loadPano;
  window.crossFadeTo = crossFadeTo;
  window.THREE = window.THREE || { MathUtils };
  console.log("[INIT] KIOSK_VIEWER successfully exposed on window.");
}