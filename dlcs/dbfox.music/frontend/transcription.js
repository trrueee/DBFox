import {
  BasicPitch,
  addPitchBendsToNoteEvents,
  noteFramesToTime,
  outputToNotesPoly,
} from "./vendor/basic-pitch.js";

const MODEL_SAMPLE_RATE = 22050;
const PITCH_CLASS_NAMES = ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"];
const MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
const MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];

async function resampleMono(audioBuffer) {
  const length = Math.max(1, Math.ceil(audioBuffer.duration * MODEL_SAMPLE_RATE));
  const context = new OfflineAudioContext(1, length, MODEL_SAMPLE_RATE);
  const sourceBuffer = context.createBuffer(1, audioBuffer.length, audioBuffer.sampleRate);
  const mixed = sourceBuffer.getChannelData(0);
  for (let channel = 0; channel < audioBuffer.numberOfChannels; channel += 1) {
    const input = audioBuffer.getChannelData(channel);
    for (let index = 0; index < input.length; index += 1) mixed[index] += input[index] / audioBuffer.numberOfChannels;
  }
  const source = context.createBufferSource();
  source.buffer = sourceBuffer;
  source.connect(context.destination);
  source.start();
  return context.startRendering();
}

function inferTempo(notes) {
  const onsets = [...new Set(notes.map((note) => Math.round(note.start_seconds * 100) / 100))].sort((a, b) => a - b);
  const intervals = [];
  for (let index = 1; index < onsets.length; index += 1) {
    const interval = onsets[index] - onsets[index - 1];
    if (interval >= 0.18 && interval <= 1.5) intervals.push(interval);
  }
  if (!intervals.length) return 76;
  let bestTempo = 76;
  let bestScore = -1;
  for (let tempo = 40; tempo <= 200; tempo += 1) {
    const beat = 60 / tempo;
    const score = intervals.reduce((sum, interval) => {
      const ratio = interval / beat;
      const nearest = Math.max(0.25, Math.round(ratio * 4) / 4);
      return sum + Math.exp(-Math.abs(ratio - nearest) * 8);
    }, 0);
    if (score > bestScore) {
      bestScore = score;
      bestTempo = tempo;
    }
  }
  return bestTempo;
}

function inferKey(notes) {
  const histogram = Array(12).fill(0);
  for (const note of notes) histogram[note.pitch % 12] += (note.end_seconds - note.start_seconds) * note.velocity;
  let best = { score: -Infinity, tonic: "C", mode: "major" };
  for (let tonic = 0; tonic < 12; tonic += 1) {
    for (const [mode, profile] of [["major", MAJOR_PROFILE], ["minor", MINOR_PROFILE]]) {
      const score = histogram.reduce((sum, value, pitchClass) => sum + value * profile[(pitchClass - tonic + 12) % 12], 0);
      if (score > best.score) best = { score, tonic: PITCH_CLASS_NAMES[tonic], mode };
    }
  }
  return { tonic: best.tonic, mode: best.mode };
}

function uncertainty(notes, duration) {
  const ranges = [];
  for (let start = 0; start < duration; start += 4) {
    const windowNotes = notes.filter((note) => note.start_seconds < start + 4 && note.end_seconds > start);
    if (!windowNotes.length) continue;
    const confidence = windowNotes.reduce((sum, note) => sum + note.confidence, 0) / windowNotes.length;
    const simultaneous = Math.max(...windowNotes.map((note) => windowNotes.filter((other) => other.start_seconds < note.end_seconds && other.end_seconds > note.start_seconds).length));
    if (confidence < 0.52 || simultaneous >= 8) {
      ranges.push({
        start_seconds: start,
        end_seconds: Math.min(duration, start + 4),
        confidence,
        reason: simultaneous >= 8 ? "dense_polyphony" : "low_note_confidence",
      });
    }
  }
  return ranges;
}

export async function transcribePiano(audioBuffer, onProgress) {
  const mono = await resampleMono(audioBuffer);
  const modelUrl = new URL("./vendor/basic-pitch-model/model.json", import.meta.url).href;
  const model = new BasicPitch(modelUrl);
  const frames = [];
  const onsets = [];
  const contours = [];
  await model.evaluateModel(mono, (frameBatch, onsetBatch, contourBatch) => {
    frames.push(...frameBatch);
    onsets.push(...onsetBatch);
    contours.push(...contourBatch);
  }, onProgress);
  const raw = noteFramesToTime(addPitchBendsToNoteEvents(
    contours,
    outputToNotesPoly(frames, onsets, 0.25, 0.25, 5, true, 4186.01, 27.5),
  ));
  const notes = raw
    .filter((note) => note.pitchMidi >= 21 && note.pitchMidi <= 108 && note.durationSeconds >= 0.04)
    .slice(0, 8192)
    .map((note) => ({
      start_seconds: Math.max(0, note.startTimeSeconds),
      end_seconds: Math.min(audioBuffer.duration, note.startTimeSeconds + note.durationSeconds),
      pitch: note.pitchMidi,
      velocity: Math.min(1, Math.max(0.01, note.amplitude)),
      confidence: Math.min(1, Math.max(0, note.amplitude)),
    }));
  const confidence = notes.length
    ? notes.reduce((sum, note) => sum + note.confidence, 0) / notes.length
    : 0;
  return {
    provider_id: "spotify.basic-pitch",
    provider_version: "1.0.1",
    tempo: inferTempo(notes),
    meter: { beats: 4, beat_unit: 4 },
    key: inferKey(notes),
    confidence,
    notes,
    uncertain_ranges: uncertainty(notes, audioBuffer.duration),
  };
}
