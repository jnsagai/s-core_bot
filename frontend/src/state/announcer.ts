import { useCallback, useRef, useState } from "react";

/**
 * One shared polite live region (FR-004, US4 AS2). `announce` ignores a message identical to the
 * previous one, so a state transition is read once, never once per rendered claim or token.
 */
export function useAnnouncer(): [string, (message: string) => void] {
  const [message, setMessage] = useState("");
  const last = useRef("");
  const announce = useCallback((next: string) => {
    if (next && next !== last.current) {
      last.current = next;
      setMessage(next);
    }
  }, []);
  return [message, announce];
}
