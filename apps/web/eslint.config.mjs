import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypeScript from "eslint-config-next/typescript";

/**
 * ESLint flat config.
 *
 * eslint-config-next 16 ships native flat configs, so they are spread directly. The
 * `FlatCompat` bridge from @eslint/eslintrc is not needed and in fact crashes on these
 * configs, because it JSON-stringifies a plugin object that contains a circular reference.
 */
const config = [
  ...nextCoreWebVitals,
  ...nextTypeScript,
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "next-env.d.ts",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  {
    rules: {
      // An unused variable is either a leftover or a bug. Underscore-prefixed names are
      // the escape hatch for intentionally-ignored arguments.
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // `any` defeats the point of the generated contracts.
      "@typescript-eslint/no-explicit-any": "error",
      // console.log left in a server component prints on every render.
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
];

export default config;
