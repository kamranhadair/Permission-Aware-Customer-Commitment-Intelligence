import test from "node:test";
import assert from "node:assert/strict";
import { askReducer, initialAskState } from "../src/features/commitments/lib/askReducer.ts";
import type { CitationView } from "../src/types/domain.ts";

const citation: CitationView = {
  id: "1",
  citationLabel: "E1",
  source: "call",
  title: "T",
  excerpt: "e",
  occurredAt: "2026-01-01T00:00:00Z",
};

test("SUBMIT moves to loading with the given requestId", () => {
  assert.deepEqual(askReducer(initialAskState, { type: "SUBMIT", requestId: 1 }), { phase: "loading", requestId: 1 });
});

test("RESOLVED for the current request applies the result", () => {
  let state = askReducer(initialAskState, { type: "SUBMIT", requestId: 1 });
  state = askReducer(state, {
    type: "RESOLVED",
    requestId: 1,
    result: { kind: "answered", answer: "A", citations: [citation] },
  });
  assert.deepEqual(state, { phase: "answered", requestId: 1, answer: "A", citations: [citation] });
});

test("a stale RESOLVED for a superseded request (user asked again before the first resolved) is discarded", () => {
  let state = askReducer(initialAskState, { type: "SUBMIT", requestId: 1 });
  state = askReducer(state, { type: "SUBMIT", requestId: 2 });
  const beforeStaleResolve = state;

  state = askReducer(state, {
    type: "RESOLVED",
    requestId: 1,
    result: { kind: "answered", answer: "stale answer for request 1", citations: [] },
  });

  assert.deepEqual(state, beforeStaleResolve);
  assert.deepEqual(state, { phase: "loading", requestId: 2 });
});

test("RESET always clears to idle, discarding any in-flight or resolved state", () => {
  let state = askReducer(initialAskState, { type: "SUBMIT", requestId: 1 });
  state = askReducer(state, {
    type: "RESOLVED",
    requestId: 1,
    result: { kind: "answered", answer: "A", citations: [] },
  });
  state = askReducer(state, { type: "RESET" });
  assert.deepEqual(state, { phase: "idle" });
});

test("a RESOLVED that arrives after a RESET (e.g. a persona/account switch mid-flight) is discarded, not applied", () => {
  let state = askReducer(initialAskState, { type: "SUBMIT", requestId: 1 });
  state = askReducer(state, { type: "RESET" });
  state = askReducer(state, {
    type: "RESOLVED",
    requestId: 1,
    result: { kind: "answered", answer: "late answer belonging to the old persona", citations: [] },
  });
  assert.deepEqual(state, { phase: "idle" });
});

test("insufficient_evidence/not_found/operational_error resolve to their own distinct phases", () => {
  const submit = askReducer(initialAskState, { type: "SUBMIT", requestId: 7 });
  assert.equal(
    askReducer(submit, { type: "RESOLVED", requestId: 7, result: { kind: "insufficient_evidence" } }).phase,
    "insufficient_evidence",
  );
  assert.equal(
    askReducer(submit, { type: "RESOLVED", requestId: 7, result: { kind: "not_found" } }).phase,
    "not_found",
  );
  assert.equal(
    askReducer(submit, { type: "RESOLVED", requestId: 7, result: { kind: "operational_error" } }).phase,
    "operational_error",
  );
});
