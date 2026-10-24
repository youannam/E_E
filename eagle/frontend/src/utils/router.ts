// A tiny hash router: "#/alerts/12" -> { page: "alerts", id: 12 }.
// Hash URLs work with any static file server and need no extra library.
import { useEffect, useState } from "react";

export type PageName = "dashboard" | "alerts" | "users" | "activities" | "simulation" | "rules" | "accounts";

export interface Route {
  page: PageName;
  id: number | null;
}

const PAGES: PageName[] = ["dashboard", "alerts", "users", "activities", "simulation", "rules", "accounts"];

export function parseHash(hash: string): Route {
  const [first, second] = hash.replace(/^#\/?/, "").split("?")[0].split("/");
  const page = PAGES.includes(first as PageName) ? (first as PageName) : "dashboard";
  const id = second && /^\d+$/.test(second) ? Number(second) : null;
  return { page, id };
}

/** Query parameters after the page in the hash, e.g. "#/alerts?date=2026-10-09". */
export function hashParams(): URLSearchParams {
  return new URLSearchParams(window.location.hash.split("?")[1] ?? "");
}

export function navigate(path: string): void {
  window.location.hash = path.startsWith("#") ? path : `#${path}`;
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
