// A real child pipe and the actual EngineSupervisor isolate post-handshake backpressure.
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import assert from 'node:assert/strict';
const root=resolve(fileURLToPath(new URL('../../../..',import.meta.url)));
const require=createRequire(resolve(root,'desktop/package.json'));
const {build}=require('esbuild');
const compiled=await build({entryPoints:[resolve(root,'desktop/main/engine.ts')],bundle:true,platform:'node',format:'esm',write:false});
const {EngineSupervisor}=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const python=process.argv[2]||'D:/Project/DBFox/.venv/Scripts/python.exe';
let child,finished=false;
const supervisor=new EngineSupervisor({async launch(){
  child=spawn(python,['-u','-c',`import os,time,json
print('DBFOX_ENGINE_READY '+json.dumps({'port':18625,'protocolVersion':1,'serverInfo':{'name':'dbfox-engine','version':'probe'},'capabilities':['http','sse','problem-details']}),flush=True)
time.sleep(.2)
for i in range(1024): os.write(1,b'x'*4096)
os.write(2,b'DRAINED')
time.sleep(60)
`],{stdio:['ignore','pipe','pipe'],windowsHide:true});
  child.stderr.on('data',data=>{if(data.toString().includes('DRAINED'))finished=true;});
  return {pid:child.pid,stdout:child.stdout,onExit(listener){const handler=(code,signal)=>listener({code,signal});child.on('exit',handler);return ()=>child.off('exit',handler);},async stop(){child.kill();await new Promise(resolve=>child.once('close',resolve));}};
}},{async waitUntilHealthy(){}},{restartLimit:0,tokenFactory:()=> 'verification-only-in-memory'});
try {
  await supervisor.start();
  await new Promise(resolve=>setTimeout(resolve,1200));
  const beforeDrain=finished,flowing=child.stdout.readableFlowing;
  child.stdout.resume();
  for(let i=0;i<30&&!finished;i++)await new Promise(resolve=>setTimeout(resolve,50));
  console.log(JSON.stringify({ready:supervisor.status().state,producer_completed_without_intervention:beforeDrain,stdout_flowing_after_ready:flowing,producer_completed_after_control_resume:finished,bytes:4194304}));
  assert.equal(beforeDrain,true,'Ready EngineSupervisor left the child stdout pipe blocked');
} finally {await supervisor.stop();}
