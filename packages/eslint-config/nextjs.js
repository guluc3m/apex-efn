const { FlatCompat } = require('@eslint/eslintrc')

const base = require('./base.js')

const compat = new FlatCompat({ baseDirectory: __dirname })

/** @type {import("eslint").Linter.Config[]} */
module.exports = [
  ...compat.extends('next/core-web-vitals'),
  ...base,
  { rules: { '@next/next/no-html-link-for-pages': 'off' } },
]
