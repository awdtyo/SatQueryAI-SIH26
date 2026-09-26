import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { checkHealth, getCapabilities } from "../api/mockClient";
import type { Capabilities } from "../lib/capabilities";
import type { HealthSnapshot } from "../types/api";

const HEALTH_POLL_MS = 15000;

interface MissionStatus {
  /** Live `/api/health` snapshot, or `{ status: "offline" }` when unreachable. */
  health: HealthSnapshot | null;
  /** Live `/api/capabilities` map, or null when it could not be read. */
  capabilities: Capabilities | null;
  /** True until the first health probe settles. */
  probing: boolean;
}

const MissionStatusContext = createContext<MissionStatus>({
  health: null,
  capabilities: null,
  probing: true,
});

/**
 * Single source of truth for backend/system state.
 *
 * Both the boot cinematic and the dashboard read from here, so a module is never
 * reported READY in one place and UNKNOWN in another, and the health probe runs
 * exactly once per page.
 */
export function useMissionStatus(): MissionStatus {
  return useContext(MissionStatusContext);
}

export function MissionStatusProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<HealthSnapshot | null>(null);
  const [capabilities, setCapabilities] = useState<Capabilities | null>(null);
  const [probing, setProbing] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const snapshot = await checkHealth();
        if (!cancelled) setHealth(snapshot as HealthSnapshot);
      } catch {
        if (!cancelled) setHealth({ status: "offline" });
      } finally {
        if (!cancelled) setProbing(false);
      }
    };
    void poll();
    const id = window.setInterval(poll, HEALTH_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    getCapabilities()
      .then((caps) => {
        if (!cancelled) setCapabilities(caps);
      })
      .catch(() => {
        // Capability map unavailable — panels fall back to UNKNOWN, never READY.
        if (!cancelled) setCapabilities(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const value = useMemo<MissionStatus>(
    () => ({ health, capabilities, probing }),
    [health, capabilities, probing],
  );

  return <MissionStatusContext.Provider value={value}>{children}</MissionStatusContext.Provider>;
}
