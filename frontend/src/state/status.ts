import type { TurnStatus } from "./conversation";

export const STATUS_LABELS: Record<TurnStatus, string> = {
  queued: "Queued",
  searching: "Searching the documentation",
  generating: "Generating an answer",
  validating: "Checking the answer against its sources",
  ready: "Ready",
  cancelled: "Stopped",
  failed: "Failed",
};
