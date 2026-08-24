import { Accidental, Formatter, Renderer, Stave, StaveNote, Voice } from "./vendor/vexflow.js";

const NAMES = ["c", "c#", "d", "eb", "e", "f", "f#", "g", "ab", "a", "bb", "b"];

function pitchKey(pitch) {
  return `${NAMES[pitch % 12]}/${Math.floor(pitch / 12) - 1}`;
}

function durationName(duration) {
  if (duration >= 3.5) return "w";
  if (duration >= 1.75) return "h";
  if (duration >= 0.75) return "q";
  if (duration >= 0.375) return "8";
  return "16";
}

function restTickables(duration, clef) {
  const result = [];
  let remaining = Math.max(0, duration);
  for (const value of [4, 2, 1, 0.5, 0.25]) {
    while (remaining + 1e-6 >= value) {
      result.push(new StaveNote({
        clef,
        keys: [clef === "bass" ? "d/3" : "b/4"],
        duration: `${durationName(value)}r`,
      }));
      remaining -= value;
    }
  }
  return result;
}

function tickables(notes, clef, beatsPerMeasure) {
  const groups = new Map();
  for (const note of notes) {
    const key = `${note.beat.toFixed(4)}:${note.duration.toFixed(4)}`;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(note);
  }
  const result = [];
  let cursor = 0;
  for (const group of [...groups.values()].sort((a, b) => a[0].beat - b[0].beat)) {
    if (group[0].beat > cursor + 1e-6) result.push(...restTickables(group[0].beat - cursor, clef));
    const staveNote = new StaveNote({
      clef,
      keys: group.map((note) => pitchKey(note.pitch)),
      duration: durationName(group[0].duration),
    });
    group.forEach((note, index) => {
      if ([1, 3, 6, 8, 10].includes(note.pitch % 12)) staveNote.addModifier(new Accidental(NAMES[note.pitch % 12].slice(1)), index);
    });
    result.push(staveNote);
    cursor = Math.max(cursor, group[0].beat + group[0].duration);
  }
  if (cursor < beatsPerMeasure - 1e-6) result.push(...restTickables(beatsPerMeasure - cursor, clef));
  return result;
}

export function renderMeasure(container, document, measure) {
  container.replaceChildren();
  const width = Math.max(250, container.clientWidth || 300);
  const renderer = new Renderer(container, Renderer.Backends.SVG);
  renderer.resize(width, 204);
  const context = renderer.getContext();
  const treble = new Stave(8, 28, width - 16);
  const bass = new Stave(8, 108, width - 16);
  if (measure === 1) {
    treble.addClef("treble").addKeySignature(document.key.tonic + (document.key.mode === "minor" ? "m" : ""));
    bass.addClef("bass").addKeySignature(document.key.tonic + (document.key.mode === "minor" ? "m" : ""));
    treble.addTimeSignature(`${document.meter.beats}/${document.meter.beat_unit}`);
    bass.addTimeSignature(`${document.meter.beats}/${document.meter.beat_unit}`);
  }
  treble.setContext(context).draw();
  bass.setContext(context).draw();
  const harmony = (document.harmony || []).filter((event) => event.measure === measure);
  if (harmony.length) {
    context.save();
    context.setFont("Inter, system-ui, sans-serif", 12, "500");
    context.setFillStyle("currentColor");
    for (const event of harmony) {
      const left = measure === 1 ? 82 : 28;
      const usable = width - left - 24;
      context.fillText(event.symbol, left + usable * (event.beat / document.meter.beats), 20);
    }
    context.restore();
  }
  for (const [hand, stave, clef] of [["right", treble, "treble"], ["left", bass, "bass"]]) {
    const notes = tickables(
      document.notes.filter((note) => note.measure === measure && note.hand === hand),
      clef,
      document.meter.beats,
    );
    if (!notes.length) continue;
    const voice = new Voice({ numBeats: document.meter.beats, beatValue: document.meter.beat_unit }).setMode(Voice.Mode.SOFT);
    voice.addTickables(notes);
    new Formatter().joinVoices([voice]).format([voice], width - (measure === 1 ? 105 : 48));
    voice.draw(context, stave);
  }
}
