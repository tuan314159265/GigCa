const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const ts = require('typescript');
const code = ts.transpileModule(fs.readFileSync('src/app/(main)/dashboard/_components/gigca/visible-poll.ts', 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
let tick, listener, cleared = false, removed = false, calls = 0;
const document = {
  visibilityState: 'visible',
  addEventListener: (name, callback) => { assert.equal(name, 'visibilitychange'); listener = callback; },
  removeEventListener: (name, callback) => { assert.equal(callback, listener); removed = true; },
};
const context = { exports: {}, document, window: {
  setInterval: (callback, interval) => { assert.equal(interval, 30000); tick = callback; return 1; },
  clearInterval: (id) => { assert.equal(id, 1); cleared = true; },
} };
vm.runInNewContext(code, context);
const stop = context.exports.startVisiblePolling(() => calls++, 30000);
tick(); assert.equal(calls, 1);
document.visibilityState = 'hidden'; tick(); listener(); assert.equal(calls, 1);
document.visibilityState = 'visible'; listener(); assert.equal(calls, 2);
stop(); assert.equal(cleared, true); assert.equal(removed, true);
console.log('Visible polling checks passed.');
