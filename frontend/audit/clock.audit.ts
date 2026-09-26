/**
 * Clock audit.
 *
 * The boot's continuity rests on this loop reaching exactly 1, firing onEnd
 * exactly once, and behaving sanely when the tab is hidden or the shot is
 * cancelled. Headless browsers cannot drive it (their rAF is not tied to the
 * wall clock the loop reads), so it is driven here with a controlled frame
 * source and a controlled clock.
 *
 * The motion helpers are installed as globals *before* importing motion.ts, so
 * the module under test is the real one, unmodified.
 */

// ── Controlled environment ──────────────────────────────────────────────────
let now = 0;
let rafId = 0;
let queue: Array<(t: number) => void> = [];

type Listener = () => void;
const listeners = new Map<string, Listener[]>();
const doc = {
  hidden: false,
  addEventListener(type: string, fn: Listener) {
    const list = listeners.get(type) ?? [];
    list.push(fn);
    listeners.set(type, list);
  },
  removeEventListener(type: string, fn: Listener) {
    const list = listeners.get(type) ?? [];
    listeners.set(type, list.filter((f) => f !== fn));
  },
  dispatch(type: string) {
    for (const fn of [...(listeners.get(type) ?? [])]) fn();
  },
};

interface FakeGlobals {
  performance: { now: () => number };
  requestAnimationFrame: (cb: (t: number) => void) => number;
  cancelAnimationFrame: () => void;
  document: typeof doc;
}

const fake = globalThis as unknown as FakeGlobals;
fake.performance = { now: () => now };
fake.requestAnimationFrame = (cb) => {
  queue.push(cb);
  return ++rafId;
};
fake.cancelAnimationFrame = () => {
  queue = [];
};
fake.document = doc;

const { runClock } = await import("../src/lib/motion.ts");

/** Advance time and deliver one frame, as a browser would. */
function frame(advanceMs: number) {
  now += advanceMs;
  const pending = queue;
  queue = [];
  for (const cb of pending) cb(now);
}

let failures = 0;
const fail = (m: string) => { failures++; console.log("  FAIL  " + m); };
const ok = (m: string) => console.log("  ok    " + m);

const DURATION = 4200;

console.log(`\nClock audit — duration ${DURATION}ms, 60fps\n`);

// ── A normal run reaches exactly 1, once ────────────────────────────────────
console.log("normal run:");
{
  const seen: number[] = [];
  let ends = 0;
  const stop = runClock(DURATION, {
    onFrame: (p) => seen.push(p),
    onEnd: () => ends++,
  });

  let guard = 0;
  while (ends === 0 && guard++ < 2000) frame(1000 / 60);
  stop();

  if (ends !== 1) fail(`onEnd fired ${ends} times, expected exactly 1`);
  else ok("onEnd fires exactly once");

  if (seen[seen.length - 1] !== 1) fail(`final position is ${seen[seen.length - 1]}, expected exactly 1`);
  else ok("final position is exactly 1");

  let monotonic = true, worstBack = 0;
  for (let i = 1; i < seen.length; i++) {
    const d = seen[i]! - seen[i - 1]!;
    if (d < 0) monotonic = false;
    worstBack = Math.max(worstBack, -d);
  }
  if (!monotonic) fail(`position went backwards by up to ${worstBack.toFixed(4)}`);
  else ok(`position is monotonic over ${seen.length} frames`);

  // ~1 frame per 16.7ms; allow slack for the first/last partial frame.
  const expected = Math.round(DURATION / (1000 / 60));
  if (Math.abs(seen.length - expected) > 2) fail(`${seen.length} frames, expected ~${expected}`);
  else ok(`${seen.length} frames (expected ~${expected})`);

  if (seen[0]! <= 0) fail(`first frame position is ${seen[0]}, expected > 0`);
  else ok(`first frame is already in motion (p=${seen[0]!.toFixed(4)})`);

  // No frame should jump more than a couple of ms worth of progress.
  const maxStep = Math.max(...seen.slice(1).map((v, i) => v - seen[i]!));
  const stepLimit = 2 / (1000 / 60);
  if (maxStep > stepLimit) fail(`largest single-frame step ${maxStep.toFixed(5)} exceeds ${stepLimit.toFixed(5)}`);
  else ok(`largest single-frame step ${maxStep.toFixed(5)} (limit ${stepLimit.toFixed(5)})`);
}

// ── Reduced motion resolves without asking for a frame ──────────────────────
console.log("\ninstant (reduced motion):");
{
  queue = [];
  now = 0;
  let frames = 0, ends = 0, lastP = -1;
  const stop = runClock(DURATION, {
    instant: true,
    onFrame: (p) => { frames++; lastP = p; },
    onEnd: () => ends++,
  });

  if (frames !== 1) fail(`called onFrame ${frames} times, expected 1`);
  else ok("onFrame called once");
  if (lastP !== 1) fail(`onFrame received ${lastP}, expected 1`);
  else ok("onFrame received the end state");
  if (ends !== 1) fail(`onEnd fired ${ends} times, expected 1`);
  else ok("onEnd fired once");
  if (queue.length !== 0) fail(`requested ${queue.length} frames, expected none`);
  else ok("no animation frames requested");
  stop();
}

// ── Cancelling stops everything ────────────────────────────────────────────
console.log("\ncancellation:");
{
  queue = [];
  now = 0;
  let ends = 0, frames = 0;
  const stop = runClock(DURATION, { onFrame: () => frames++, onEnd: () => ends++ });
  frame(16);
  const atCancel = frames;
  stop();
  for (let i = 0; i < 500; i++) frame(16);
  if (ends !== 0) fail(`onEnd fired after cancel (${ends})`);
  else ok("onEnd does not fire after cancel");
  if (frames !== atCancel) fail(`${frames - atCancel} frames ran after cancel`);
  else ok("no frames are delivered after cancel");
}

// ── A hidden tab must not stall the shot for ever ───────────────────────────
console.log("\nhidden tab:");
{
  queue = [];
  now = 0;
  const seen: number[] = [];
  let ends = 0;
  const stop = runClock(DURATION, { onFrame: (p) => seen.push(p), onEnd: () => ends++ });

  for (let i = 0; i < 30; i++) frame(16); // ~half a second in
  const beforeHide = seen[seen.length - 1]!;

  // Hidden: the browser stops delivering frames entirely.
  doc.hidden = true;
  doc.dispatch("visibilitychange");
  queue = [];
  now += 10_000; // ten seconds pass with nothing drawn
  for (let i = 0; i < 50; i++) frame(16);

  doc.hidden = false;
  doc.dispatch("visibilitychange");
  for (let i = 0; i < 400 && ends === 0; i++) frame(16);
  stop();

  if (ends !== 1) fail(`onEnd fired ${ends} times after resuming, expected 1`);
  else ok("shot completes on resume rather than stalling");
  if (beforeHide >= 1) fail("shot already finished before hiding");
  else ok(`hid mid-shot at p=${beforeHide.toFixed(3)}`);
  const last = seen[seen.length - 1]!;
  if (last !== 1) fail(`resumed to p=${last}, expected exactly 1`);
  else ok("resumes to exactly 1");
}

console.log(`\n${failures === 0 ? "PASS" : "FAIL"} — ${failures} failure(s)\n`);
process.exit(failures === 0 ? 0 : 1);
