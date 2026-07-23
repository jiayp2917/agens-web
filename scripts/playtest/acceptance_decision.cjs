"use strict";

function issueCounts(issues) {
  return {
    p0: (issues || []).filter((item) => item?.level === "P0").length,
    p1: (issues || []).filter((item) => item?.level === "P1").length,
  };
}

function isAcceptedResult(result) {
  return result === "passed" || result === "passed_terminal";
}

function evaluateAcceptance({ result, issues, contentAuditFailOnP1 = false }) {
  const counts = issueCounts(issues);
  if (isAcceptedResult(result) && counts.p0 > 0) return "failed_audit";
  if (isAcceptedResult(result) && contentAuditFailOnP1 && counts.p1 > 0) {
    return "failed_content";
  }
  return result;
}

function acceptanceFailed({ result, issues, contentAuditFailOnP1 = false }) {
  const finalResult = evaluateAcceptance({ result, issues, contentAuditFailOnP1 });
  return !isAcceptedResult(finalResult);
}

module.exports = {
  acceptanceFailed,
  evaluateAcceptance,
  isAcceptedResult,
  issueCounts,
};
