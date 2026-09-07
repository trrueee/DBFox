// Debugger/profile/download boundary only; actual application entry remains unchanged.
import { app } from 'electron';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { appendFileSync, mkdirSync } from 'node:fs';

const runtime = process.env.DBFOX_RUNTIME_DIR;
app.setPath('userData', join(runtime, 'electron-profile'));
app.setPath('logs', join(runtime, 'electron-logs'));
app.commandLine.appendSwitch('remote-debugging-port', process.env.GAME_QA_CDP_PORT || '19230');
const destination = join(runtime, 'downloads');
mkdirSync(destination, { recursive: true });
app.on('session-created', session => {
  session.on('will-download', (_event, item) => {
    const filename = item.getFilename();
    if (!/^[a-zA-Z0-9._ -]+\.(png|json)$/.test(filename)) return;
    item.setSavePath(join(destination, filename));
    item.once('done', (_done, state) => {
      appendFileSync(join(runtime, 'download-events.jsonl'), JSON.stringify({ filename, state,
        totalBytes: item.getTotalBytes(), receivedBytes: item.getReceivedBytes(),
        boundary: 'verification-controlled-native-save-path' }) + '\n');
    });
  });
});
await import(pathToFileURL(join(process.cwd(), 'dist-electron/main/index.js')).href);
