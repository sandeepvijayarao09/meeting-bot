// Offscreen document: owns the audio capture + WebSocket for the whole meeting.
// It outlives the popup and the service worker, which is why it exists.

const SERVER_URL = 'ws://127.0.0.1:8765';
const TAG_MIC = 0;
const TAG_TAB = 1;

/**
 * @typedef {Object} ServerMessage
 * @property {string} type
 * @property {string} [message]
 * @property {string} [session]
 * @property {string} [path]
 * @property {boolean} [summarized]
 */

/**
 * @typedef {Object} CaptureState
 * @property {boolean} recording
 * @property {WebSocket | null} ws
 * @property {AudioContext | null} ctx
 * @property {MediaStream[]} streams
 * @property {number | null} startedAt
 * @property {string | null} session
 */

/** @type {CaptureState} */
let state = idleState();

/** @returns {CaptureState} */
function idleState() {
  return { recording: false, ws: null, ctx: null, streams: [], startedAt: null, session: null };
}

/**
 * @param {unknown} e
 * @returns {string}
 */
function errorMessage(e) {
  return e instanceof Error ? e.message : String(e);
}

chrome.runtime.onMessage.addListener(
  /**
   * @param {{type?: string, streamId?: string, title?: string}} msg
   * @param {chrome.runtime.MessageSender} _sender
   * @param {(response?: unknown) => void} sendResponse
   * @returns {boolean | undefined}
   */
  (msg, _sender, sendResponse) => {
    if (msg.type === 'mb-offscreen-start') {
      start(msg)
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: errorMessage(e) }));
      return true;
    }
    if (msg.type === 'mb-stop') {
      stop()
        .then((r) => sendResponse(r))
        .catch((e) => sendResponse({ ok: false, error: errorMessage(e) }));
      return true;
    }
    if (msg.type === 'mb-status') {
      sendResponse({ recording: state.recording, startedAt: state.startedAt, session: state.session });
    }
    return undefined;
  }
);

/** @returns {Promise<WebSocket>} */
function connect() {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(SERVER_URL);
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => resolve(ws);
    ws.onerror = () =>
      reject(new Error('Cannot reach the Meeting Bot server. Run: uv run mbot serve'));
  });
}

/**
 * Waits for the next JSON (text) frame from the server.
 * @param {WebSocket} ws
 * @param {number} [timeoutMs]
 * @returns {Promise<ServerMessage>}
 */
function nextMessage(ws, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('server timed out')), timeoutMs ?? 30000);
    ws.onmessage = (e) => {
      if (typeof e.data !== 'string') return;
      clearTimeout(timer);
      ws.onmessage = null;
      resolve(/** @type {ServerMessage} */ (JSON.parse(e.data)));
    };
    ws.onclose = () => {
      clearTimeout(timer);
      reject(new Error('server closed the connection'));
    };
  });
}

/**
 * @param {{streamId?: string, title?: string}} options
 * @returns {Promise<{ok: boolean, session?: string}>}
 */
async function start({ streamId, title }) {
  if (state.recording) throw new Error('already recording');
  if (!streamId) throw new Error('missing tab stream id');

  const ws = await connect();

  // chromeMediaSource constraints are a Chrome extension, not in the standard
  // MediaStreamConstraints type — hence the cast.
  const tabConstraints = /** @type {MediaStreamConstraints} */ (
    /** @type {unknown} */ ({
      audio: { mandatory: { chromeMediaSource: 'tab', chromeMediaSourceId: streamId } },
      video: false,
    })
  );
  const tabStream = await navigator.mediaDevices.getUserMedia(tabConstraints);

  /** @type {MediaStream} */
  let micStream;
  try {
    micStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch {
    tabStream.getTracks().forEach((t) => t.stop());
    ws.close();
    throw new Error(
      'Microphone not allowed for the extension yet — click "Enable microphone" in the popup first.'
    );
  }

  // 16 kHz context: Chrome resamples internally; ideal rate for Whisper, and
  // wideband-voice quality for the passthrough you keep hearing.
  const ctx = new AudioContext({ sampleRate: 16000 });
  await ctx.audioWorklet.addModule('pcm-worklet.js');

  /**
   * @param {number} tag
   * @returns {(e: MessageEvent) => void}
   */
  const sendFrames = (tag) => (e) => {
    if (ws.readyState !== WebSocket.OPEN) return;
    const pcm = new Uint8Array(/** @type {ArrayBuffer} */ (e.data));
    const frame = new Uint8Array(pcm.length + 1);
    frame[0] = tag;
    frame.set(pcm, 1);
    ws.send(frame);
  };

  // Tab audio: capture AND pass through so the user still hears the meeting.
  const tabSrc = ctx.createMediaStreamSource(tabStream);
  const tabNode = new AudioWorkletNode(ctx, 'pcm-sender');
  tabNode.port.onmessage = sendFrames(TAG_TAB);
  tabSrc.connect(tabNode);
  tabNode.connect(ctx.destination);

  // Mic: capture only — muted gain keeps the graph pulling without echo.
  const micSrc = ctx.createMediaStreamSource(micStream);
  const micNode = new AudioWorkletNode(ctx, 'pcm-sender');
  micNode.port.onmessage = sendFrames(TAG_MIC);
  const mute = ctx.createGain();
  mute.gain.value = 0;
  micSrc.connect(micNode);
  micNode.connect(mute);
  mute.connect(ctx.destination);

  ws.send(JSON.stringify({ type: 'start', title: title || '' }));
  const started = await nextMessage(ws);
  if (started.type !== 'started') {
    [tabStream, micStream].forEach((s) => s.getTracks().forEach((t) => t.stop()));
    void ctx.close();
    ws.close();
    throw new Error(started.message || 'server refused to start a session');
  }

  state = {
    recording: true,
    ws,
    ctx,
    streams: [tabStream, micStream],
    startedAt: Date.now(),
    session: started.session ?? null,
  };
  void chrome.runtime.sendMessage({ type: 'mb-recording-started' });
  return { ok: true, session: started.session };
}

/**
 * @returns {Promise<{ok: boolean, error?: string, path?: string, summarized?: boolean}>}
 */
async function stop() {
  if (!state.recording || !state.ws || !state.ctx) {
    return { ok: false, error: 'not recording' };
  }
  const { ws, ctx, streams } = state;
  state.recording = false;

  streams.forEach((s) => s.getTracks().forEach((t) => t.stop()));
  await ctx.close();
  ws.send(JSON.stringify({ type: 'stop' }));

  // Finishing transcription + the NIM summary can take a while on long meetings.
  /** @type {ServerMessage} */
  let reply;
  try {
    reply = await nextMessage(ws, 15 * 60 * 1000);
  } finally {
    ws.close();
    state = idleState();
  }
  void chrome.runtime.sendMessage({
    type: 'mb-finished',
    path: reply.path,
    summarized: reply.summarized,
  });
  return { ok: true, path: reply.path, summarized: reply.summarized };
}
