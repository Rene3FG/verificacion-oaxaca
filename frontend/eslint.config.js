// Q8: linter del frontend. Reglas recomendadas de JS + "essential" de Vue
// (errores reales, no estilo). Sin formateador obligatorio.
import js from "@eslint/js";
import pluginVue from "eslint-plugin-vue";
import globals from "globals";

export default [
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  ...pluginVue.configs["flat/essential"],
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: { ...globals.browser, ...globals.node },
    },
  },
  {
    files: ["**/*.test.js", "**/*.spec.js", "tests/**"],
    languageOptions: { globals: { ...globals.vitest } },
  },
];
