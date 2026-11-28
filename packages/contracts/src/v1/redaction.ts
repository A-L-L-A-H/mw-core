export const REDACTED_PLACEHOLDER = '[REDACTED]' as const;

export const DEFAULT_SENSITIVE_KEY_PATTERN =
  /(secret|token|password|passwd|apikey|api_key|authorization|cookie|private[_-]?key|credential)/i;

export const DEFAULT_REDACT_PATTERNS: readonly RegExp[] = [
  /Bearer\s+[A-Za-z0-9\-._~+/]+=*/gi,
  /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/g,
  /(?:sk|pk|mw)_(?:live|test|prod)_[A-Za-z0-9]{12,}/g,
  /-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----/g,
];

export function redactString(
  input: string,
  patterns: readonly RegExp[] = DEFAULT_REDACT_PATTERNS,
): string {
  let output = input;
  for (const pattern of patterns) {
    output = output.replace(pattern, REDACTED_PLACEHOLDER);
  }
  return output;
}

export function redactObject(
  input: unknown,
  sensitiveKeyPattern: RegExp = DEFAULT_SENSITIVE_KEY_PATTERN,
  patterns: readonly RegExp[] = DEFAULT_REDACT_PATTERNS,
): unknown {
  if (typeof input === 'string') {
    return redactString(input, patterns);
  }
  if (Array.isArray(input)) {
    return input.map((entry) => redactObject(entry, sensitiveKeyPattern, patterns));
  }
  if (typeof input !== 'object' || input === null) {
    return input;
  }

  const sanitized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(input as Record<string, unknown>)) {
    sanitized[key] = sensitiveKeyPattern.test(key)
      ? REDACTED_PLACEHOLDER
      : redactObject(value, sensitiveKeyPattern, patterns);
  }
  return sanitized;
}
