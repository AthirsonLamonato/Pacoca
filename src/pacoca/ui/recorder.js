// Runs on the browser audio thread. Capture stays on this computer.
class PacocaCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.pending = [];
    this.phase = 0;
    this.sum = 0;
    this.count = 0;
  }
  process(inputs) {
    const input = inputs[0]?.[0];
    if (!input) return true;
    const ratio = sampleRate / 16000;
    for (const sample of input) {
      this.sum += sample;
      this.count++;
      this.phase++;
      if (this.phase >= ratio) {
        this.pending.push(this.sum / this.count);
        this.phase -= ratio;
        this.sum = 0;
        this.count = 0;
      }
    }
    if (this.pending.length >= 512) {
      const data = new Float32Array(this.pending.splice(0, 512));
      this.port.postMessage(data, [data.buffer]);
    }
    return true;
  }
}
registerProcessor("pacoca-capture", PacocaCapture);
