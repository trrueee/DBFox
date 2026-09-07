import test from "node:test";
import assert from "node:assert/strict";
import { createPlayback, curveTrack, advance } from "../frontend/playback.js";

const document = { timing: { duration: 3600000 }, targets: [{ id: "object", position: [0,0,0], rotation: [0,0,0], scale: [1,1,1] }], tracks: [{ id: "track", target_id: "object", property: "position.x", enabled: true }], keyframes: [{ id:"a",track_id:"track",tick:3599999,value:1 }, { id:"b",track_id:"track",tick:3600000,value:2 }], curves: [], clips: [] };
test("one millisecond keys at one hour survive Mixer and replay", () => {
  const playback = createPlayback(document);
  playback.seek(3599999); assert.equal(playback.targets.get("object").position.x, 1);
  playback.seek(3600000); assert.equal(playback.targets.get("object").position.x, 2);
  playback.seek(3599999); assert.equal(playback.targets.get("object").position.x, 1);
  playback.dispose(); playback.dispose(); assert.equal(playback.targets.size, 0);
});
test("mixed native curves and exact key boundary", () => {
  const curves = new Map([["hold",{kind:"hold"}], ["bezier",{kind:"bezier",x1:.25,y1:0,x2:.75,y2:0}]]);
  const track = curveTrack(".position[x]", [{tick:0,value:0,curve_id:"hold"},{tick:1000,value:1,curve_id:"bezier"},{tick:2000,value:2}], curves);
  const interpolant = track.createInterpolant(new Float64Array(1));
  assert.equal(interpolant.evaluate(.999)[0],0); assert.equal(interpolant.evaluate(1)[0],1);
  assert.equal(interpolant.evaluate(1.5)[0],1.125); assert.equal(interpolant.evaluate(2)[0],2);
});
test("clip trimming preserves the complete curve and endpoint value", () => {
  const d = structuredClone(document); d.timing.duration=2000; d.keyframes=[{id:"a",track_id:"track",tick:0,value:0,curve_id:"curve"},{id:"b",track_id:"track",tick:2000,value:2}];
  d.curves=[{id:"curve",kind:"bezier",x1:.25,y1:0,x2:.75,y2:0}]; d.clips=[{id:"clip",track_ids:["track"],start:500,end:1500}];
  const full=createPlayback(d), trimmed=createPlayback(d,"clip");
  for(const tick of [500,750,1000,1250,1500,500]) { full.seek(tick); trimmed.seek(tick); assert.equal(trimmed.targets.get("object").position.x,full.targets.get("object").position.x); }
  full.dispose();trimmed.dispose();
});
test("twenty thousand keys and ten thousand seeks remain bounded", () => {
  const keys=Array.from({length:20000},(_,i)=>({tick:i,value:i*2}));
  const track=curveTrack(".position[x]",keys,new Map()), interpolant=track.createInterpolant(new Float64Array(1));
  const start=performance.now();
  for(let i=0;i<10000;i++){const tick=(i*7919)%19999+.5; assert.ok(Math.abs(interpolant.evaluate(tick/1000)[0]-tick*2)<1e-7);}
  assert.ok(performance.now()-start<5000,"CPU scalar probe exceeded 5 seconds");
});
test("marker crossing is bounded and seek remains separate",()=>{
  const markers=[{id:"start",tick:0},{id:"mid",tick:50},{id:"end",tick:100}];
  assert.deepEqual(advance(40,20,0,100,false,markers).crossed,["mid"]);
  assert.deepEqual(advance(90,20,0,100,true,markers).crossed,["start","end"]);
  assert.equal(advance(90,20,0,100,false,markers).ended,true);
});
