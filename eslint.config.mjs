// JavaScript lint for CI (ESLint). The site's scripts in docs/ are classic <script> files that
// share one global scope; the tools in scripts/ and the tests in tests/ are Node modules.
// When a review corrects a new code pattern, add the rule that catches it here (AGENTS.md,
// "Corrections become checks"). Run: npx eslint .   (versions in .github/workflows/ci.yml)
import js from "@eslint/js";
import globals from "globals";

export default [
  // codeql/*/test holds the cases a query must find, bad on purpose
  { ignores: ["dashboard/**", "docs/vendor/**", ".github/**", "node_modules/**", "codeql/**"] },
  // eslint-disable and other inline comments do not count: a finding is fixed, never silenced
  { linterOptions: { noInlineConfig: true, reportUnusedInlineConfigs: "error" } },
  js.configs.recommended,
  {
    files: ["docs/**/*.js"],
    languageOptions: {
      sourceType: "script",
      globals: {
        ...globals.browser,
        L: "readonly", // Leaflet, docs/vendor/leaflet
        // set by one page script and read by the next (window.RCB = ... and top-level names)
        RCB: "readonly", RCBGeo: "readonly", RCBSentinel: "readonly", RCBWayback: "readonly",
        I18N: "readonly", i18nAdd: "readonly",
      },
    },
    rules: {
      // a top-level function of one page script is called from another one or from the HTML
      "no-unused-vars": ["error", { vars: "local", args: "none", caughtErrors: "none" }],
      // the script that defines a shared name (listed above) declares it at the top level
      "no-redeclare": ["error", { builtinGlobals: false }],
    },
  },
  {
    files: ["docs/sw.js"],
    languageOptions: { globals: { ...globals.serviceworker } },
  },
  {
    files: ["**/*.mjs", "**/*.cjs", "scripts/**/*.js", "tests/**/*.js"],
    languageOptions: { globals: { ...globals.node } },
    rules: { "no-unused-vars": ["error", { args: "none", caughtErrors: "none" }] },
  },
  {
    files: ["**/*.cjs"],
    languageOptions: { sourceType: "commonjs" },
  },
];
