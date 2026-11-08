const globals = require('globals')

const base = require('./base.js')

/** @type {import("eslint").Linter.Config[]} */
module.exports = [
  ...base,
  {
    languageOptions: { globals: { ...globals.node } },
  },
]
