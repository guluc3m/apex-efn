const js = require('@eslint/js')
const tsPlugin = require('@typescript-eslint/eslint-plugin')
const prettier = require('eslint-config-prettier')
const importPlugin = require('eslint-plugin-import')

/** @type {import("eslint").Linter.Config[]} */
module.exports = [
  {
    ignores: [
      '**/node_modules',
      '**/dist',
      '**/.next',
      '**/coverage',
      '**/*.generated.*',
      '**/*.config.{js,mjs}',
    ],
  },
  js.configs.recommended,
  ...tsPlugin.configs['flat/recommended-type-checked'],
  {
    languageOptions: { parserOptions: { projectService: true } },
    plugins: { import: importPlugin },
    rules: {
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/explicit-function-return-type': 'off',
      '@typescript-eslint/explicit-module-boundary-types': 'off',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/no-misused-promises': 'error',
      'import/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],
      'no-console': ['warn', { allow: ['warn', 'error'] }],
    },
  },
  prettier,
]
