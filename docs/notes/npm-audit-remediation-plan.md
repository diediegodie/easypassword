# npm audit remediation plan (frontend)

Summary
- Audit summary: `docs/npm-audit-frontend.json` — 55 vulnerabilities (35 high, 16 moderate, 4 low).
- Root cause: many issues originate from outdated Angular core/tooling and build toolchain dependencies (e.g. `@angular/*`, `@angular-devkit/*`, `@angular/cli`, `@angular/compiler-cli`, `jest-preset-angular`). Many fixes require major version bumps.

Goals
- Eliminate or mitigate high/critical vulnerabilities in production dependencies.
- Keep CI and local developer experience stable.

High-level remediation steps
1. Capture current state
   - Review `docs/npm-audit-frontend.json` (already saved).
   - Create a feature branch: `git checkout -b fix/npm-audit-upgrades`.

2. Prioritize direct prod deps first
   - Target `@angular/core`, `@angular/common`, `@angular/compiler`, `@angular/platform-browser`, `@angular/router`, `@angular/forms`, `@angular/animations`.
   - Upgrade to the latest compatible stable major (audit shows fixes available at `22.0.7` for many). This is a major upgrade and will likely require code changes.

3. Upgrade build tooling and test presets
   - Upgrade `@angular/cli` and `@angular-devkit/build-angular` (fixes many transitive vulnerabilities such as `webpack`, `postcss`, `esbuild`, `copy-webpack-plugin`).
   - Upgrade `@angular/compiler-cli` and `jest-preset-angular` (audit suggests `jest-preset-angular@17`).

4. Upgrade devtooling and linters
   - Bump `@typescript-eslint/*` packages to versions compatible with the upgraded TypeScript and ESLint (audit reports these as high).

5. Apply updates safely
   - Use `ng update` where possible to handle Angular migrations:

```bash
git checkout -b fix/npm-audit-upgrades
npm ci
npx ng update @angular/core @angular/cli
```

   - After Angular update, run `npm install` to update lockfile.
   - Run `npm test`, `npm run build`, and linting locally and in CI.

6. Handle transitive fixes that remain
   - If some advisories are not fixed by upgrades, consider using npm `overrides` (npm v8+) or yarn `resolutions` to pin safe versions of transitive deps.
   - Example (package.json `overrides`):

```json
"overrides": {
  "serialize-javascript": "7.0.5"
}
```

   - Run `npm ci` and validate again.

7. If upgrade is not feasible immediately
   - Mitigate risk by restricting dev tooling use in CI for production builds; ensure production bundle does not include vulnerable dev dependencies.
   - Consider backporting patches for small transitive packages if acceptable.

Testing and rollout
- Create a CI job that runs full unit, integration, and e2e tests for the upgrade branch.
- Run manual smoke tests of the app (`docker-compose up --build`) and validate health endpoints and critical flows.
- Prepare a PR with upgrade notes, migration steps, and checklist for reviewers.

Timeline & effort estimate
- Small teams: 1–3 days for upgrade + fixes + test run if no major breaking API changes. If templates/strictness require code changes, 1–2 weeks may be needed.
- Risk: major Angular/tooling upgrades often affect TypeScript config, Jest setup (`jest-preset-angular`), and builder APIs.

Deliverables for the remediation PR
- `package.json` and `package-lock.json` updated (or `yarn.lock`).
- `docs/npm-audit-frontend.json` regenerated after fixes.
- CI green on branch with tests and build.
- Short rollback plan (revert lockfile and package.json) and notes for local devs.

References
- Audit snapshot: `docs/npm-audit-frontend.json`.
- Recommended next steps: open a tracked issue and coordinate the upgrade in a dedicated branch/PR.
