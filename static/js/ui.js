/**
 * ui.js – Pill chips, floor-elevator transition HUD, step label, showcase capsule,
 *          breadcrumb bubble, and staircase-anchored floor transition.
 * Orchestrates the full query → route → traverse → showcase → reset flow.
 */
import {
  loadPano,
  crossFadeTo,
  startShowcase,
  stopShowcase,
  startShowcaseOrbit,
  startDestinationShowcase,
  getTargetOrientation,
  setCamera,
  setCameraHeading,
  getHeadingForScene,
  SCENE_CALIBRATION,
  getCalibratedHeading,
  getStaircaseBranchYaw,
  viewerInstance
} from "./viewer.js?v=5.0";
import { initSpeech, toggleMic, playAudio } from "./speech.js?v=2.0";

const START_NODE = "16_Entrance_from_out_side";
const getStartCalib = () => getCalibratedHeading(START_NODE);
const STEP_DELAY = 2200;   // ms between auto-step traversal
const FLOOR_HOLD = 800;    // ms floor-transition interstitial

/* ── Task B: staircase nodes – only show floor HUD from inside these ─────── */
const STAIRCASE_NODE_IDS = new Set([
  "06_stairs_floor1",
  "07_stairs_floor2",
  "10_stairs_floor3",
]);

/* ── DOM refs ─────────────────────────────────────────────────────────────── */
const $input = document.getElementById("search-input");
const $sendBtn = document.getElementById("send-btn");
const $micBtn = document.getElementById("mic-btn");
const $stepLabel = document.getElementById("step-label");
const $floorHud = document.getElementById("floor-hud");
const $floorDir = document.getElementById("floor-hud-direction");
const $floorLabel = document.getElementById("floor-hud-label");
const $showcaseHud = document.getElementById("showcase-hud");
const $showcaseTxt = document.getElementById("showcase-label");
const $showcaseCnt = document.getElementById("showcase-count");
const $breadcrumb = document.getElementById("route-breadcrumb-bubble");
const $breadcrumbList = document.getElementById("breadcrumb-steps-list");

/* ── State ────────────────────────────────────────────────────────────────── */
let _traversing = false;
let _stepTimers = [];

/* ── Quick Pills ──────────────────────────────────────────────────────────── */
const PILLS = [
  { label: "Lalit Sir's Cabin", query: "lalit sir" },
  { label: "Bosch Lab", query: "bosch lab" },
  { label: "Robotics Lab", query: "robotics lab" },
  { label: "Room 307", query: "307" },
  { label: "Washroom (GF)", query: "washroom" },
  { label: "Girls Washroom (1F)", query: "girls washroom" },
  { label: "Lab 1", query: "lab 1" },
];
const $pillsRow = document.getElementById("pills-row");
PILLS.forEach(({ label, query }) => {
  const btn = document.createElement("button");
  btn.className = "pill";
  btn.textContent = label;
  btn.addEventListener("click", () => submitQuery(query));
  $pillsRow.appendChild(btn);
});

/* ── Input handling ──────────────────────────────────────────────────────── */
$sendBtn.addEventListener("click", () => {
  const q = $input.value.trim();
  if (q) submitQuery(q);
});
$input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { const q = $input.value.trim(); if (q) submitQuery(q); }
});
$micBtn.addEventListener("click", toggleMic);

initSpeech((transcript) => {
  $input.value = transcript;
  submitQuery(transcript);
});

/* ── Core query flow ─────────────────────────────────────────────────────── */
async function submitQuery(query) {
  stopShowcase();
  if (_traversing) cancelTraversal();
  $input.value = "";
  setStepLabel("Searching…", true);

  const viewer = window.viewer || viewerInstance;
  if (viewer) {
    viewer.activeTourDestination = query;
  }

  let data;
  try {
    const res = await fetch("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, start: START_NODE }),
    });
    data = await res.json();
  } catch (err) {
    setStepLabel("Network error – try again", true);
    setTimeout(() => setStepLabel("", false), 3000);
    return;
  }

  const steps = data.route?.steps || [];
  if (!steps.length) {
    setStepLabel("No route found.", true);
    setTimeout(() => setStepLabel("", false), 3000);
    return;
  }

  const destEntity = data.destination_entity || { target_branch: data.target_branch, pano_id: data.target_pano_id };
  const destTitle = data.display_title || query;
  if (viewer) {
    viewer.activeTourDestination = destTitle || query;
  }

  // Use synchronized multi-phase tour if available, otherwise fallback
  if (data.tour_segments && data.tour_segments.length > 0) {
    playSynchronizedTour(data.tour_segments, data.route, destTitle, destEntity);
  } else {
    if (data.audio_base64) playAudio(data.audio_base64);
    traverseRoute(steps, destTitle, destEntity);
  }
}

/* ── Synchronous Audio-Visual Guided Tour (Slow & Accessible) ─────────────── */
let _activeTourCancelToken = 0;

export async function playSynchronizedTour(tourSegments, routeData = null, destinationTitle = "", destinationEntity = null) {
  stopShowcase();
  cancelTraversal();

  _traversing = true;
  const tourToken = ++_activeTourCancelToken;

  const viewer = window.viewer || viewerInstance;
  window.activeTourQuery = destinationTitle || destinationEntity?.name || "";
  if (viewer) {
    viewer.activeTourDestination = window.activeTourQuery;
  }

  // 1. Build and display breadcrumb list for entire path
  const steps = routeData?.steps || [];
  if (steps.length > 0) {
    buildBreadcrumb(steps);
    showBreadcrumb();
    updateBreadcrumbStep(steps[0].pano_id);
  }

  const getAudioPlayer = () => {
    let p = document.getElementById("kiosk-audio-player");
    if (!p) {
      p = document.createElement("audio");
      p.id = "kiosk-audio-player";
      p.preload = "auto";
      document.body.appendChild(p);
    }
    return p;
  };

  const playAudioAndWait = (base64Audio) => {
    return new Promise((resolve) => {
      if (!base64Audio || _activeTourCancelToken !== tourToken) {
        resolve();
        return;
      }
      const player = getAudioPlayer();
      const src = base64Audio.startsWith("data:")
        ? base64Audio
        : `data:audio/mp3;base64,${base64Audio}`;

      player.src = src;

      let resolved = false;
      const done = () => {
        if (!resolved) {
          resolved = true;
          player.onended = null;
          player.onerror = null;
          resolve();
        }
      };

      player.onended = done;
      player.onerror = (err) => {
        console.warn("[Tour Audio Error]", err);
        done(); // fallback so tour never freezes
      };

      const playPromise = player.play();
      if (playPromise !== undefined) {
        playPromise.catch((e) => {
          console.warn("[Tour Audio Play Catch]", e);
          done();
        });
      }
    });
  };

  const wait = (ms) => new Promise((resolve) => {
    const t = setTimeout(resolve, ms);
    _stepTimers.push(t);
  });

  try {
    for (const segment of tourSegments) {
      if (_activeTourCancelToken !== tourToken) break;

      console.log(`[Tour Phase] Starting: ${segment.phase} - "${segment.text}"`);

      // ── Special handling for Phase 4: Arrival & Showcase ──
      if (segment.phase === "showcase" || segment.id === "arrival") {
        const destNode = segment.nodes?.[0] || segment.node_sequence?.[0] || (steps.length ? steps[steps.length - 1].pano_id : "");

        // 1. Immediately crossfade into the destination room
        if (destNode) {
          const heading = getTargetOrientation(destNode, window.activeTourQuery);
          if (viewer && typeof viewer.crossFadeTo === "function") {
            await viewer.crossFadeTo(destNode, heading.yaw, heading.pitch);
          } else {
            await crossFadeTo(destNode, heading.yaw, heading.pitch);
          }
          updateBreadcrumbStep(destNode);
        }

        if (_activeTourCancelToken !== tourToken) break;

        // 2. Set subtitle text explaining arrival (do NOT show on-screen counter)
        setStepLabel(segment.text, true);
        hideShowcaseHUD();

        // 3. Start voice statement & rotate 360 degree image SIMULTANEOUSLY!
        console.log("[Tour Phase 4] Speaking destination context and rotating 360° simultaneously (no on-screen counter)...");
        const audioPromise = playAudioAndWait(segment.audio_base64);

        if (viewer && typeof viewer.startShowcaseOrbit === "function") {
          viewer.startShowcaseOrbit();
        } else {
          startShowcaseOrbit();
        }

        // 4. Rotate till voice is completing its statement
        await audioPromise;
        if (_activeTourCancelToken !== tourToken) break;

        // 5. Internally count for 5 seconds while 360 rotation continues
        console.log("[Tour Phase 4] Voice statement completed. Rotating for 5 seconds internal count...");
        await wait(5000);
        if (_activeTourCancelToken !== tourToken) break;

        // 6. Stop rotation
        if (viewer && typeof viewer.stopShowcase === "function") {
          viewer.stopShowcase();
        } else {
          stopShowcase();
        }

        // Done with tour phases
        break;
      }

      // ── Phases 1, 2, 3: Sequential guidance ──
      setStepLabel(segment.text, true);

      // 1. Start speaking guidance for this stage
      const audioPromise = playAudioAndWait(segment.audio_base64);

      // Speech leads action: gentle head-start pause before physical camera movement
      await wait(400);
      if (_activeTourCancelToken !== tourToken) break;

      // 2. Step through the physical nodes associated with this phase
      const phaseNodes = segment.nodes || segment.node_sequence || [];
      for (const nodeId of phaseNodes) {
        if (_activeTourCancelToken !== tourToken) break;

        // Elevator floor HUD for staircase transitions
        if (STAIRCASE_NODE_IDS.has(nodeId)) {
          const stepMatch = steps.find(s => s.pano_id === nodeId);
          if (stepMatch && stepMatch.floor_transition) {
            showFloorHUD(stepMatch.floor_direction, stepMatch.to_floor_name);
            await wait(FLOOR_HOLD);
            hideFloorHUD();
          }
        }

        // Apply locked / calibrated heading
        const heading = getTargetOrientation(nodeId, window.activeTourQuery);

        if (viewer && typeof viewer.crossFadeTo === "function") {
          await viewer.crossFadeTo(nodeId, heading.yaw, heading.pitch);
        } else {
          await crossFadeTo(nodeId, heading.yaw, heading.pitch);
        }

        // Update left breadcrumb bubble
        updateBreadcrumbStep(nodeId);

        // Comfortable pacing: hold scene view for 1.8 seconds between steps
        await wait(1800);
      }

      // 3. Ensure audio finishes completely before beginning next phase
      await audioPromise;
      if (_activeTourCancelToken !== tourToken) break;

      await wait(500); // 500ms peaceful pause between phases
    }

    if (_activeTourCancelToken !== tourToken) return;

    // ── End navigation: smooth reset back to front entrance ──
    console.log("[Tour End] Navigation completed. Resetting to entrance...");
    await wait(800);
    if (_activeTourCancelToken !== tourToken) return;

    const entranceHeading = getTargetOrientation(START_NODE);
    if (viewer && typeof viewer.crossFadeTo === "function") {
      await viewer.crossFadeTo(START_NODE, entranceHeading.yaw, entranceHeading.pitch);
    } else {
      await crossFadeTo(START_NODE, entranceHeading.yaw, entranceHeading.pitch);
    }

    hideBreadcrumbBubble();
    hideShowcaseHUD();
    setStepLabel("", false);
    _traversing = false;

  } catch (err) {
    console.error("[Tour Execution Error]", err);
    cancelTraversal();
  }
}

/* ── Route traversal (Fallback) ───────────────────────────────────────────── */
function traverseRoute(steps, destinationTitle, destinationEntity = null) {
  stopShowcase();
  _traversing = true;
  let idx = 0;

  const viewer = window.viewer || viewerInstance;
  if (viewer) {
    viewer.activeTourDestination = destinationTitle || destinationEntity?.name || viewer.activeTourDestination || "";
  }

  const finalStep = steps && steps.length > 0 ? steps[steps.length - 1] : null;
  const finalDestId = [
    destinationEntity?.id,
    destinationEntity?.pano_id,
    destinationEntity?.linked_pano_id,
    destinationTitle,
    finalStep?.pano_id
  ].filter(Boolean).join(" ");

  buildBreadcrumb(steps);
  showBreadcrumb();

  async function next() {
    if (idx >= steps.length) return;
    const step = steps[idx];
    idx++;

    if (step.floor_transition && STAIRCASE_NODE_IDS.has(step.pano_id)) {
      showFloorHUD(step.floor_direction, step.to_floor_name);
      const t = setTimeout(async () => {
        hideFloorHUD();
        await doLoadStep(step, destinationEntity, finalDestId);
        updateBreadcrumbStep(step.pano_id);
        scheduleNext(next);
      }, FLOOR_HOLD);
      _stepTimers.push(t);
      return;
    }

    await doLoadStep(step, destinationEntity, finalDestId);
    updateBreadcrumbStep(step.pano_id);

    if (step.is_final) {
      const t = setTimeout(() => launchShowcase(step, destinationTitle), 800);
      _stepTimers.push(t);
    } else {
      scheduleNext(next);
    }
  }

  const first = steps[0];
  doLoadStep(first, destinationEntity, finalDestId);
  setStepLabel(`${first.title} · Step 1 of ${steps.length}`, true);
  updateBreadcrumbStep(first.pano_id);

  if (steps.length === 1) {
    const t = setTimeout(() => launchShowcase(first, destinationTitle), 800);
    _stepTimers.push(t);
  } else {
    idx = 1;
    scheduleNext(next);
  }
}

async function doLoadStep(step, destinationEntity = null, finalDestinationId = null) {
  stopShowcase();
  const nodeId = step.pano_id;
  const viewer = window.viewer || viewerInstance;
  if (viewer) {
    viewer.currentPanoId = nodeId;
  }

  const activeDest = viewer?.activeTourDestination || destinationEntity?.name || finalDestinationId || "";
  const targetHeading = getHeadingForScene(nodeId, activeDest);

  if (viewer && typeof viewer.setCameraHeading === "function") {
    viewer.setCameraHeading(targetHeading.yaw, targetHeading.pitch);
  } else {
    setCameraHeading(targetHeading.yaw, targetHeading.pitch);
  }

  if (viewer && typeof viewer.crossFadeTo === "function") {
    await viewer.crossFadeTo(nodeId, targetHeading.yaw, targetHeading.pitch);
  } else {
    await crossFadeTo(nodeId, targetHeading.yaw, targetHeading.pitch);
  }

  if (viewer && typeof viewer.setCameraHeading === "function") {
    viewer.setCameraHeading(targetHeading.yaw, targetHeading.pitch);
  } else {
    setCameraHeading(targetHeading.yaw, targetHeading.pitch);
  }

  setStepLabel(`${step.title} · Step ${step.index + 1} of ${step.total}`, true);
}

function scheduleNext(fn) {
  const t = setTimeout(fn, STEP_DELAY);
  _stepTimers.push(t);
}

function cancelTraversal() {
  _activeTourCancelToken++;
  _traversing = false;
  stopShowcase();
  const player = document.getElementById("kiosk-audio-player");
  if (player) {
    try {
      player.pause();
      player.currentTime = 0;
    } catch (_) {}
  }
  _stepTimers.forEach(clearTimeout);
  _stepTimers.forEach(clearInterval);
  _stepTimers = [];
  hideFloorHUD();
  hideShowcaseHUD();
  hideBreadcrumb();
  setStepLabel("", false);
}

/* ── Showcase (Fallback) ──────────────────────────────────────────────────── */
function launchShowcase(step, destinationTitle) {
  setStepLabel("", false);
  hideShowcaseHUD();

  startShowcaseOrbit();
  const t = setTimeout(() => {
    stopShowcase();
    hideBreadcrumb();
    setStepLabel("", false);
    _traversing = false;
    const startCalib = getStartCalib();
    loadPano(`/static/panos/${START_NODE}.jpg`, startCalib.yaw, startCalib.pitch);
  }, 5000);
  _stepTimers.push(t);
}

/* ── Floor HUD helpers ───────────────────────────────────────────────────── */
function showFloorHUD(direction, floorName) {
  $floorDir.textContent = direction === "up" ? "⬆" : "⬇";
  $floorLabel.textContent = direction === "up"
    ? `Ascending to ${floorName}`
    : `Descending to ${floorName}`;
  $floorHud.classList.add("active");
}
function hideFloorHUD() {
  $floorHud.classList.remove("active");
}

/* ── Showcase HUD helpers ────────────────────────────────────────────────── */
function showShowcaseHUD(title, secs) {
  if ($showcaseTxt) $showcaseTxt.textContent = `Exploring ${title}`;
  if ($showcaseCnt) $showcaseCnt.textContent = `${secs}s`;
  $showcaseHud.classList.add("active");
}
function hideShowcaseHUD() {
  $showcaseHud.classList.remove("active");
}

/* ── Breadcrumb helpers ──────────────────────────────────────────────────── */
function buildBreadcrumb(steps) {
  if (!$breadcrumbList) return;
  $breadcrumbList.innerHTML = "";
  steps.forEach((step, i) => {
    const el = document.createElement("div");
    el.className = "breadcrumb-step";
    el.dataset.index = i;
    el.dataset.nodeId = step.pano_id;
    el.innerHTML =
      `<span class="step-dot"></span>` +
      `<span>${step.title}</span>`;
    $breadcrumbList.appendChild(el);
  });
}

export function updateBreadcrumbStep(nodeId) {
  if (!$breadcrumbList) return;
  const items = Array.from($breadcrumbList.querySelectorAll(".breadcrumb-step"));
  const activeIdx = items.findIndex(el => el.dataset.nodeId === nodeId);
  if (activeIdx === -1) return;
  items.forEach((el, idx) => {
    el.classList.toggle("completed", idx < activeIdx);
    el.classList.toggle("active", idx === activeIdx);
  });
}

export function highlightBreadcrumbStep(activeIndex) {
  if (!$breadcrumbList) return;
  $breadcrumbList.querySelectorAll(".breadcrumb-step").forEach((el) => {
    const idx = parseInt(el.dataset.index, 10);
    el.classList.toggle("completed", idx < activeIndex);
    el.classList.toggle("active", idx === activeIndex);
    if (idx >= activeIndex) el.classList.remove("completed");
    if (idx !== activeIndex) el.classList.remove("active");
  });
}

function showBreadcrumb() {
  if ($breadcrumb) $breadcrumb.classList.remove("hidden");
}
function hideBreadcrumb() {
  if ($breadcrumb) $breadcrumb.classList.add("hidden");
}
export function hideBreadcrumbBubble() {
  hideBreadcrumb();
}
export function showBreadcrumbBubble() {
  showBreadcrumb();
}

/* ── Step label helpers ──────────────────────────────────────────────────── */
function setStepLabel(text, visible) {
  $stepLabel.textContent = text;
  $stepLabel.classList.toggle("visible", visible && !!text);
}

// Expose on window for external callers or testing
if (typeof window !== "undefined") {
  window.playSynchronizedTour = playSynchronizedTour;
  window.updateBreadcrumbStep = updateBreadcrumbStep;
  window.hideBreadcrumbBubble = hideBreadcrumbBubble;
  window.showBreadcrumbBubble = showBreadcrumbBubble;
}
