"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function browserArtifactDir(projectRoot, environment = process.env) {
  if (!evaluationModeEnabled(environment)) {
    return path.join(projectRoot, "output", "playwright");
  }

  const rawRoot = String(environment.AGENS_ARTIFACT_ROOT || "").trim();
  if (!rawRoot) {
    throw new Error("AGENS_ARTIFACT_ROOT is required in evaluation mode");
  }

  const artifactRoot = path.resolve(rawRoot);
  const relative = path.relative(path.resolve(projectRoot), artifactRoot);
  if (!relative || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    throw new Error("AGENS_ARTIFACT_ROOT must be outside the repository");
  }

  fs.mkdirSync(artifactRoot, { recursive: true });
  restrictWindowsAcl(artifactRoot, environment);
  const runLabel = safeRunLabel(environment.AGENS_EVALUATION_RUN_LABEL);
  return path.join(artifactRoot, "browser", runLabel);
}

function evaluationModeEnabled(environment) {
  return new Set(["1", "true", "yes", "on"]).has(
    String(environment.AGENS_EVALUATION_MODE || "").trim().toLowerCase(),
  );
}

function restrictWindowsAcl(artifactRoot, environment) {
  if (process.platform !== "win32") return;
  const user = String(environment.USERNAME || "").trim();
  if (!user) throw new Error("current Windows user is required for evaluation evidence");

  const commands = [
    ["/inheritance:r"],
    ["/grant:r", `${user}:(OI)(CI)F`, "SYSTEM:(OI)(CI)F"],
    ["/remove:g", "Everyone", "Users", "Authenticated Users"],
  ];
  for (const args of commands) {
    const result = spawnSync("icacls", [artifactRoot, ...args], { encoding: "utf8" });
    if (result.status !== 0) {
      throw new Error("could not restrict AGENS_ARTIFACT_ROOT ACL");
    }
  }
}

function safeRunLabel(value) {
  const normalized = String(value || "").trim();
  if (!normalized) return "shared";
  if (!/^[A-Za-z0-9_.-]{1,100}$/u.test(normalized)) {
    throw new Error("AGENS_EVALUATION_RUN_LABEL is invalid");
  }
  return normalized;
}

module.exports = { browserArtifactDir, evaluationModeEnabled };
