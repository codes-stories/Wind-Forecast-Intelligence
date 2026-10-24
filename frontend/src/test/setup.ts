import "@testing-library/jest-dom/vitest";

// Recharts' ResponsiveContainer relies on ResizeObserver, which jsdom lacks.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

if (!("ResizeObserver" in globalThis)) {
  Object.defineProperty(globalThis, "ResizeObserver", {
    value: ResizeObserverStub,
    writable: true,
    configurable: true,
  });
}

// jsdom's AbortSignal belongs to a different realm than Node's (undici) fetch,
// which rejects it with "Expected signal to be an instance of AbortSignal".
// Strip incompatible signals so real requests work in jsdom tests (abort-on-
// unmount is not exercised in tests).
const nativeFetch = globalThis.fetch?.bind(globalThis);
if (nativeFetch) {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (init?.signal && typeof Request === "function") {
      try {
        // Node's Request validates the signal against Node's AbortSignal realm
        new Request("http://signal-check.invalid/", { signal: init.signal });
      } catch {
        const fallback: RequestInit = { ...init };
        delete fallback.signal;
        return nativeFetch(input, fallback);
      }
    }
    return nativeFetch(input, init);
  }) as typeof fetch;
}
