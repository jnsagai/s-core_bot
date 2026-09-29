/**
 * Readiness derived from `/api/v1/capabilities`, `/health/ready` and `/api/v1/snapshots`
 * (data-model.md AppReadinessState). Fetched on load and re-fetched only on an explicit user
 * action — there is deliberately no timer or polling here (FR-006a, A-036).
 */
import { useCallback, useEffect, useState } from "react";
import { getCapabilities, getHealthReady } from "../api/capabilities";
import { getSnapshots, type SnapshotSummary } from "../api/snapshots";

export interface AppReadinessState {
  status: "loading" | "ready" | "failed";
  search: { available: boolean; degradedReason: string | null };
  chat: { available: boolean; reason: string | null };
  compare: { available: boolean; reason: string | null };
  limits: { questionCharacters: number; historyCharacters: number } | null;
  models: { generation: string; embedding: string } | null;
  snapshots: SnapshotSummary[];
  activeSnapshotId: string | null;
  error: string | null;
  fetchedAt: number | null;
}

export const INITIAL_READINESS: AppReadinessState = {
  status: "loading",
  search: { available: false, degradedReason: null },
  chat: { available: false, reason: null },
  compare: { available: false, reason: null },
  limits: null,
  models: null,
  snapshots: [],
  activeSnapshotId: null,
  error: null,
  fetchedAt: null,
};

export async function loadReadiness(): Promise<AppReadinessState> {
  const [capabilities, snapshots] = await Promise.all([getCapabilities(), getSnapshots()]);
  const ready = await getHealthReady().catch(() => null);
  const search = capabilities.modes.search ?? { available: false, reasons: [] };
  const chat = capabilities.modes.chat ?? { available: false, reasons: [] };
  const comparison = capabilities.modes.compare ?? { available: false, reasons: [] };
  const searchReasons = ready?.capabilities?.search?.reasons ?? search.reasons;
  return {
    status: "ready",
    search: {
      available: search.available,
      degradedReason: searchReasons.find((r) => r !== "not_implemented") ?? null,
    },
    chat: { available: chat.available, reason: chat.reasons[0] ?? null },
    compare: { available: comparison.available, reason: comparison.reasons[0] ?? null },
    limits: {
      questionCharacters: capabilities.limits.questionCharacters,
      historyCharacters: capabilities.limits.historyCharacters,
    },
    models: capabilities.models,
    snapshots: snapshots.snapshots,
    activeSnapshotId: snapshots.active,
    error: null,
    fetchedAt: Date.now(),
  };
}

export function useReadiness(): [AppReadinessState, () => void] {
  const [state, setState] = useState<AppReadinessState>(INITIAL_READINESS);
  const refresh = useCallback(() => {
    loadReadiness()
      .then(setState)
      .catch((error: unknown) =>
        setState({
          ...INITIAL_READINESS,
          status: "failed",
          error: error instanceof Error ? error.message : "The application API is unreachable.",
        }),
      );
  }, []);
  useEffect(() => {
    refresh();
  }, [refresh]);
  return [state, refresh];
}
