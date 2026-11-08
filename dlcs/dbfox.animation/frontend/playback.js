import { AnimationMixer, AnimationClip, NumberKeyframeTrack, Object3D, LoopOnce, LinearInterpolant, DiscreteInterpolant, BezierInterpolant } from "./vendor/three.js";

// Domain-to-engine boundary: interval choice is ours; interpolation mathematics is Three's.
// AnimationMixer writes resultBuffer after factory creation, so every native interpolant
// receives that buffer at evaluation. No canonical state is serialized from Three.
export function curveTrack(name, keys, curves) {
  const times = new Float64Array(keys.map((key) => key.tick / 1000));
  const values = new Float64Array(keys.map((key) => key.value));
  const modes = keys.map((key) => curves.get(key.curve_id) || { kind: "linear" });
  const incoming = new Float64Array(keys.length * 2), outgoing = new Float64Array(keys.length * 2);
  for (let i = 0; i < keys.length; i++) {
    incoming.set([times[i], values[i]], i * 2); outgoing.set([times[i], values[i]], i * 2);
  }
  for (let i = 0; i < keys.length; i++) {
    if (i + 1 < keys.length) {
      const curve = modes[i], dt = times[i + 1] - times[i], dv = values[i + 1] - values[i];
      outgoing.set([times[i] + dt * (curve.x1 ?? 1 / 3), values[i] + dv * (curve.y1 ?? 1 / 3)], i * 2);
      incoming.set([times[i] + dt * (curve.x2 ?? 2 / 3), values[i] + dv * (curve.y2 ?? 2 / 3)], (i + 1) * 2);
    }
  }
  // Preserve millisecond resolution and finite scalar precision at long durations.
  const track = new NumberKeyframeTrack(name, times, values);
  track.times = times; track.values = values;
  track.createInterpolant = (buffer) => {
    const variants = { linear: new LinearInterpolant(times, values, 1, buffer), hold: new DiscreteInterpolant(times, values, 1, buffer), bezier: new BezierInterpolant(times, values, 1, buffer) };
    variants.bezier.inTangents = incoming; variants.bezier.outTangents = outgoing;
    return { parameterPositions: times, sampleValues: values, resultBuffer: buffer, settings: null,
      evaluate(time) {
        let lo = 0, hi = times.length;
        while (lo < hi) { const mid = (lo + hi) >>> 1; if (times[mid] <= time) lo = mid + 1; else hi = mid; }
        const index = Math.max(0, Math.min(times.length - 1, lo - 1));
        const native = variants[modes[index].kind];
        if (this.resultBuffer) native.resultBuffer = this.resultBuffer;
        return native.evaluate(time);
      },
    };
  };
  return track;
}

export function createPlayback(document, clipId = null) {
  const root = new Object3D(), targets = new Map(), curves = new Map(document.curves.map((curve) => [curve.id, curve]));
  for (const target of document.targets) {
    const object = new Object3D(); object.name = `target${targets.size}`;
    object.position.fromArray(target.position); object.rotation.set(...target.rotation); object.scale.fromArray(target.scale);
    root.add(object); targets.set(target.id, object);
  }
  const clip = clipId ? document.clips.find((value) => value.id === clipId) : null;
  if (clipId && !clip) throw new Error("Clip no longer exists");
  const grouped = new Map();
  for (const key of document.keyframes) { if (!grouped.has(key.track_id)) grouped.set(key.track_id, []); grouped.get(key.track_id).push(key); }
  const tracks = [];
  for (const track of document.tracks) {
    if (!track.enabled || (clip && !clip.track_ids.includes(track.id))) continue;
    const keys = grouped.get(track.id)?.sort((a, b) => a.tick - b.tick);
    if (!keys?.length) continue;
    const object = targets.get(track.target_id);
    const [property, axis] = track.property.split(".");
    if (!object || !["position", "rotation", "scale"].includes(property) || !["x", "y", "z"].includes(axis)) throw new Error("Invalid animation binding");
    tracks.push(curveTrack(`${object.name}.${property}[${axis}]`, keys, curves));
  }
  const animation = new AnimationClip("animation", document.timing.duration / 1000, tracks);
  const mixer = new AnimationMixer(root), action = mixer.clipAction(animation);
  action.setLoop(LoopOnce, 1); action.clampWhenFinished = true; action.play();
  const start = clip?.start ?? 0, end = clip?.end ?? document.timing.duration;
  let disposed = false;
  return { root, targets, start, end,
    seek(tick) { if (disposed) return; action.paused = false; mixer.timeScale = 1; mixer.setTime(Math.max(start, Math.min(end, tick)) / 1000); },
    dispose() { if (disposed) return; disposed = true; mixer.stopAllAction(); mixer.uncacheRoot(root); root.clear(); targets.clear(); },
  };
}

// Explicit seeks are silent. Playback crossings use (previous, next], including a
// loop's starting marker once; callers retain neither marker events nor playback state.
export function advance(previous, elapsed, start, end, loop, markers) {
  const distance = Math.max(0, elapsed), length = end - start;
  if (length <= 0) throw new Error("Invalid playback window");
  const raw = previous + distance;
  const loops = loop ? Math.max(0, Math.floor((raw - start) / length)) : 0;
  const tick = loop ? start + ((raw - start) % length) : Math.min(end, raw);
  const crossed = markers.filter((marker) => marker.tick >= start && marker.tick <= end &&
    (loops ? marker.tick > previous || marker.tick <= tick || loops > 1 : marker.tick > previous && marker.tick <= tick));
  return { tick, ended: !loop && raw >= end, crossed: crossed.map((marker) => marker.id), loops };
}
