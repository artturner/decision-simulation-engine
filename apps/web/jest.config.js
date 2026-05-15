const nextJest = require("next/jest");

const createJestConfig = nextJest({ dir: "./" });

/** @type {import('jest').Config} */
const config = {
  testEnvironment: "jest-environment-jsdom",
  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],
  // Resolve @/ alias to match tsconfig paths
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/$1",
  },
  // Keep jest out of .next build artifacts and Playwright e2e specs
  testPathIgnorePatterns: ["/node_modules/", "/.next/", "/e2e/"],
  // Prevent Haste collision with .next/standalone/package.json
  watchPathIgnorePatterns: ["/.next/"],
  modulePathIgnorePatterns: ["/.next/"],
};

module.exports = createJestConfig(config);
