import { useState } from "react";
import type { SnapshotSummary } from "../api/snapshots";
import { Dialog } from "./Dialog";

/** Snapshot choice (FR-017): applies at once when the conversation is empty; otherwise asks for
 * confirmation before clearing it, so no earlier evidence is shown against another snapshot. */
export function SnapshotSelector({
  snapshots,
  selected,
  hasTurns,
  onSelect,
}: {
  snapshots: SnapshotSummary[];
  selected: string | null;
  hasTurns: boolean;
  onSelect: (snapshotId: string) => void;
}) {
  const [pending, setPending] = useState<string | null>(null);

  function change(value: string) {
    if (value === selected) {
      return;
    }
    if (hasTurns) {
      setPending(value);
    } else {
      onSelect(value);
    }
  }

  return (
    <div className="snapshot-selector">
      <label htmlFor="snapshot">Documentation snapshot</label>
      <select id="snapshot" value={selected ?? ""} onChange={(e) => change(e.target.value)}>
        {selected === null && <option value="">No snapshot available</option>}
        {snapshots.map((s) => (
          <option key={s.snapshotId} value={s.snapshotId}>
            {s.snapshotId}
            {s.active ? " (active)" : ` (${s.state})`}
          </option>
        ))}
      </select>
      {pending && (
        <Dialog title="Switch documentation snapshot?" onClose={() => setPending(null)}>
          <p>
            Switching starts a new conversation. The current questions and answers will be cleared,
            because their evidence belongs to the other snapshot.
          </p>
          <div className="actions">
            <button
              type="button"
              onClick={() => {
                onSelect(pending);
                setPending(null);
              }}
            >
              Switch and clear
            </button>
            <button type="button" onClick={() => setPending(null)}>
              Keep current snapshot
            </button>
          </div>
        </Dialog>
      )}
    </div>
  );
}
