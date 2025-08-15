// ===== Config =====
const API_BASE = "http://127.0.0.1:8000"; // change for prod if needed

// ===== Session ID in URL (with fallback) =====
function getSessionId() {
  const params = new URLSearchParams(location.search);
  let sid = params.get("session_id");
  if (!sid) {
    const uuid = (crypto && crypto.randomUUID)
      ? crypto.randomUUID()
      : "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, c => {
          const r = (Math.random() * 16) | 0;
          const v = c === "x" ? r : (r & 0x3) | 0x8;
          return v.toString(16);
        });
    sid = uuid;
    params.set("session_id", sid);
    const newUrl = `${location.pathname}?${params.toString()}${location.hash || ""}`;
    history.replaceState({}, "", newUrl);
  }
  return sid;
}
const sessionId = getSessionId();

// ===== Elements =====
const recordBtn = document.getElementById("recordBtn");
const stopLoopBtn = document.getElementById("stopLoopBtn");
// Support both old and new IDs so UI always updates
const transcriptionText =
  document.getElementById("transcriptionText") ||
  document.getElementById("TranscriptionText");

// Wrap/ensure a label span so we can update text without removing icons/dot
function getRecordLabelEl() {
  let el = recordBtn.querySelector("[data-label]");
  if (el) return el;
  for (const node of [...recordBtn.childNodes]) {
    if (node.nodeType === Node.TEXT_NODE && node.textContent.trim().length) {
      const span = document.createElement("span");
      span.dataset.label = "true";
      span.textContent = node.textContent.trim();
      recordBtn.replaceChild(span, node);
      return span;
    }
  }
  const span = document.createElement("span");
  span.dataset.label = "true";
  span.textContent = "Start Recording";
  recordBtn.appendChild(span);
  return span;
}
const recordLabelEl = getRecordLabelEl();

// ===== State =====
let mediaRecorder = null;
let mediaStream = null;
let recorderMimeType = "audio/webm";
let audioChunks = [];
let isRecording = false;
let isStarting = false;
let conversationLoop = false;

let currentFetchController = null;

// Single reusable audio player to avoid overlapping instances
const player = new Audio();
player.preload = "auto";
let playerStarted = false;

// Token to ensure only the latest response plays
let turnToken = 0;

// ===== Helpers =====
function setRecordingUI(recording) {
  recordBtn.classList.toggle("recording", recording);
  recordBtn.setAttribute("aria-pressed", String(recording));
  recordLabelEl.textContent = recording ? "Stop Recording" : "Start Recording";
}
function showStopLoopBtn(show) {
  stopLoopBtn?.classList.toggle("hidden", !show);
}
function setStatus(msg) {
  if (!transcriptionText) {
    console.warn("transcriptionText element not found");
    return;
  }
  transcriptionText.textContent = msg;
}
function stopMediaTracks() {
  if (mediaStream) {
    try { mediaStream.getTracks().forEach(t => t.stop()); } catch {}
    mediaStream = null;
  }
}
function pickMimeType() {
  if (!("MediaRecorder" in window) || typeof MediaRecorder.isTypeSupported !== "function") return "";
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4;codecs=mp4a",
    "audio/aac",
  ];
  return candidates.find(t => MediaRecorder.isTypeSupported(t)) || "";
}
function stopPlayback() {
  try {
    player.pause();
    player.src = "";
    player.load();
  } catch {}
  playerStarted = false;
}

// ===== Button: Start/Stop Recording (and loop) =====
recordBtn.addEventListener("click", async () => {
  if (isStarting) return;

  if (!isRecording) {
    conversationLoop = true;
    showStopLoopBtn(true);
    await startRecording();
  } else {
    // Stop the mic, but DO NOT abort the pending upload/response for this turn.
    // We want the current reply to arrive and play.
    conversationLoop = false;
    showStopLoopBtn(false);
    stopRecording();
    // Do not: currentFetchController?.abort();
    // Do not: turnToken++; (would invalidate the current turn)
  }
});

// ===== Button: Stop Conversation Loop =====
stopLoopBtn?.addEventListener("click", () => {
  conversationLoop = false;
  try { currentFetchController?.abort(); } catch {}
  turnToken++; // invalidate any pending turn
  stopRecording();
  stopPlayback();
  setStatus(`${transcriptionText?.textContent || ""}\n🛑 Conversation loop stopped.`);
  showStopLoopBtn(false);
});

// ===== Start Recording =====
async function startRecording() {
  if (!navigator.mediaDevices || !window.MediaRecorder) {
    setStatus("❌ Recording not supported in this browser.");
    return;
  }
  if (isRecording) return;

  try {
    isStarting = true;

    const constraints = {
      audio: {
        channelCount: 1,
        noiseSuppression: true,
        echoCancellation: true,
        autoGainControl: true,
      },
    };
    mediaStream = await navigator.mediaDevices.getUserMedia(constraints);

    const mime = pickMimeType();
    mediaRecorder = mime ? new MediaRecorder(mediaStream, { mimeType: mime }) : new MediaRecorder(mediaStream);
    recorderMimeType = mediaRecorder.mimeType || mime || "audio/webm";
    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) audioChunks.push(e.data);
    };

    mediaRecorder.addEventListener("stop", () => {
      handleAudioUpload().finally(() => {
        stopMediaTracks();
        mediaRecorder = null;
      });
    }, { once: true });

    mediaRecorder.start();
    isRecording = true;
    setRecordingUI(true);
    setStatus("🎙 Listening...");
  } catch (err) {
    console.error("Mic error", err);
    setStatus("❌ Mic access denied or unavailable.");
    stopMediaTracks();
  } finally {
    isStarting = false;
  }
}

// ===== Stop Recording =====
function stopRecording() {
  if (!isRecording && !mediaRecorder) {
    stopMediaTracks();
    setRecordingUI(false);
    return;
  }
  isRecording = false;
  setRecordingUI(false);
  try {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
    } else {
      stopMediaTracks();
    }
  } catch (e) {
    console.warn("Stopping recorder failed", e);
    stopMediaTracks();
  }
}

// ===== Upload and handle server response (single playback) =====
async function handleAudioUpload() {
  if (!audioChunks.length) {
    setStatus("⚠️ No audio captured. Try again.");
    if (conversationLoop) await startRecording();
    return;
  }

  setStatus("⏫ Uploading...");

  const ext = recorderMimeType.includes("webm") ? "webm"
    : recorderMimeType.includes("ogg") ? "ogg"
    : recorderMimeType.includes("mp4") ? "m4a"
    : recorderMimeType.includes("aac") ? "aac"
    : "dat";

  const audioBlob = new Blob(audioChunks, { type: recorderMimeType || "audio/webm" });
  const formData = new FormData();
  formData.append("audio", audioBlob, `recording.${ext}`);

  // Abort any previous pending call only when starting a NEW upload
  try { currentFetchController?.abort(); } catch {}
  currentFetchController = new AbortController();

  // Token for this turn
  const myTurn = ++turnToken;

  try {
    const res = await fetch(`${API_BASE}/agent/chat/${encodeURIComponent(sessionId)}`, {
      method: "POST",
      body: formData,
      signal: currentFetchController.signal,
      headers: { Accept: "application/json" },
    });

    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    console.log("agent/chat response", data);

    if (myTurn !== turnToken) return; // stale

    const userTxt = data.transcribed_text || "❌ No transcription";
    const aiTxt = data.llm_response || "❌ No response";
    setStatus(`User: ${userTxt}\nAI: ${aiTxt}`);

    if (data.audio_url) {
      try { speechSynthesis?.cancel(); } catch {}

      // Use a single player
      const url = new URL(data.audio_url, location.origin).href;
      playerStarted = false;

      player.onended = () => {
        if (myTurn !== turnToken) return;
        if (conversationLoop) startRecording();
      };
      player.onerror = () => {
        if (myTurn !== turnToken) return;
        if (!playerStarted) {
          console.error("Error loading/playing AI audio");
          // playFallbackAudio(aiTxt); // optional
          if (conversationLoop) startRecording();
        }
      };

      stopPlayback();
      player.src = url;

      try {
        await player.play();
        playerStarted = true;
      } catch (playErr) {
        console.warn("Autoplay failed", playErr);
        // playFallbackAudio(aiTxt); // optional
        if (conversationLoop) startRecording();
      }
    } else {
      setStatus("⚠️ No audio returned.");
      // playFallbackAudio(aiTxt); // optional
      if (conversationLoop) startRecording();
    }
  } catch (error) {
    if (error.name === "AbortError") return; // aborted by Stop Loop
    console.error("Error during upload or API call:", error);
    setStatus("❌ Connection failed.");
    // playFallbackAudio(); // optional
    if (conversationLoop) startRecording();
  }
}

// Cleanup on unload
window.addEventListener("beforeunload", () => {
  try { speechSynthesis?.cancel(); } catch {}
  try { currentFetchController?.abort(); } catch {}
  stopPlayback();
  stopMediaTracks();
});