const askButton = document.getElementById('ask');
const result = document.getElementById('result');

if (askButton && result) {
  askButton.addEventListener('click', async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      result.textContent = '✓ Microphone enabled — you can close this tab and start recording.';
      result.style.color = '#2e7d32';
    } catch {
      result.textContent =
        '✗ Denied. Click the 🎤 icon in the address bar (or Site settings) to allow, then try again.';
      result.style.color = '#c62828';
    }
  });
}
