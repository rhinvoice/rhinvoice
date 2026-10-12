/**
 * Layer rules for the frontend, analogous to the backend import-linter contracts.
 *
 *   app ──▶ features ──▶ components/ui ──▶ lib
 *               │                          ▲
 *               └──────▶ api ──────────────┘
 *
 * @type {import('dependency-cruiser').IConfiguration}
 */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      severity: "error",
      from: {},
      to: { circular: true },
    },
    {
      name: "lib-is-pure",
      comment: "lib/ contains framework-free logic and must not depend on other layers.",
      severity: "error",
      from: { path: "^src/lib/" },
      to: { path: "^src/(app|features|components|api)/" },
    },
    {
      name: "ui-components-are-generic",
      comment: "components/ui must not know about features, routing or the API.",
      severity: "error",
      from: { path: "^src/components/" },
      to: { path: "^src/(app|features|api)/" },
    },
    {
      name: "api-is-a-leaf",
      comment: "The API client only depends on lib/.",
      severity: "error",
      from: { path: "^src/api/" },
      to: { path: "^src/(app|features|components)/" },
    },
    {
      name: "features-do-not-know-the-app",
      severity: "error",
      from: { path: "^src/features/" },
      to: { path: "^src/app/" },
    },
    {
      name: "features-are-independent",
      comment: "Features share code through lib/, components/ or features/shared only.",
      severity: "error",
      from: { path: "^src/features/([^/]+)/" },
      to: {
        path: "^src/features/([^/]+)/",
        pathNot: ["^src/features/$1/", "^src/features/shared/"],
      },
    },
    {
      name: "no-dev-dependencies-in-production-code",
      severity: "error",
      from: { path: "^src/", pathNot: ["\\.test\\.tsx?$", "^src/test/"] },
      to: { dependencyTypes: ["npm-dev"], dependencyTypesNot: ["type-only"] },
    },
    {
      name: "no-unresolvable",
      severity: "error",
      from: {},
      // "node" is a triple-slash types reference in tests, not a module.
      to: { couldNotResolve: true, pathNot: ["^node$"] },
    },
    {
      name: "no-orphans",
      severity: "error",
      from: {
        orphan: true,
        pathNot: ["\\.d\\.ts$", "\\.test\\.tsx?$", "^src/test/", "^src/main\\.tsx$"],
      },
      to: {},
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.app.json" },
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default", "types"],
      extensions: [".ts", ".tsx", ".d.ts", ".js", ".css"],
    },
    reporterOptions: { text: { highlightFocused: true } },
  },
};
