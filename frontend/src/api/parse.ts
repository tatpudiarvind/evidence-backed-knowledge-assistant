/** Thrown when an API response doesn't have the expected shape. */
export class ResponseShapeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ResponseShapeError";
  }
}

export type JsonObject = Record<string, unknown>;

export function asObject(value: unknown): JsonObject {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new ResponseShapeError("Expected a JSON object.");
  }
  return value as JsonObject;
}

export function readString(source: JsonObject, key: string): string {
  const value = source[key];
  if (typeof value !== "string") {
    throw new ResponseShapeError(`Expected "${key}" to be a string.`);
  }
  return value;
}

export function readOptionalString(source: JsonObject, key: string): string | null {
  const value = source[key];
  if (value === undefined || value === null) {
    return null;
  }
  if (typeof value !== "string") {
    throw new ResponseShapeError(`Expected "${key}" to be a string or null.`);
  }
  return value;
}

export function readNumber(source: JsonObject, key: string): number {
  const value = source[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ResponseShapeError(`Expected "${key}" to be a number.`);
  }
  return value;
}

export function readOptionalNumber(source: JsonObject, key: string): number | null {
  const value = source[key];
  if (value === undefined || value === null) {
    return null;
  }
  return readNumber(source, key);
}

export function readBoolean(source: JsonObject, key: string): boolean {
  const value = source[key];
  if (typeof value !== "boolean") {
    throw new ResponseShapeError(`Expected "${key}" to be true or false.`);
  }
  return value;
}

export function readArray(source: JsonObject, key: string): unknown[] {
  const value = source[key];
  if (!Array.isArray(value)) {
    throw new ResponseShapeError(`Expected "${key}" to be an array.`);
  }
  return value;
}

export function readEnum<T extends string>(
  source: JsonObject,
  key: string,
  allowed: readonly T[],
): T {
  const value = readString(source, key);
  const match = allowed.find((option) => option === value);
  if (match === undefined) {
    throw new ResponseShapeError(`Unexpected "${key}" value.`);
  }
  return match;
}

export function readOptionalEnum<T extends string>(
  source: JsonObject,
  key: string,
  allowed: readonly T[],
): T | null {
  const value = source[key];
  if (value === undefined || value === null) {
    return null;
  }
  return readEnum(source, key, allowed);
}
