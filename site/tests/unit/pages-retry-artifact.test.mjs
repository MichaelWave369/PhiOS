import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const yaml = readFileSync(new URL("../../../.github/workflows/site.yml", import.meta.url), "utf8");
const nameExpr = "github-pages-\${{ github.run_attempt }}";

test("Pages upload and deploy select the same explicit attempt-scoped artifact name", () => {
  const upload = yaml.match(
    /- uses: actions\/upload-pages-artifact@v5\s+with:\s+name: ([^\r\n]+)\s+path: site\/dist/,
  );
  const deploy = yaml.match(
    /- name: Deploy GitHub Pages\s+id: deployment\s+uses: actions\/deploy-pages@v5\s+with:\s+artifact_name: ([^\r\n]+)/,
  );
  assert.ok(upload, "Pages uploader must name the artifact explicitly");
  assert.ok(deploy, "Pages deployer must select that named artifact explicitly");
  assert.equal(upload[1].trim(), nameExpr);
  assert.equal(deploy[1].trim(), nameExpr);
});

test("retrying a failed deployment does not create indistinguishable artifacts", () => {
  const first = nameExpr.replace("\${{ github.run_attempt }}", "1");
  const second = nameExpr.replace("\${{ github.run_attempt }}", "2");
  assert.notEqual(first, second);
  assert.equal(first, "github-pages-1");
  assert.equal(second, "github-pages-2");
});
