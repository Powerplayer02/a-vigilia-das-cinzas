"""Optional Frida timings for an owned diagnostic child, never the live game.

Install Frida in the diagnostic environment only. Hooks change execution timing;
these observations locate waits and must not be used as FPS benchmarks.
"""
import json
from pathlib import Path

SCRIPT = r'''
const qpc = new NativeFunction(Module.getGlobalExportByName('QueryPerformanceCounter'), 'int', ['pointer']);
const qpf = new NativeFunction(Module.getGlobalExportByName('QueryPerformanceFrequency'), 'int', ['pointer']);
const frequency = Memory.alloc(8); qpf(frequency);
const scale = 1000 / Number(frequency.readS64());
function now() { const value = Memory.alloc(8); qpc(value); return Number(value.readS64()) * scale; }
const stats = {}, installed = [];
for (const module of Process.enumerateModules()) {
  if (!/^(libpanda.*|opengl32|gdi32)\.dll$/i.test(module.name)) continue;
  for (const exp of module.enumerateExports()) {
    if (exp.type !== 'function') continue;
    const name = exp.name;
    if (!(/\?tick@ClockObject@@/.test(name) || /\?(main_tick|client_main_tick)@PStatClient@@/.test(name) ||
          /\?transmit_control_data@PStatClientImpl@@/.test(name) || /\?render_frame@GraphicsEngine@@/.test(name) ||
          /\?force_yield@Thread@@/.test(name) || /^(wglMakeCurrent|SwapBuffers|glFinish)$/.test(name))) continue;
    const label = module.name + '!' + name;
    stats[label] = {calls:0,total_ms:0,max_ms:0}; installed.push(label);
    Interceptor.attach(exp.address, {
      onEnter() { this.begin = now(); this.utc = Date.now(); },
      onLeave() {
        const elapsed = now() - this.begin, entry = stats[label];
        entry.calls++; entry.total_ms += elapsed; entry.max_ms = Math.max(entry.max_ms, elapsed);
        if (elapsed >= 20) send({kind:'slow_call',name:label,ms:elapsed,utc_ms:this.utc,thread:this.threadId});
      }
    });
  }
}
send({kind:'hooks',pid:Process.id,installed});
rpc.exports = { summary() { return stats; } };
'''


class NativeTrace:
    def __init__(self, pid: int, directory: Path):
        import frida
        self.directory = directory
        self.stream = (directory / 'native-calls.jsonl').open('w', encoding='utf8', buffering=1)
        self.session = frida.attach(pid)
        self.script = self.session.create_script(SCRIPT)
        self.errors = []
        self.hooks = []
        def message(value, data):
            self.stream.write(json.dumps(value) + '\n')
            if value['type'] == 'error': self.errors.append(value)
            elif value.get('payload', {}).get('kind') == 'hooks':
                self.hooks = value['payload']['installed']
        self.script.on('message', message)
        self.script.load()
        # A synchronous RPC is also a barrier for hook installation.
        self.script.exports_sync.summary()
        if self.errors or not any('ClockObject' in name for name in self.hooks):
            self.close()
            raise RuntimeError('Native hooks unavailable; inspect native-calls.jsonl')

    def checkpoint(self):
        result = self.script.exports_sync.summary()
        (self.directory / 'native-call-summary.json').write_text(json.dumps(result, indent=2), encoding='utf8')

    def close(self):
        try: self.session.detach()
        finally: self.stream.close()
