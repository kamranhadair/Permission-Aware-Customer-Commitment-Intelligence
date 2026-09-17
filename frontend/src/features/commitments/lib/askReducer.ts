// Pure state machine for the account page's "Ask about this account" panel
// (AskAccountPanel.tsx). Kept independent of React/fetch so the two
// security-relevant behaviors it exists to guarantee can be proven with
// plain function calls, no rendering required:
//   1. switching persona/account resets any previously shown answer —
//      RESET always clears to "idle" unconditionally.
//   2. a response for a superseded request can never overwrite what a
//      newer request already produced/is producing — RESOLVED is ignored
//      unless its requestId matches the current in-flight request.

import type { CitationView } from "../../../types/domain.ts";

export type AskResolution =
  | { kind: "answered"; answer: string; citations: CitationView[] }
  | { kind: "insufficient_evidence" }
  | { kind: "not_found" }
  | { kind: "operational_error" };

export type AskState =
  | { phase: "idle" }
  | { phase: "loading"; requestId: number }
  | { phase: "answered"; requestId: number; answer: string; citations: CitationView[] }
  | { phase: "insufficient_evidence"; requestId: number }
  | { phase: "not_found"; requestId: number }
  | { phase: "operational_error"; requestId: number };

export type AskAction =
  | { type: "SUBMIT"; requestId: number }
  | { type: "RESOLVED"; requestId: number; result: AskResolution }
  | { type: "RESET" };

export const initialAskState: AskState = { phase: "idle" };

export function askReducer(state: AskState, action: AskAction): AskState {
  switch (action.type) {
    case "RESET":
      return { phase: "idle" };

    case "SUBMIT":
      return { phase: "loading", requestId: action.requestId };

    case "RESOLVED": {
      const isCurrentRequest = state.phase !== "idle" && state.requestId === action.requestId;
      if (!isCurrentRequest) {
        // A stale response for a request that's no longer the latest one
        // (superseded by a new question, or by a persona/account switch
        // that reset state) — discard it silently.
        return state;
      }
      switch (action.result.kind) {
        case "answered":
          return {
            phase: "answered",
            requestId: action.requestId,
            answer: action.result.answer,
            citations: action.result.citations,
          };
        case "insufficient_evidence":
          return { phase: "insufficient_evidence", requestId: action.requestId };
        case "not_found":
          return { phase: "not_found", requestId: action.requestId };
        case "operational_error":
          return { phase: "operational_error", requestId: action.requestId };
      }
    }
  }
}
