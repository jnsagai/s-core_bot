import type { TurnStatus } from "../state/conversation";
import { STATUS_LABELS } from "../state/status";


/** Visual state of one request (FR-004). Announcements go through `LiveRegion`, not here. */
export function StatusBadge({ status, position }: { status: TurnStatus; position?: number }) {
  const label =
    status === "queued" && position ? `${STATUS_LABELS.queued} (position ${position})` : STATUS_LABELS[status];
  return (
    <span className={`status status-${status}`} data-status={status}>
      {label}
    </span>
  );
}
