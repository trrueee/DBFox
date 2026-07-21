import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist', 'src-tauri/target']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'react-hooks/purity': 'warn',
      'react-hooks/set-state-in-effect': 'warn',
      'react-refresh/only-export-components': 'warn',
    },
  },
  {
    // TanStack Table intentionally exposes mutable callback-bearing instances.
    // React Compiler detects that boundary and skips only these components;
    // runtime hook validation remains enabled everywhere else.
    files: [
      'src/components/DataTable.tsx',
      'src/features/workspace/artifacts/table/ArtifactTableGrid.tsx',
      'src/features/workspace/table/TablePreviewPane.tsx',
    ],
    rules: {
      'react-hooks/incompatible-library': 'off',
    },
  },
])
