// Typed failures of the analytical engines (FR-018-38, FR-018-51): a violated physical domain is E_RANGE, a malformed argument
// E_SCHEMA, a solver that does not converge E_RUNTIME, an input above a size cap E_SIZE. The host maps `code` to the protocol error of the same name.
export type AnalyticalErrorCode = "E_RANGE" | "E_SCHEMA" | "E_RUNTIME" | "E_SIZE";

export class AnalyticalError extends Error {
  readonly code: AnalyticalErrorCode;
  constructor(code: AnalyticalErrorCode, message: string) {
    super(message);
    this.name = "AnalyticalError";
    this.code = code;
  }
}

export const rangeError = (message: string) => new AnalyticalError("E_RANGE", message);
export const schemaError = (message: string) => new AnalyticalError("E_SCHEMA", message);
export const runtimeError = (message: string) => new AnalyticalError("E_RUNTIME", message);
export const sizeError = (message: string) => new AnalyticalError("E_SIZE", message);
