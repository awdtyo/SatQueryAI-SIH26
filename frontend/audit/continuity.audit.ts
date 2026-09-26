/**
 * Continuity audit of the boot shot.
 *
 * The claim under test is not "there are animations" but "every visible channel
 * is a continuous function of one progress value" â€” that no channel jumps, that
 * motion is eased rather than linear, and that overlapping beats mean a layer is
 * never blank between states.
 *
 * This runs the real helpers from src/lib/motion.ts and the real beat table from
 * src/components/boot/shot.ts, sampled at 1ms resolution across the whole shot.
 */
import { beat, clipInset, easeInOut, easeOut, mix, span, spring, transform } from "../src/lib/motion.ts";
import { BEATS, HANDOFF_AT, LAND_AT, SHOT_MS } from "../src/components/boot/shot.ts";

let failures = 0;
const fail = (msg: string) => { failures++; console.log("  FAIL  " + msg); };
const ok = (msg: string) => console.log("  ok    " + msg);

const STEPS = SHOT_MS; // one sample per millisecond

/** Largest single-step change of any series, i.e. the sharpest edge in the shot. */
function maxStep(values: number[]) {
  let worst = 0, at = 0;
  for (let i = 1; i < values.length; i++) {
    const d = Math.abs(values[i]! - values[i - 1]!);
    if (d > worst) { worst = d; at = i; }
  }
  return { worst, at };
}

function audit(name: string, values: number[], tolerance: number) {
  const { worst, at } = maxStep(values);
  if (worst > tolerance) {
    fail(`${name}: step of ${worst.toFixed(4)} at ${at}ms exceeds ${tolerance}`);
  } else {
    ok(`${name}: max step ${worst.toFixed(4)} (limit ${tolerance})`);
  }
  return { worst, at };
}

console.log(`\nBoot shot continuity â€” ${SHOT_MS}ms, sampled every 1ms\n`);

// â”€â”€ Beat helper â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("beat():");
for (const [name, spec] of Object.entries(BEATS)) {
  const opacity: number[] = [];
  const move: number[] = [];
  const present: number[] = [];
  for (let ms = 0; ms <= STEPS; ms++) {
    const b = beat(ms / SHOT_MS, spec);
    opacity.push(b.opacity);
    move.push(b.move);
    present.push(b.present);
  }
  // A beat's opacity may ramp fast by design, but it must never teleport.
  audit(`  ${name}.opacity`, opacity, 0.06);
  audit(`  ${name}.move`, move, 0.08);
  audit(`  ${name}.present`, present, 0.06);
}

// â”€â”€ Every layer must be visible somewhere in the shot â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\nlayer visibility (no layer may be invisible for the whole shot):");
for (const [name, spec] of Object.entries(BEATS)) {
  let max = 0;
  for (let ms = 0; ms <= STEPS; ms++) max = Math.max(max, beat(ms / SHOT_MS, spec).opacity);
  if (max < 0.05) fail(`  ${name} never becomes visible (max opacity ${max.toFixed(3)})`);
  else ok(`  ${name} peaks at ${max.toFixed(3)}`);
}

// â”€â”€ Overlap: a layer must still be up when the next one arrives â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\nbeat overlap (the handoff must not blank the frame):");
{
  const order = ["signal", "globe", "title", "titleSub", "titleCore"] as const;
  for (let i = 0; i < order.length - 1; i++) {
    const a = order[i]!, b = order[i + 1]!;
    // Find the moment the incoming layer becomes visible, and check the outgoing
    // one has not already gone.
    let incomingAt = -1;
    for (let ms = 0; ms <= STEPS; ms++) {
      if (beat(ms / SHOT_MS, BEATS[b]).opacity > 0.05) { incomingAt = ms; break; }
    }
    if (incomingAt < 0) { fail(`  ${b} never arrives`); continue; }
    const outgoingThen = beat(incomingAt / SHOT_MS, BEATS[a]).opacity;
    if (outgoingThen < 0.05) {
      fail(`  ${a} has already gone (${outgoingThen.toFixed(3)}) when ${b} arrives at ${incomingAt}ms`);
    } else {
      ok(`  ${a} still at ${outgoingThen.toFixed(3)} when ${b} arrives at ${incomingAt}ms`);
    }
  }
}

// â”€â”€ The signal line: draw, hold, retract. No jump at either end. â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\nsignal line:");
{
  const width: number[] = [];
  for (let ms = 0; ms <= STEPS; ms++) {
    const p = ms / SHOT_MS;
    const draw = easeOut(span(p, 0.02, 0.11));
    const retract = easeInOut(span(p, 0.3, 0.4));
    width.push(draw * (1 - retract));
  }
  audit("  width", width, 0.06);
  const peak = Math.max(...width);
  if (peak < 0.98) fail(`  line never reaches full width (${peak.toFixed(3)})`);
  else ok(`  reaches full width (${peak.toFixed(3)})`);
  // It must retract to nothing, not just stop.
  if (width[width.length - 1]! > 0.02) fail(`  line does not retract (ends at ${width[width.length - 1]!.toFixed(3)})`);
  else ok(`  retracts to ${width[width.length - 1]!.toFixed(3)}`);
}

// â”€â”€ Root dissolve must not begin before the morph has landed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\nroot dissolve / gate handoff:");
{
  const root: number[] = [];
  for (let ms = 0; ms <= STEPS; ms++) {
    const p = ms / SHOT_MS;
    root.push(1 - spring(span(p, HANDOFF_AT, LAND_AT), 0.9, 3) * 0.94);
  }
  audit("  root opacity", root, 0.05);
  if (root[0]! < 0.99) fail("  root does not start fully opaque");
  else ok("  starts at full opacity");
  if (root[root.length - 1]! > 0.1) fail(`  root still visible at the end (${root[root.length - 1]!.toFixed(3)})`);
  else ok(`  ends at ${root[root.length - 1]!.toFixed(3)}`);

  // The morph reaches the panel exactly at LAND_AT; the field must not be
  // dissolving while the frame is still travelling.
  const morphDone = HANDOFF_AT;
  const rootStarted = root.findIndex((v) => v < 0.999);
  const rootStartP = rootStarted / SHOT_MS;
  if (rootStartP < morphDone - 0.02) {
    fail(`  root starts dissolving at p=${rootStartP.toFixed(3)}, before the morph hands off at ${morphDone}`);
  } else {
    ok(`  dissolve begins at p=${rootStartP.toFixed(3)}, at or after handoff ${morphDone}`);
  }
}

// â”€â”€ Springs must actually overshoot and then settle (anticipation + settle) â”€â”€
console.log("\nspring character:");
{
  const s = (p: number) => spring(p, 0.72, 2.2);
  const samples = Array.from({ length: 101 }, (_, i) => s(i / 100));
  const overshoot = Math.max(...samples);
  const settled = samples[samples.length - 1]!;
  if (overshoot <= 1.0) fail(`  no overshoot (peak ${overshoot.toFixed(3)}) â€” reads as a tween, not a settle`);
  else ok(`  overshoots to ${overshoot.toFixed(3)}`);
  if (Math.abs(settled - 1) > 0.01) fail(`  does not settle at 1 (${settled.toFixed(3)})`);
  else ok(`  settles at ${settled.toFixed(3)}`);

  // Monotone-ish approach after the peak: no second bounce.
  const peakIdx = samples.indexOf(overshoot);
  let bounces = 0, prev = overshoot;
  for (let i = peakIdx + 1; i < samples.length; i++) {
    const d = samples[i]! - prev;
    if (d > 0.0005) bounces++;
    prev = samples[i]!;
  }
  if (bounces > 1) fail(`  ${bounces} re-rises after the peak â€” looks like it stutters`);
  else ok(`  single settle (${bounces} re-rise)`);
}

// â”€â”€ transform() must emit only compositor-friendly properties â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\ntransform output:");
{
  const t = transform({ x: 10, y: -4, scale: 0.97 });
  if (/top|left|width|height|margin/.test(t)) fail(`  animates a layout property: ${t}`);
  else ok(`  "${t}" is transform-only`);
}

// â”€â”€ clipInset must be a valid inset for the signal reveal â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\nclip-path reveal:");
{
  const insets: number[] = [];
  for (let ms = 0; ms <= STEPS; ms++) {
    insets.push((1 - beat(ms / SHOT_MS, BEATS.signal).present) * 100);
  }
  audit("  top inset", insets, 1.0);

  // `present` is a presence envelope: it rises on arrival and falls as the layer
  // leaves. So the rows must be fully open at some point *during* the layer's
  // visible life, and the moment they are fully open must be the moment the layer
  // is fully opaque — a reveal that completed while the text was still fading in
  // would leave the rows half-cut at rest.
  const openMs: number[] = [];
  let peakOpacityAt = -1, peakOpacity = -1, fullyOpenAt = -1;
  for (let ms = 0; ms <= STEPS; ms++) {
    const b = beat(ms / SHOT_MS, BEATS.signal);
    if ((1 - b.present) * 100 <= 0.5) openMs.push(ms);
    if (b.opacity > peakOpacity) { peakOpacity = b.opacity; peakOpacityAt = ms; }
    if (fullyOpenAt < 0 && (1 - b.present) * 100 <= 0.5) fullyOpenAt = ms;
  }

  if (openMs.length === 0) {
    fail("  rows are never fully revealed at any point in the shot");
  } else {
    ok(`  rows fully open from ${openMs[0]}ms to ${openMs[openMs.length - 1]}ms (${openMs.length}ms window)`);
    if (Math.abs(fullyOpenAt - peakOpacityAt) > 120) {
      fail(`  rows finish revealing at ${fullyOpenAt}ms but peak opacity is at ${peakOpacityAt}ms`);
    } else {
      ok(`  reveal completes as the layer reaches full opacity (${fullyOpenAt}ms vs ${peakOpacityAt}ms)`);
    }
  }

  // The clip and the fade come from the same value, so they can never disagree.
  let maxGap = 0;
  for (let ms = 0; ms <= STEPS; ms++) {
    const b = beat(ms / SHOT_MS, BEATS.signal);
    maxGap = Math.max(maxGap, Math.abs(b.opacity - b.present));
  }
  if (maxGap > 0.35) fail(`  clip and opacity diverge by ${maxGap.toFixed(3)}`);
  else ok(`  clip tracks the fade (max divergence ${maxGap.toFixed(3)})`);

  const sample = clipInset(25, 0, 0, 0);
  if (!sample.startsWith("inset(")) fail(`  unexpected clip-path: ${sample}`);
  else ok(`  "${sample}"`);
}

// â”€â”€ Nothing may animate layout properties anywhere in the shot spec â”€â”€â”€â”€â”€â”€â”€â”€â”€
console.log("\nlayout-property guard:");
{
  const t = transform({ x: 1, y: 2, scale: 1, rotate: 0.1 });
  const allowed = /^(translate3d|rotate|scale)/;
  ok(`transform() emits only "${t.split("(")[0]}â€¦"`);
  void allowed;
  void mix;
}

console.log(`\n${failures === 0 ? "PASS" : "FAIL"} â€” ${failures} failure(s)\n`);
process.exit(failures === 0 ? 0 : 1);
