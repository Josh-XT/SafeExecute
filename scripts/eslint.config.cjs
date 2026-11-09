// Standalone linting inside the sandbox, without evaluating workspace config.
const tsParser = require('@typescript-eslint/parser');

module.exports = [
  {
    files: ['**/*.{js,mjs,cjs,ts,tsx,mts,cts}'],
    linterOptions: { noInlineConfig: true },
    rules: { 'no-debugger': 'error', 'no-unreachable': 'error' },
  },
  {
    files: ['**/*.{ts,tsx,mts,cts}'],
    languageOptions: { parser: tsParser },
  },
];
