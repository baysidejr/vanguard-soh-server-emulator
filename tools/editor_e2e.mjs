// Drive the content editor page in headless Microsoft Edge over the DevTools protocol (no
// packages: Node 22+ has fetch and WebSocket built in). Used by server/test_systems.py
// EditorSaveTests, and by hand:
//
//     node tools/editor_e2e.mjs <url> <steps.json>
//
// steps.json is a list: a string is a JavaScript expression evaluated in the page (awaited),
// a number is a wait in milliseconds. Each result is printed as one JSON line; the exit code is 1
// if any step threw.
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const [url, stepsFile] = process.argv.slice(2);
const steps = JSON.parse(fs.readFileSync(stepsFile, "utf8"));
const EDGE = process.env.EDGE || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const port = 9300 + Math.floor(Math.random() * 600);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "editor-e2e-"));
const edge = spawn(EDGE, ["--headless=new", "--disable-gpu", `--remote-debugging-port=${port}`,
  `--user-data-dir=${profile}`, "--window-size=1400,1000", "about:blank"], { stdio: "ignore" });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failed = false;
try {
  let targets;
  for (let i = 0; i < 100 && !targets; i++) {
    try { targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); } catch { await sleep(200); }
  }
  const page = targets.find(t => t.type === "page");
  const ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise(r => { ws.onopen = r; });
  let id = 0;
  const pending = {};
  ws.onmessage = e => { const m = JSON.parse(e.data); if (m.id && pending[m.id]) { pending[m.id](m); delete pending[m.id]; } };
  const send = (method, params = {}) => new Promise(r => { const i = ++id; pending[i] = r; ws.send(JSON.stringify({ id: i, method, params })); });
  await send("Page.enable");
  await send("Page.navigate", { url });
  await sleep(2500);
  for (const step of steps) {
    if (typeof step === "number") { await sleep(step); continue; }
    const r = (await send("Runtime.evaluate", { expression: step, awaitPromise: true, returnByValue: true })).result;
    if (r.exceptionDetails) {
      failed = true;
      console.log(JSON.stringify({ error: r.exceptionDetails.exception?.description || r.exceptionDetails.text }));
    } else {
      console.log(JSON.stringify({ value: r.result.value }));
    }
  }
  ws.close();
} finally {
  edge.kill();
}
process.exit(failed ? 1 : 0);
