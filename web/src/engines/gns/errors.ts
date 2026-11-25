// Error classes of the `gns` engine (spec 011, FR-011-15).

/** The graph builder or the GNS step received an invalid input; no graph or acceleration is returned. */
export class InvalidGraphError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvalidGraphError";
  }
}
