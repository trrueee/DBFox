import { fileURLToPath } from 'node:url'
import { ESLint } from 'eslint'

const eslint = new ESLint({
  cwd: fileURLToPath(new URL('../../', import.meta.url)),
  overrideConfigFile: fileURLToPath(new URL('../eslint.dlcs.config.js', import.meta.url)),
})
const results = await eslint.lintFiles(['dlcs/*/frontend/**/*.js', 'dlcs/*/vendor-src/**/*.js'])
const formatter = await eslint.loadFormatter('stylish')
process.stdout.write(formatter.format(results))
if (results.some(result => result.errorCount || result.warningCount)) process.exitCode = 1
