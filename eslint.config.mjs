import js from '@eslint/js';
import { defineConfig, globalIgnores } from 'eslint/config';
import { createTypeScriptImportResolver } from 'eslint-import-resolver-typescript';
import { importX } from 'eslint-plugin-import-x';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default defineConfig([
  globalIgnores([
    '**/node_modules/**',
    '**/dist/**',
    '**/.expo/**',
    '**/android/**',
    '**/ios/**',
    'apps/api/**',
    'supabase/**',
    'infra/**',
  ]),
  {
    files: ['**/*.{js,mjs,cjs,ts,tsx}'],
    extends: [js.configs.recommended, tseslint.configs.recommended],
    languageOptions: {
      globals: { ...globals.node },
    },
    rules: {
      '@typescript-eslint/consistent-type-imports': ['error', { fixStyle: 'inline-type-imports' }],
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', ignoreRestSiblings: true }],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
  {
    // Circular import detection (type-only imports are ignored by this rule).
    files: ['**/*.{js,mjs,cjs,ts,tsx}'],
    extends: [importX.flatConfigs.typescript],
    settings: {
      'import-x/resolver-next': [
        createTypeScriptImportResolver({
          noWarnOnMultipleProjects: true,
          project: [
            `${import.meta.dirname}/apps/mobile/tsconfig.json`,
            `${import.meta.dirname}/packages/domain/tsconfig.json`,
          ],
        }),
      ],
    },
    rules: {
      'import-x/no-cycle': ['error', { ignoreExternal: true }],
      'import-x/no-self-import': 'error',
    },
  },
  {
    files: ['apps/mobile/**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.browser, __DEV__: 'readonly' },
    },
  },
  {
    files: ['**/*.config.{js,cjs}', 'apps/mobile/babel.config.js', 'apps/mobile/metro.config.js', 'apps/mobile/tailwind.config.js'],
    rules: { '@typescript-eslint/no-require-imports': 'off' },
  },
]);
