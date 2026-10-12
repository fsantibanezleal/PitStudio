// Every call of the console UI: one request to its own origin (the console API), no other host.
import type { Job, JobCreated, JobList, Problem, RecipeList, RunList } from "~/contracts/generated/console";

export type Json = Record<string, unknown>;
export interface StageRef {
  id: string;
  variant?: string;
}
export interface JobRequest {
  recipe: string;
  profile: string;
  stages?: StageRef[];
  force?: boolean;
  rerun_check?: boolean;
}

/** A failed call: the problem's one-line detail when the console sent one, else the HTTP status. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch (e) {
    throw new ApiError(e instanceof Error ? e.message : "network error", 0);
  }
  const text = await res.text();
  let body: unknown;
  try {
    body = JSON.parse(text);
  } catch {
    body = undefined;
  }
  if (!res.ok) {
    const p = body as Partial<Problem> | undefined;
    throw new ApiError(
      typeof p?.detail === "string" && p.detail ? p.detail : `HTTP ${res.status}`,
      res.status,
    );
  }
  if (body === undefined || body === null || typeof body !== "object")
    throw new ApiError("invalid response body", res.status);
  return body as T;
}

const post = (body?: unknown): RequestInit => ({
  method: "POST",
  headers: { "content-type": "application/json" },
  body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  recipes: () => call<RecipeList>("/recipes"),
  recipe: (id: string) => call<Json>(`/recipes/${encodeURIComponent(id)}`),
  queue: () => call<JobList>("/queue"),
  runs: () => call<RunList>("/runs"),
  run: (id: string) => call<Json>(`/runs/${encodeURIComponent(id)}`),
  createJob: (req: JobRequest) => call<JobCreated>("/jobs", post(req)),
  cancelJob: (id: string) => call<Job>(`/jobs/${encodeURIComponent(id)}/cancel`, post()),
  artefactUrl: (run: string, artefact: string) =>
    `/runs/${encodeURIComponent(run)}/artefacts/${encodeURIComponent(artefact)}`,
  eventsUrl: (run: string) => `/runs/${encodeURIComponent(run)}/events`,
};

export function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}
