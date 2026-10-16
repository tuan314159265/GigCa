// Browser-only: no requests while the tab is hidden; refresh on returning.
export function startVisiblePolling(refresh: () => void, intervalMs: number) {
  const visibleRefresh = () => {
    if (document.visibilityState === "visible") refresh();
  };
  const timer = window.setInterval(visibleRefresh, intervalMs);
  document.addEventListener("visibilitychange", visibleRefresh);
  return () => {
    window.clearInterval(timer);
    document.removeEventListener("visibilitychange", visibleRefresh);
  };
}
