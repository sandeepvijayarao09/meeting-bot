// Service worker: offscreen-document lifecycle + toolbar badge.
// All capture state lives in the offscreen document, which survives
// this worker being suspended mid-meeting.

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
    if (msg.type === 'mb-start') {
      void handleStart(msg).then(sendResponse);
      return true;
    }
    if (msg.type === 'mb-recording-started') {
      void chrome.action.setBadgeText({ text: 'REC' });
      void chrome.action.setBadgeBackgroundColor({ color: '#d22' });
    }
    if (msg.type === 'mb-finished') {
      void chrome.action.setBadgeText({ text: '' });
      setTimeout(() => chrome.offscreen.closeDocument().catch(() => {}), 500);
    }
    return undefined;
  }
);

/**
 * @param {{streamId?: string, title?: string}} msg
 * @returns {Promise<{ok: boolean, error?: string}>}
 */
async function handleStart(msg) {
  try {
    const has = await chrome.offscreen.hasDocument();
    if (!has) {
      await chrome.offscreen.createDocument({
        url: 'offscreen.html',
        reasons: ['USER_MEDIA'],
        justification: 'Capture tab and microphone audio for local meeting transcription',
      });
    }
    /** @type {{ok: boolean, error?: string} | undefined} */
    const res = await chrome.runtime.sendMessage({
      type: 'mb-offscreen-start',
      streamId: msg.streamId,
      title: msg.title,
    });
    if (!res || !res.ok) {
      chrome.offscreen.closeDocument().catch(() => {});
    }
    return res || { ok: false, error: 'capture page did not respond' };
  } catch (e) {
    return { ok: false, error: errorMessage(e) };
  }
}
