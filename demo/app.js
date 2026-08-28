const cameras = {
  cam1: {
    title: "Wide room view",
    label: "Camera 1 · wide room",
    source: "media/cam1.mp4",
    poster: "media/cam1.jpg",
    reason: "Best view of the team and patient",
  },
  cam2: {
    title: "Bedside overhead view",
    label: "Camera 2 · bedside overhead",
    source: "media/cam2.mp4",
    poster: "media/cam2.jpg",
    reason: "Closer view of bedside activity",
  },
  cam3: {
    title: "Doorway view",
    label: "Camera 3 · doorway",
    source: "media/cam3.mp4",
    poster: "media/cam3.jpg",
    reason: "Alternative view of team coordination",
  },
  monitor: {
    title: "Patient monitor view",
    label: "Monitor · vitals display",
    source: "media/monitor.mp4",
    poster: "media/monitor.jpg",
    reason: "Independent view of changing observations",
  },
};

const moments = {
  oxygen: {
    title: "Oxygen escalation discussed",
    summary: "The transcript and observed team activity indicate an escalation in response to a changing patient state.",
    camera: "cam1",
    offset: 4,
    window: "06:00–06:30",
    available: "5 of 5 modalities",
    transcript: "“Saturations are falling again. Let’s increase oxygen and reassess now.”",
    transcriptCitation: "TR-006-041",
    transcriptTime: "06:03–06:07",
    speakerLabel: "P02",
    speakerKind: "Active speaker",
    speakerContext: "Localized to the harness-selected view",
    visual: "Three tracked participants are positioned around the bedside while one participant gestures toward the patient.",
    visualCitation: "VS-006-041",
    secondaryKind: "Visual scene",
    selectionSource: "Camera 1 selected",
    selectionBasis: "Highest ASD",
    modalityCitation: "MC-006-041",
    modalities: ["transcript", "speaker", "scene", "attention", "monitor"],
  },
  roles: {
    title: "Team reallocates roles",
    summary: "A direct verbal allocation is followed by a visible shift in activity around the bedside.",
    camera: "cam3",
    offset: 9,
    window: "06:00–06:30",
    available: "4 of 5 modalities",
    transcript: "“Can you watch the monitor while I reassess the airway?”",
    transcriptCitation: "TR-006-090",
    transcriptTime: "06:08–06:11",
    speakerLabel: "P01",
    speakerKind: "Active speaker",
    speakerContext: "Localized to the harness-selected doorway view",
    visual: "The doorway view preserves three anonymous tracks within this view as activity shifts around the patient.",
    visualCitation: "VS-006-090",
    secondaryKind: "Visual scene",
    selectionSource: "Camera 3 selected",
    selectionBasis: "Highest ASD",
    modalityCitation: "MC-006-090",
    modalities: ["transcript", "speaker", "scene", "attention"],
  },
  monitor: {
    title: "Monitor change prompts reassessment",
    summary: "Monitor evidence and the following exchange converge on a need to reassess the patient response.",
    camera: "monitor",
    offset: 13,
    window: "06:00–06:30",
    available: "5 of 5 modalities",
    transcript: "“Check that reading again and tell me if the trend continues.”",
    transcriptCitation: "TR-006-132",
    transcriptTime: "06:12–06:15",
    speakerLabel: "ASR",
    speakerKind: "Room audio",
    speakerContext: "Speech aligned temporally with the monitor change",
    visual: "The independent monitor view supplies a directly inspectable source alongside the room-camera evidence.",
    visualCitation: "OCR-006-132",
    secondaryKind: "Monitor OCR",
    selectionSource: "Monitor selected",
    selectionBasis: "Direct source",
    modalityCitation: "MC-006-132",
    modalities: ["transcript", "speaker", "scene", "attention", "monitor"],
  },
};

const STORAGE_KEY = "expert-vision-agent-harness.demo.v1";

function loadSavedReview() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
  } catch {
    return {};
  }
}

const savedReview = loadSavedReview();
const state = {
  camera: "cam1",
  moment: null,
  playbackTime: 4,
  decisions: savedReview.decisions || {},
  notes: savedReview.notes || {},
};

const video = document.querySelector("#main-video");
const videoFrame = document.querySelector("#video-frame");
const videoStage = document.querySelector("#video-stage");
const playControl = document.querySelector("#play-control");
const centerPlay = document.querySelector("#center-play");
const progress = document.querySelector("#video-progress");
const elapsed = document.querySelector("#elapsed-time");
const toast = document.querySelector("#toast");
let toastTimer;
let cameraLoadGeneration = 0;
let pendingPlaybackTime = null;

function saveReview() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ decisions: state.decisions, notes: state.notes }));
  } catch {
    // The demo remains usable if browser storage is disabled, but the interface
    // must not imply persistence that the browser did not provide.
    const status = document.querySelector("#save-status");
    if (status) status.textContent = "Stored for this tab only";
  }
}

function openDrawer(selector) {
  document.querySelectorAll(".drawer-dialog[open]").forEach((dialog) => dialog.close());
  document.querySelector(selector).showModal();
}

function excerptTime(seconds) {
  return `06:${String(Math.min(15, Math.max(0, Math.floor(seconds)))).padStart(2, "0")}`;
}

function setPlaying(isPlaying) {
  videoFrame.classList.toggle("playing", isPlaying);
  videoStage.classList.toggle("playing", isPlaying);
  playControl.setAttribute("aria-label", isPlaying ? "Pause excerpt" : "Play or pause excerpt");
  centerPlay.setAttribute("aria-label", isPlaying ? "Pause selected video" : "Play selected video");
}

function togglePlayback() {
  if (video.ended) video.currentTime = 0;
  if (video.paused) video.play().catch(() => setPlaying(false));
  else video.pause();
}

function showToast(message) {
  clearTimeout(toastTimer);
  toast.textContent = message;
  toast.classList.add("show");
  toastTimer = setTimeout(() => toast.classList.remove("show"), 2200);
}

function selectCamera(cameraKey, { seekTo = null } = {}) {
  const camera = cameras[cameraKey];
  if (!camera) return;
  const wasPlaying = !video.paused;
  const preservedTime = seekTo ?? pendingPlaybackTime ?? state.playbackTime;
  const loadGeneration = ++cameraLoadGeneration;
  pendingPlaybackTime = preservedTime;
  state.playbackTime = preservedTime;
  state.camera = cameraKey;

  video.pause();
  video.src = camera.source;
  video.poster = camera.poster;
  video.load();
  video.addEventListener("loadedmetadata", () => {
    if (loadGeneration !== cameraLoadGeneration) return;
    progress.max = video.duration;
    video.currentTime = Math.min(preservedTime, Math.max(0, video.duration - 0.1));
    progress.setAttribute("aria-valuetext", `${excerptTime(video.currentTime)} of 06:15`);
    video.addEventListener("seeked", () => {
      if (loadGeneration !== cameraLoadGeneration) return;
      state.playbackTime = video.currentTime;
      pendingPlaybackTime = null;
    }, { once: true });
    if (wasPlaying) video.play().catch(() => setPlaying(false));
  }, { once: true });

  document.querySelector("#viewer-title").textContent = camera.title;
  document.querySelector("#video-camera-label").innerHTML = `<i></i>${camera.label}`;
  document.querySelector("#selection-reason").textContent = camera.reason;
  const harnessSelected = cameraKey === moments[state.moment].camera;
  document.querySelector("#selection-kind").innerHTML = `<i></i>${harnessSelected ? "Harness selection" : "Comparison view"}`;

  document.querySelectorAll(".camera-choice").forEach((button) => {
    const active = button.dataset.camera === cameraKey;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", String(active));
    button.tabIndex = active ? 0 : -1;
    const oldLabel = button.querySelector(".camera-thumb > i");
    if (oldLabel) oldLabel.remove();
    if (active) {
      const label = document.createElement("i");
      label.textContent = harnessSelected ? "Selected by harness" : "Viewing";
      button.querySelector(".camera-thumb").append(label);
    }
  });
}

function selectMoment(momentKey) {
  const moment = moments[momentKey];
  if (!moment) return;
  const noteInput = document.querySelector("#educator-note");
  if (noteInput && state.moment) {
    state.notes[state.moment] = noteInput.value;
    saveReview();
  }
  state.moment = momentKey;
  document.querySelectorAll(".moment").forEach((button) => {
    const active = button.dataset.moment === momentKey;
    button.classList.toggle("active", active);
    button.setAttribute("aria-checked", String(active));
    button.tabIndex = active ? 0 : -1;
  });

  document.querySelector("#moment-summary").textContent = moment.summary;
  document.querySelector("#window-value").textContent = moment.window;
  document.querySelector("#available-value").textContent = moment.available;
  document.querySelector("#evidence-title").textContent = moment.title;
  document.querySelector("#drawer-title").textContent = moment.title;
  document.querySelector("#preview-citation").textContent = moment.transcriptCitation;
  document.querySelector("#preview-time").textContent = moment.transcriptTime;
  document.querySelector("#quote-preview").textContent = moment.transcript.replace(/^“|”$/g, "");
  document.querySelector("#transcript-text").textContent = moment.transcript;
  document.querySelector("#transcript-citation").textContent = moment.transcriptCitation;
  document.querySelector("#transcript-time").textContent = moment.transcriptTime;
  document.querySelector("#speaker-label").textContent = moment.speakerLabel;
  document.querySelector("#speaker-kind").textContent = moment.speakerKind;
  document.querySelector("#speaker-context").textContent = moment.speakerContext;
  document.querySelector("#visual-text").textContent = moment.visual;
  document.querySelector("#visual-citation").textContent = moment.visualCitation;
  document.querySelector("#secondary-kind").textContent = moment.secondaryKind;
  document.querySelector("#secondary-dot").className = moment.secondaryKind === "Monitor OCR" ? "context-dot" : "visual-dot";
  document.querySelector("#selection-source").textContent = moment.selectionSource;
  document.querySelector("#selection-basis").textContent = moment.selectionBasis;
  document.querySelector("#modality-citation").textContent = moment.modalityCitation;
  document.querySelectorAll("[data-modality]").forEach((item) => {
    const available = moment.modalities.includes(item.dataset.modality);
    item.classList.toggle("unavailable", !available);
    item.setAttribute("aria-label", `${item.textContent.trim()}: ${available ? "available" : "unavailable"}`);
  });
  document.querySelector("#educator-note").value = state.notes[momentKey] || state.decisions[momentKey]?.note || "";

  selectCamera(moment.camera, { seekTo: moment.offset });
  updateDecisionControls();
}

function updateDecisionControls() {
  const current = state.decisions[state.moment];
  const status = document.querySelector("#decision-status");
  document.querySelectorAll("[data-decision]").forEach((button) => {
    button.classList.toggle("selected", current?.decision === button.dataset.decision);
  });
  const labels = { accepted: "Included", amended: "Amendment noted", rejected: "Excluded" };
  status.textContent = current ? labels[current.decision] : "Awaiting review";
  status.classList.toggle("resolved-status", Boolean(current));

  // The queue shows the outcome, not just that a decision happened: an excluded
  // moment and an included one must not read the same at a glance.
  const outcomeLabels = { accepted: "Included", amended: "Amended", rejected: "Excluded" };
  document.querySelectorAll(".moment").forEach((button) => {
    const record = state.decisions[button.dataset.moment];
    const priority = button.querySelector(".priority");
    priority.dataset.originalLabel ||= priority.textContent;
    button.classList.toggle("reviewed", Boolean(record));
    priority.textContent = record ? outcomeLabels[record.decision] : priority.dataset.originalLabel;
    priority.dataset.outcome = record ? record.decision : "";
  });

  const total = Object.keys(moments).length;
  const reviewed = Object.keys(state.decisions).length;
  const included = Object.values(state.decisions).filter((item) => item.decision !== "rejected").length;
  document.querySelector("#reviewed-count").textContent = reviewed;
  document.querySelector("#plan-count").textContent = included;
  document.querySelector("#plan-reviewed-count").textContent = included;
  document.querySelector("#review-progress-bar").style.width = `${(reviewed / total) * 100}%`;

  const complete = reviewed === total;
  document.querySelector(".review-meter").classList.toggle("complete", complete);
  const workspaceStatus = document.querySelector("#workspace-status");
  if (complete) {
    workspaceStatus.textContent = included === 1
      ? `All ${total} moments reviewed. 1 is included in the debrief plan.`
      : `All ${total} moments reviewed. ${included} are included in the debrief plan.`;
  } else if (current) {
    workspaceStatus.textContent = `${moments[state.moment].title} has been ${labels[current.decision].toLowerCase()}.`;
  } else {
    workspaceStatus.textContent = "Inspect the harness-selected evidence and record an educator decision.";
  }
}

function decide(decision) {
  const rawNote = document.querySelector("#educator-note").value;
  const note = rawNote.trim();
  state.notes[state.moment] = rawNote;
  state.decisions[state.moment] = {
    decision,
    note,
  };
  saveReview();
  updateDecisionControls();
  const messages = { accepted: "Moment added to the debrief plan", amended: "Moment saved with an amendment", rejected: "Moment excluded from the plan" };
  showToast(messages[decision]);
}

function openPlan() {
  const container = document.querySelector("#plan-items");
  const items = Object.entries(state.decisions).filter(([, value]) => value.decision !== "rejected");
  container.replaceChildren();
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = "Nothing here yet. Include or amend a moment in the review panel and it will appear in this plan.";
    container.append(empty);
  } else {
    items.forEach(([key, value]) => {
      const item = document.createElement("div");
      item.className = "plan-item";
      const summary = document.createElement("span");
      const title = document.createElement("b");
      const detail = document.createElement("small");
      const status = document.createElement("i");
      title.textContent = moments[key].title;
      detail.textContent = value.note || moments[key].transcriptTime;
      status.textContent = value.decision === "amended" ? "Amended" : "Included";
      summary.append(title, detail);
      item.append(summary, status);
      container.append(item);
    });
  }
  openDrawer("#plan-dialog");
}

video.addEventListener("play", () => setPlaying(true));
video.addEventListener("pause", () => setPlaying(false));
video.addEventListener("ended", () => setPlaying(false));
video.addEventListener("timeupdate", () => {
  const duration = Number.isFinite(video.duration) ? video.duration : 15;
  const percentage = Math.min(100, (video.currentTime / duration) * 100);
  progress.value = video.currentTime;
  if (pendingPlaybackTime === null) state.playbackTime = video.currentTime;
  progress.max = duration;
  progress.style.setProperty("--progress", `${percentage}%`);
  elapsed.textContent = excerptTime(video.currentTime);
  progress.setAttribute("aria-valuetext", `${excerptTime(video.currentTime)} of 06:15`);
});
video.addEventListener("click", togglePlayback);
playControl.addEventListener("click", togglePlayback);
centerPlay.addEventListener("click", togglePlayback);
progress.addEventListener("input", () => {
  pendingPlaybackTime = null;
  state.playbackTime = Number(progress.value);
  video.currentTime = state.playbackTime;
  progress.setAttribute("aria-valuetext", `${excerptTime(state.playbackTime)} of 06:15`);
});
document.querySelector("#restart-video").addEventListener("click", () => {
  video.currentTime = 0;
  video.play().catch(() => setPlaying(false));
});

document.querySelectorAll(".camera-choice").forEach((button) => {
  button.addEventListener("click", () => selectCamera(button.dataset.camera));
});
document.querySelectorAll(".moment").forEach((button) => {
  button.addEventListener("click", () => selectMoment(button.dataset.moment));
});

function addRadioGroupKeys(containerSelector, itemSelector, previousKey, nextKey) {
  document.querySelector(containerSelector).addEventListener("keydown", (event) => {
    if (![previousKey, nextKey].includes(event.key)) return;
    const items = [...document.querySelectorAll(itemSelector)];
    const current = items.indexOf(document.activeElement);
    if (current < 0) return;
    event.preventDefault();
    const direction = event.key === nextKey ? 1 : -1;
    const next = items[(current + direction + items.length) % items.length];
    next.click();
    next.focus();
  });
}

addRadioGroupKeys(".camera-picker", ".camera-choice", "ArrowLeft", "ArrowRight");
addRadioGroupKeys(".moment-list", ".moment", "ArrowUp", "ArrowDown");

document.querySelectorAll("[data-decision]").forEach((button) => {
  button.addEventListener("click", () => decide(button.dataset.decision));
});
document.querySelector("#educator-note").addEventListener("input", (event) => {
  state.notes[state.moment] = event.target.value;
  if (state.decisions[state.moment]) state.decisions[state.moment].note = event.target.value.trim();
  saveReview();
});
document.querySelector("#view-plan").addEventListener("click", openPlan);
document.querySelector("#open-evidence").addEventListener("click", () => openDrawer("#evidence-dialog"));
document.querySelector("#session-info").addEventListener("click", () => openDrawer("#session-dialog"));
document.querySelector("#next-moment").addEventListener("click", () => {
  const keys = Object.keys(moments);
  const current = keys.indexOf(state.moment);
  const next = Math.min(keys.length - 1, current + 1);
  if (next === current) {
    // Last moment: route into the plan rather than dead-ending on a toast.
    showToast("That was the last flagged moment. Opening the debrief plan.");
    openPlan();
    return;
  }
  selectMoment(keys[next]);
});
document.querySelectorAll(".drawer-close").forEach((button) => {
  button.addEventListener("click", () => button.closest("dialog").close());
});
document.querySelectorAll(".drawer-dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
});

// Shortcuts are for the page, not for focused controls. Space is the native
// activation key for a button, so intercepting it while one has focus swallows
// the click and starts the video instead (WCAG 2.1.1).
const INTERACTIVE = "button, a, input, textarea, select, [role='slider'], [contenteditable='true']";
const TEXT_ENTRY = "input, textarea, select, [contenteditable='true']";

document.addEventListener("keydown", (event) => {
  if (document.querySelector(".drawer-dialog[open]")) return;
  const onControl = Boolean(event.target?.closest?.(INTERACTIVE))
    || Boolean(document.activeElement?.closest?.(INTERACTIVE));
  const inTextEntry = Boolean(event.target?.closest?.(TEXT_ENTRY))
    || Boolean(document.activeElement?.closest?.(TEXT_ENTRY));

  if (event.code === "Space" && !onControl) {
    event.preventDefault();
    togglePlayback();
  }
  if (["KeyJ", "KeyK"].includes(event.code) && !inTextEntry) {
    event.preventDefault();
    const keys = Object.keys(moments);
    const current = keys.indexOf(state.moment);
    const next = event.code === "KeyJ" ? Math.min(keys.length - 1, current + 1) : Math.max(0, current - 1);
    selectMoment(keys[next]);
    document.querySelector(`[data-moment="${keys[next]}"]`).focus();
  }
});

selectMoment("oxygen");
