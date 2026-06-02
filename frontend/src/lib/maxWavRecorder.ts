/**
 * Запись WAV через Web Audio API для MAX WebView.
 * MediaRecorder в миниаппе часто отдаёт пустой или битый blob; PCM→WAV стабильнее для серверного STT.
 */

const TARGET_SAMPLE_RATE = 48_000;

export class MaxWavRecorder {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private processor: ScriptProcessorNode | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private silentGain: GainNode | null = null;
  private buffers: Float32Array[] = [];
  private sampleRate = TARGET_SAMPLE_RATE;

  async start(): Promise<void> {
    this.buffers = [];
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });

    const Ctx = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) {
      throw new Error("audio_context_unsupported");
    }

    this.ctx = new Ctx({ sampleRate: TARGET_SAMPLE_RATE });
    if (this.ctx.state === "suspended") {
      await this.ctx.resume();
    }
    this.sampleRate = this.ctx.sampleRate;

    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.processor = this.ctx.createScriptProcessor(4096, 1, 1);
    this.silentGain = this.ctx.createGain();
    this.silentGain.gain.value = 0;

    this.processor.onaudioprocess = (ev) => {
      const channel = ev.inputBuffer.getChannelData(0);
      this.buffers.push(new Float32Array(channel));
    };

    this.source.connect(this.processor);
    this.processor.connect(this.silentGain);
    this.silentGain.connect(this.ctx.destination);
  }

  async stop(): Promise<Blob> {
    const samples = this.drainSamples();
    this.cleanup();
    if (samples.length === 0) {
      return new Blob([], { type: "audio/wav" });
    }
    const pcm = this.resampleToTarget(samples, this.sampleRate);
    return encodeWav(pcm, TARGET_SAMPLE_RATE);
  }

  abort(): void {
    this.cleanup();
  }

  private drainSamples(): Float32Array {
    let total = 0;
    for (const b of this.buffers) total += b.length;
    const merged = new Float32Array(total);
    let offset = 0;
    for (const b of this.buffers) {
      merged.set(b, offset);
      offset += b.length;
    }
    this.buffers = [];
    return merged;
  }

  private resampleToTarget(samples: Float32Array, fromRate: number): Float32Array {
    if (fromRate === TARGET_SAMPLE_RATE || fromRate <= 0) {
      return samples;
    }
    const ratio = TARGET_SAMPLE_RATE / fromRate;
    const outLen = Math.max(1, Math.round(samples.length * ratio));
    const out = new Float32Array(outLen);
    for (let i = 0; i < outLen; i++) {
      const srcPos = i / ratio;
      const idx = Math.floor(srcPos);
      const frac = srcPos - idx;
      const a = samples[idx] ?? 0;
      const b = samples[Math.min(idx + 1, samples.length - 1)] ?? a;
      out[i] = a + (b - a) * frac;
    }
    return out;
  }

  private cleanup(): void {
    try {
      this.processor?.disconnect();
      this.source?.disconnect();
      this.silentGain?.disconnect();
    } catch {
      /* ignore */
    }
    this.processor = null;
    this.source = null;
    this.silentGain = null;
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
    void this.ctx?.close();
    this.ctx = null;
  }
}

function encodeWav(samples: Float32Array, sampleRate: number): Blob {
  const numSamples = samples.length;
  const dataBytes = numSamples * 2;
  const buffer = new ArrayBuffer(44 + dataBytes);
  const view = new DataView(buffer);

  const writeStr = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataBytes, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeStr(36, "data");
  view.setUint32(40, dataBytes, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export function isMaxWavCaptureSupported(): boolean {
  if (typeof navigator === "undefined") return false;
  if (!navigator.mediaDevices?.getUserMedia) return false;
  const Ctx = window.AudioContext || (window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctx) return false;
  try {
    const probe = new Ctx();
    const supported = typeof probe.createScriptProcessor === "function";
    void probe.close();
    return supported;
  } catch {
    return false;
  }
}
