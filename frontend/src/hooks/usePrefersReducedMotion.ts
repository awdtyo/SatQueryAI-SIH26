import { useEffect, useState } from "react";

const QUERY = "(prefers-reduced-motion: reduce)";

function readPreference(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  return window.matchMedia(QUERY).matches;
}

/** Tracks the user's motion preference, including live OS-level changes. */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(readPreference);

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const list = window.matchMedia(QUERY);
    const handleChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    list.addEventListener("change", handleChange);
    return () => list.removeEventListener("change", handleChange);
  }, []);

  return reduced;
}
