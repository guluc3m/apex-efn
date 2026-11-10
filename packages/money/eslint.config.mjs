import library from '@apex/eslint-config/library.js'

// ADR-300: deterministic engines take `now` as input. Reading the clock or unseeded randomness here is a bug.
const message = 'Inject the clock (`now`) or a seeded source instead (ADR-300).'

export default [
  ...library,
  {
    files: ['src/**/*.ts'],
    ignores: ['src/**/*.test.ts'],
    rules: {
      'no-restricted-syntax': [
        'error',
        { selector: "NewExpression[callee.name='Date'][arguments.length=0]", message },
        {
          selector: "CallExpression[callee.object.name='Date'][callee.property.name='now']",
          message,
        },
        {
          selector: "CallExpression[callee.object.name='Math'][callee.property.name='random']",
          message,
        },
      ],
    },
  },
]
