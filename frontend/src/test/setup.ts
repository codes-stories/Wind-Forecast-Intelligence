import "@testing-library/jest-dom/vitest";

// Recharts' ResponsiveContainer relies on ResizeObserver and layout size,
// neither of which jsdom provides. Simulate a reasonable chart box so charts
// don't emit "width(0) and height(0)" warnings during tests.
class ResizeObserverStub {
  private readonly callback: ResizeObserverCallback;
  private readonly elements = new Set<Element>();

  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
  }

  observe(element: Element): void {
    if (this.elements.has(element)) return;
    this.elements.add(element);
    queueMicrotask(() => {
      if (!this.elements.has(element)) return;
      const box = {
        width: 800,
        height: 320,
        top: 0,
        left: 0,
        right: 800,
        bottom: 320,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      };
      this.callback(
        [
          {
            target: element,
            contentRect: box,
            borderBoxSize: [],
            contentBoxSize: [],
            devicePixelContentBoxSize: [],
          } as unknown as ResizeObserverEntry,
        ],
        this as unknown as ResizeObserver,
      );
    });
  }

  unobserve(element: Element): void {
    this.elements.delete(element);
  }

  disconnect(): void {
    this.elements.clear();
  }
}

if (!("ResizeObserver" in globalThis)) {
  Object.defineProperty(globalThis, "ResizeObserver", {
    value: ResizeObserverStub,
    writable: true,
    configurable: true,
  });
}

// jsdom performs no layout, so every element reports a 0×0 rect. Recharts sizes
// itself from getBoundingClientRect() and warns on 0. Give zero-sized elements
// a plausible chart box so tests behave like a real browser.
const elementProto = Element.prototype as unknown as {
  getBoundingClientRect: () => DOMRect;
};
const originalGetBoundingClientRect = elementProto.getBoundingClientRect;
elementProto.getBoundingClientRect = function patched(this: Element): DOMRect {
  const rect = originalGetBoundingClientRect.call(this);
  if (rect.width === 0 && rect.height === 0) {
    return {
      x: 0,
      y: 0,
      width: 800,
      height: 320,
      top: 0,
      left: 0,
      right: 800,
      bottom: 320,
      toJSON: () => ({}),
    } as DOMRect;
  }
  return rect;
};

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
