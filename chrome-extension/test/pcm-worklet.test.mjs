// Unit tests for the extension's real audio encoder (pcm-worklet.js).
// The worklet runs in the browser's AudioWorklet scope, so we load the actual
// file with stubbed globals and exercise its process() method directly.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const dir = path.dirname(fileURLToPath(import.meta.url));
const source = readFileSync(path.join(dir, "..", "pcm-worklet.js"), "utf8");

function loadProcessor() {
  let captured;
  const sandbox = {
    AudioWorkletProcessor: class {
      constructor() {
        this.port = { postMessage() {} };
      }
    },
    registerProcessor: (_name, ctor) => {
      captured = ctor;
    },
    Int16Array,
    Math,
  };
  vm.createContext(sandbox);
  vm.runInContext(source, sandbox);
  return captured;
}

test("Float32 samples are scaled and clipped to Int16", () => {
  const Processor = loadProcessor();
  const proc = new Processor();
  const out = [];
  proc.port = { postMessage: (buf) => out.push(new Int16Array(buf)) };

  const frame = new Float32Array(2048); // exactly one flush (buffer is 2048)
  frame[0] = 1.0;
  frame[1] = -1.0;
  frame[2] = 0.0;
  frame[3] = 2.0; // out of range → clip to +1
  frame[4] = -2.0; // out of range → clip to -1
  proc.process([[frame]], [[new Float32Array(2048)]], {});

  assert.equal(out.length, 1, "one batch should be emitted at 2048 samples");
  const pcm = out[0];
  assert.equal(pcm.length, 2048);
  assert.equal(pcm[0], 32767);
  assert.equal(pcm[1], -32768);
  assert.equal(pcm[2], 0);
  assert.equal(pcm[3], 32767); // clipped
  assert.equal(pcm[4], -32768); // clipped
});

test("audio passes through to the output (user keeps hearing it)", () => {
  const Processor = loadProcessor();
  const proc = new Processor();
  proc.port = { postMessage() {} };
  const input = new Float32Array(128).fill(0.5);
  const output = new Float32Array(128);
  proc.process([[input]], [[output]], {});
  assert.ok(output.every((v) => Math.abs(v - 0.5) < 1e-6));
});

test("empty input does not throw and keeps the node alive", () => {
  const Processor = loadProcessor();
  const proc = new Processor();
  proc.port = { postMessage() {} };
  assert.equal(proc.process([[]], [[]], {}), true);
});

test("samples below the batch size are buffered, not dropped", () => {
  const Processor = loadProcessor();
  const proc = new Processor();
  let emitted = 0;
  proc.port = { postMessage: () => (emitted += 1) };
  proc.process([[new Float32Array(100)]], [[new Float32Array(100)]], {});
  assert.equal(emitted, 0, "100 < 2048 samples should not flush yet");
});
