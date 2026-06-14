// Converts Float32 audio to Int16 PCM and ships ~128 ms batches to the page.
// Audio passthrough happens via this node's output (connect it to destination
// to keep hearing the tab; route through a muted gain for the mic).
class PcmSender extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buf = new Int16Array(2048);
    this.n = 0;
  }

  /**
   * @param {Float32Array[][]} inputs
   * @param {Float32Array[][]} outputs
   * @returns {boolean}
   */
  process(inputs, outputs) {
    const input = inputs[0];
    const output = outputs[0];
    if (input.length === 0) return true;
    const ch = input[0];
    if (output.length > 0) output[0].set(ch); // passthrough
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      this.buf[this.n++] = s < 0 ? s * 0x8000 : s * 0x7fff;
      if (this.n === this.buf.length) {
        const copy = this.buf.slice(0).buffer;
        this.port.postMessage(copy, [copy]);
        this.n = 0;
      }
    }
    return true;
  }
}

registerProcessor('pcm-sender', PcmSender);
