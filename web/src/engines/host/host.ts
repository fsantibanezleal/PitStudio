// The engine host (FR-018-38, FR-018-39, FR-018-46): validates a request, runs it on the engine's backend under a timeout,
// validates the result and answers with an `output` document or a typed error. `request` never rejects.
import { engineById } from "../registry";
import {
  type EngineError,
  type EngineRequest,
  type EngineResult,
  engineError,
  validateRequest,
  validateResult,
} from "./protocol";

export interface EngineBackend {
  runtime: string;
  run(request: EngineRequest, ctx: { signal: AbortSignal }): Promise<unknown>;
  terminate(): void;
}

export type EngineResponse = EngineResult | EngineError;

export interface EngineHostOptions {
  /** Engine id -> loaded engine version. */
  loaded: Record<string, string>;
  engines: Record<string, EngineBackend>;
  /** Overrides the per-engine timeouts of spec 018 section 7.1. */
  timeoutMs?: Partial<Record<string, number>>;
  onFailure?: (engineId: string, f: { runtime: string; kind: "timeout" | "throw" | "init" }) => void;
  /** No backend is called before this has settled (FR-018-29: the capability probe finishes first). */
  ready?: Promise<unknown>;
}

const DEFAULT_TIMEOUT_MS = 10_000;

class TimeoutSignal extends Error {}

export function createEngineHost(opts: EngineHostOptions): {
  request(raw: unknown): Promise<EngineResponse>;
} {
  const timeoutFor = (id: string): number => {
    const own = opts.timeoutMs && Object.hasOwn(opts.timeoutMs, id) ? opts.timeoutMs[id] : undefined;
    return own ?? engineById(id)?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  };

  async function request(raw: unknown): Promise<EngineResponse> {
    const checked = validateRequest(raw, { loaded: opts.loaded });
    if (!checked.ok) return checked.error;
    const req = checked.request;
    const backend = Object.hasOwn(opts.engines, req.engine) ? opts.engines[req.engine] : undefined;
    if (!backend) return engineError("E_UNKNOWN_ENGINE", "this engine has no backend loaded");
    try {
      await opts.ready;
    } catch {
      // a failed probe leaves the engine on its own tier logic; the backend decides
    }
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new TimeoutSignal()), timeoutFor(req.engine));
    });
    try {
      let raw: unknown;
      try {
        raw = await Promise.race([backend.run(req, { signal: controller.signal }), timeout]);
      } finally {
        clearTimeout(timer);
      }
      const result = validateResult(raw);
      return result.ok ? result.result : result.error;
    } catch (error) {
      if (error instanceof TimeoutSignal) {
        controller.abort();
        try {
          backend.terminate();
        } catch {
          // a backend that cannot be terminated has already stopped answering
        }
        opts.onFailure?.(req.engine, { runtime: backend.runtime, kind: "timeout" });
        return engineError("E_TIMEOUT", `the engine exceeded its ${timeoutFor(req.engine)} ms limit`);
      }
      const name = error instanceof Error ? error.name : "Error";
      const message = error instanceof Error ? error.message : String(error);
      opts.onFailure?.(req.engine, { runtime: backend.runtime, kind: "throw" });
      return engineError("E_RUNTIME", message.slice(0, 300) || "the engine failed", {
        name: name.slice(0, 80),
      });
    }
  }

  return { request };
}
