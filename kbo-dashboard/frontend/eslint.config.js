export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      parserOptions: { ecmaFeatures: { jsx: true } },
      globals: Object.fromEntries([
        'window', 'document', 'localStorage', 'console', 'URL', 'URLSearchParams',
        'Event', 'AbortController', 'setTimeout', 'clearTimeout', 'setInterval',
        'clearInterval', 'requestAnimationFrame', 'cancelAnimationFrame', 'ResizeObserver',
      ].map((name) => [name, 'readonly'])),
    },
    rules: {
      'no-undef': 'error',
      'no-unreachable': 'error',
      'no-constant-condition': ['error', { checkLoops: false }],
      'no-dupe-args': 'error',
      'no-dupe-keys': 'error',
      'valid-typeof': 'error',
    },
  },
]
