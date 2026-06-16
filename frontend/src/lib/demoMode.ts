/** Public demo API — shared library on Render. */
export const SHARED_DEMO_API_URL = "https://shelftxt.onrender.com";

export function resolveApiBase(): string | null {
  const configured = import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "");
  if (configured) return configured;
  if (import.meta.env.PROD) return SHARED_DEMO_API_URL;
  return null;
}

function resolveDemoModeFlag(): boolean | null {
  const flag = import.meta.env.VITE_DEMO_MODE?.trim().toLowerCase();
  if (flag === "true") return true;
  if (flag === "false") return false;
  return null;
}

/** Optional preview mode for intentionally read-only demo deployments. */
export const isDemoMode = resolveDemoModeFlag() ?? false;

export const isReadOnlyDemo = isDemoMode;

const DEMO_READ_ONLY_MESSAGE =
  "Demo is read-only. Browse and export only — self-host to make changes.";

export function assertDemoWritable(): void {
  if (isReadOnlyDemo) {
    throw new Error(DEMO_READ_ONLY_MESSAGE);
  }
}

export function demoReadOnlyMessage(): string {
  return DEMO_READ_ONLY_MESSAGE;
}
