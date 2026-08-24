export function getAudioContext() {
  return new AudioContext();
}

const SAMPLE_PITCHES = [21];
for (let octave = 1; octave <= 7; octave += 1) {
  for (const pitchClass of [0, 3, 6, 9]) SAMPLE_PITCHES.push((octave + 1) * 12 + pitchClass);
}
SAMPLE_PITCHES.push(108);

function sampleName(pitch) {
  const pitchClass = pitch % 12;
  const octave = Math.floor(pitch / 12) - 1;
  return `${({ 0: "C", 3: "Ds", 6: "Fs", 9: "A" })[pitchClass]}${octave}v8.mp3`;
}

function nearestSample(pitch) {
  return SAMPLE_PITCHES.reduce((nearest, candidate) => (
    Math.abs(candidate - pitch) < Math.abs(nearest - pitch) ? candidate : nearest
  ), SAMPLE_PITCHES[0]);
}

export class PianoSampler {
  constructor(context) {
    this.context = context;
    this.buffers = new Map();
  }

  async buffer(pitch) {
    const samplePitch = nearestSample(pitch);
    if (this.buffers.has(samplePitch)) return this.buffers.get(samplePitch);
    const url = new URL(`./vendor/piano/${sampleName(samplePitch)}`, import.meta.url);
    const data = await fetch(url).then((response) => {
      if (!response.ok) throw new Error("钢琴音色资源不可用。");
      return response.arrayBuffer();
    });
    const decoded = await this.context.decodeAudioData(data);
    this.buffers.set(samplePitch, decoded);
    return decoded;
  }

  async play(pitch, velocity = 0.72, duration = 1, when = this.context.currentTime) {
    const audio = await this.buffer(pitch);
    const source = this.context.createBufferSource();
    const gain = this.context.createGain();
    source.buffer = audio;
    source.playbackRate.setValueAtTime(2 ** ((pitch - nearestSample(pitch)) / 12), when);
    gain.gain.setValueAtTime(Math.max(0.01, velocity) * 0.65, when);
    gain.gain.setValueAtTime(Math.max(0.01, velocity) * 0.55, when + Math.min(duration * 0.65, 0.5));
    gain.gain.exponentialRampToValueAtTime(0.001, when + Math.max(0.12, duration));
    source.connect(gain).connect(this.context.destination);
    source.start(when);
    source.stop(when + Math.max(0.14, duration + 0.05));
    return source;
  }
}

export function scoreEvents(document) {
  const secondsPerBeat = 60 / document.tempo;
  return document.notes.map((note) => ({
    ...note,
    start: ((note.measure - 1) * document.meter.beats + note.beat) * secondsPerBeat,
    durationSeconds: note.duration * secondsPerBeat,
  })).sort((a, b) => a.start - b.start || a.pitch - b.pitch);
}

export async function playScore(document, { from = 0, onPosition, onNotes, signal }) {
  const context = getAudioContext();
  await context.resume();
  const sampler = new PianoSampler(context);
  const events = scoreEvents(document).filter((event) => event.start + event.durationSeconds >= from);
  await Promise.all([...new Set(events.map((event) => event.pitch))].map((pitch) => sampler.buffer(pitch)));
  const origin = context.currentTime + 0.04 - from;
  for (const event of events) {
    if (signal.aborted) break;
    await sampler.play(event.pitch, event.velocity, event.durationSeconds, origin + event.start);
  }
  return new Promise((resolve) => {
    const tick = () => {
      if (signal.aborted) {
        context.close();
        resolve();
        return;
      }
      const position = context.currentTime - origin;
      const active = events.filter((event) => event.start <= position && event.start + event.durationSeconds > position).map((event) => event.pitch);
      onPosition(position);
      onNotes(active);
      const total = document.measure_count * document.meter.beats * 60 / document.tempo;
      if (position >= total) {
        context.close();
        resolve();
      } else requestAnimationFrame(tick);
    };
    tick();
  });
}

export async function previewPitch(pitch, velocity = 0.72) {
  const context = getAudioContext();
  await context.resume();
  const sampler = new PianoSampler(context);
  await sampler.play(pitch, velocity, 1.2);
  setTimeout(() => void context.close(), 1500);
}

export async function playTimedNotes(notes, { from = 0, onPosition, onNotes, signal }) {
  const context = getAudioContext();
  await context.resume();
  const sampler = new PianoSampler(context);
  const selected = notes.filter((note) => note.end_seconds >= from);
  await Promise.all([...new Set(selected.map((note) => note.pitch))].map((pitch) => sampler.buffer(pitch)));
  const origin = context.currentTime + 0.04 - from;
  for (const note of selected) {
    if (signal.aborted) break;
    await sampler.play(note.pitch, note.velocity, note.end_seconds - note.start_seconds, origin + note.start_seconds);
  }
  return new Promise((resolve) => {
    const tick = () => {
      if (signal.aborted) {
        void context.close();
        resolve();
        return;
      }
      const position = context.currentTime - origin;
      onPosition(position);
      onNotes(selected.filter((note) => note.start_seconds <= position && note.end_seconds > position).map((note) => note.pitch));
      if (position >= Math.max(0, ...selected.map((note) => note.end_seconds))) {
        void context.close();
        resolve();
      } else requestAnimationFrame(tick);
    };
    tick();
  });
}
