import { useEffect, useReducer, useState } from "react";
import { ChatPanel } from "./components/ChatPanel";
import { Header } from "./components/Header";
import { LiveRegion } from "./components/LiveRegion";
import { useAnnouncer } from "./state/announcer";
import { SearchPanel } from "./components/SearchPanel";
import { SnapshotSelector } from "./components/SnapshotSelector";
import { StatusView } from "./components/StatusView";
import { conversationReducer, EMPTY_CONVERSATION } from "./state/conversation";
import { useReadiness } from "./state/readiness";

type Tab = "chat" | "search" | "status";
const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Ask" },
  { id: "search", label: "Search" },
  { id: "status", label: "Status" },
];

/** App shell (FR-001): tabs without a router or a page reload. Conversation state lives only here
 * in memory, so a reload always starts empty (FR-013). */
export function App() {
  const [readiness, refreshReadiness] = useReadiness();
  const [conversation, dispatch] = useReducer(conversationReducer, EMPTY_CONVERSATION);
  const [tab, setTab] = useState<Tab>("chat");
  const [message, announce] = useAnnouncer();

  useEffect(() => {
    if (conversation.snapshotId === null && readiness.activeSnapshotId) {
      dispatch({ type: "setSnapshot", snapshotId: readiness.activeSnapshotId });
    }
  }, [readiness.activeSnapshotId, conversation.snapshotId]);

  useEffect(() => {
    announce(readiness.status === "loading" ? "Loading" : readiness.status === "failed" ? "Failed to load" : "Ready");
  }, [readiness.status, announce]);

  const snapshot = readiness.snapshots.find((s) => s.snapshotId === conversation.snapshotId);

  function selectTab(next: Tab) {
    setTab(next);
    if (next === "status") {
      refreshReadiness();
    }
  }

  return (
    <div className="app">
      <Header snapshotId={conversation.snapshotId} />
      <div className="toolbar">
        <SnapshotSelector
          snapshots={readiness.snapshots}
          selected={conversation.snapshotId}
          hasTurns={conversation.turns.length > 0}
          onSelect={(id) => dispatch({ type: "setSnapshot", snapshotId: id })}
        />
        <button
          type="button"
          onClick={() => dispatch({ type: "clear" })}
          disabled={conversation.turns.length === 0}
        >
          New conversation
        </button>
      </div>
      <div role="tablist" aria-label="Views" className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={tab === t.id}
            aria-controls={`panel-${t.id}`}
            onClick={() => selectTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <main>
        <div role="tabpanel" id="panel-chat" aria-labelledby="tab-chat" hidden={tab !== "chat"}>
          <ChatPanel
            conversation={conversation}
            dispatch={dispatch}
            readiness={readiness}
            onRetryReadiness={refreshReadiness}
            announce={announce}
          />
        </div>
        <div role="tabpanel" id="panel-search" aria-labelledby="tab-search" hidden={tab !== "search"}>
          <SearchPanel snapshotId={conversation.snapshotId} sources={snapshot?.sources ?? []} announce={announce} />
        </div>
        <div role="tabpanel" id="panel-status" aria-labelledby="tab-status" hidden={tab !== "status"}>
          <StatusView readiness={readiness} onRefresh={refreshReadiness} />
        </div>
      </main>
      <LiveRegion message={message} />
    </div>
  );
}
