/** Header (FR-002): community-project label, bound snapshot, local-mode indicator, and the short
 * persistent description from master spec §11.1. */
export function Header({ snapshotId }: { snapshotId: string | null }) {
  return (
    <header className="header">
      <h1 className="brand">
        S-CORE Docs Assistant <span className="tag">Community project</span>
      </h1>
      <p className="meta">
        <span>Snapshot: {snapshotId ?? "none"}</span> · <span>Runs on this computer</span>
      </p>
      <p className="muted small">
        Community documentation assistant. Check cited sources for engineering decisions.
      </p>
    </header>
  );
}
