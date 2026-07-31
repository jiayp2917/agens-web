"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");

function browserOutputDir(projectRoot, environment = process.env) {
  const configured = String(environment.AGENS_PLAYTEST_OUTPUT_DIR || "").trim();
  const parent = configured ? path.resolve(configured) : path.join(os.tmpdir(), "agens-web-playtest");
  const repository = path.resolve(projectRoot);
  const relative = path.relative(repository, parent);
  if (!relative || (!relative.startsWith("..") && !path.isAbsolute(relative))) {
    throw new Error("AGENS_PLAYTEST_OUTPUT_DIR must be outside the repository");
  }
  fs.mkdirSync(parent, { recursive: true });
  return fs.mkdtempSync(path.join(parent, "run-"));
}

module.exports = { browserOutputDir };
