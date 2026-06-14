// Popup UI: starts/stops a recording. The popup is ephemeral — all capture
// state lives in the offscreen document; this page just sends messages.

/**
 * @param {string} id
 * @returns {HTMLElement}
 */
function $(id) {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing element #${id}`);
  return el;
}

const toggleBtn = /** @type {HTMLButtonElement} */ ($('toggle'));
const titleInput = /** @type {HTMLInputElement} */ ($('title'));
const statusEl = $('status');
const micLink = $('mic-link');

let recording = false;
/** @type {number | undefined} */
let timer;

void init();

async function init() {
  const status = await offscreenStatus();
  if (status && status.recording && status.startedAt) {
    setRecordingUI(status.startedAt);
  }
  toggleBtn.addEventListener('click', () => void onToggle());
  $('mic-enable').addEventListener('click', () => {
    void chrome.tabs.create({ url: chrome.runtime.getURL('permission.html') });
  });
}

/**
 * @returns {Promise<{recording: boolean, startedAt: number | null} | null>}
 */
async function offscreenStatus() {
  try {
    return await chrome.runtime.sendMessage({ type: 'mb-status' });
  } catch {
    return null; // no offscreen document -> idle
  }
}

async function onToggle() {
  toggleBtn.disabled = true;
  try {
    if (!recording) await startRecording();
    else await stopRecording();
  } finally {
    toggleBtn.disabled = false;
  }
}

async function startRecording() {
  statusEl.textContent = 'Starting…';
  micLink.style.display = 'none';

  // Mic permission must be granted to the extension before the offscreen
  // document can use it (offscreen pages cannot show permission prompts).
  try {
    const probe = await navigator.mediaDevices.getUserMedia({ audio: true });
    probe.getTracks().forEach((t) => t.stop());
  } catch {
    statusEl.textContent = 'Microphone permission needed.';
    micLink.style.display = 'block';
    return;
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || tab.id === undefined) {
    statusEl.textContent = 'No active tab.';
    return;
  }
  const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tab.id });
  /** @type {{ok: boolean, error?: string} | undefined} */
  const res = await chrome.runtime.sendMessage({
    type: 'mb-start',
    streamId,
    title: titleInput.value.trim() || tab.title || '',
  });
  if (!res || !res.ok) {
    statusEl.textContent = res?.error || 'Failed to start.';
    return;
  }
  setRecordingUI(Date.now());
}

async function stopRecording() {
  statusEl.textContent =
    'Stopping — transcribing & summarizing…\n(The note opens automatically when ready.)';
  clearInterval(timer);
  toggleBtn.textContent = 'Working…';
  try {
    /** @type {{ok: boolean, error?: string, summarized?: boolean} | undefined} */
    const res = await chrome.runtime.sendMessage({ type: 'mb-stop' });
    if (res && res.ok) {
      statusEl.textContent = res.summarized
        ? 'Note ready (opened on your Mac).'
        : 'Transcript saved — run `mbot summarize` once your API key is set.';
    } else {
      statusEl.textContent = res?.error || 'Failed to stop.';
    }
  } catch {
    // Popup may outlive the message channel on long meetings; the server
    // still finishes and opens the note.
    statusEl.textContent = 'Finishing in the background — the note will open when ready.';
  }
  recording = false;
  toggleBtn.textContent = 'Start recording this tab';
  toggleBtn.classList.remove('stop');
}

/**
 * @param {number} startedAt epoch ms when the recording began
 */
function setRecordingUI(startedAt) {
  recording = true;
  toggleBtn.textContent = 'Stop & make note';
  toggleBtn.classList.add('stop');
  const tick = () => {
    const s = Math.floor((Date.now() - startedAt) / 1000);
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    statusEl.textContent = `● Recording — ${mm}:${ss}`;
  };
  tick();
  timer = setInterval(tick, 1000);
}
