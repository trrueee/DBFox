import js from '@eslint/js'
import globals from 'globals'
import { defineConfig, globalIgnores } from 'eslint/config'

// Published DLCs remain independent JavaScript modules using the public Host
// SDK. Generated vendor bytes have separate provenance and license checks.
export default defineConfig([
  globalIgnores(['**/vendor/**', '**/node_modules/**']),
  {
    files: ['**/*.js'],
    extends: [js.configs.recommended],
    languageOptions: { globals: globals.browser },
  },
])
