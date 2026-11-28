import { CONTRACT_SCHEMA_VERSION, type ContractSchemaVersion } from './contracts.js';

export type ContractErrorCode =
  | 'CONTRACT_VALIDATION_FAILED'
  | 'CONTRACT_VERSION_MISMATCH'
  | 'PATH_TRAVERSAL_DENIED'
  | 'RISK_POLICY_DENIED'
  | 'LEASE_CONFLICT'
  | 'AUTH_TOKEN_INVALID'
  | 'AUTH_TOKEN_REVOKED'
  | 'INTERNAL_CONTRACT_ERROR';

export interface ContractErrorEnvelope {
  readonly schemaVersion: ContractSchemaVersion;
  readonly code: ContractErrorCode;
  readonly message: string;
  readonly retryable: boolean;
  readonly traceId?: string;
  readonly details?: Readonly<Record<string, unknown>>;
}

export interface ContractErrorOptions {
  readonly code: ContractErrorCode;
  readonly message: string;
  readonly retryable?: boolean;
  readonly traceId?: string;
  readonly details?: Readonly<Record<string, unknown>>;
}

export class ContractError extends Error {
  public readonly code: ContractErrorCode;
  public readonly retryable: boolean;
  public readonly traceId?: string;
  public readonly details?: Readonly<Record<string, unknown>>;

  constructor(options: ContractErrorOptions) {
    super(options.message);
    this.name = 'ContractError';
    this.code = options.code;
    this.retryable = options.retryable ?? false;
    this.traceId = options.traceId;
    this.details = options.details;
  }

  public toEnvelope(): ContractErrorEnvelope {
    return {
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      code: this.code,
      message: this.message,
      retryable: this.retryable,
      ...(this.traceId ? { traceId: this.traceId } : {}),
      ...(this.details ? { details: this.details } : {}),
    };
  }
}

export function toContractErrorEnvelope(
  err: unknown,
  traceId?: string,
): ContractErrorEnvelope {
  if (err instanceof ContractError) {
    const envelope = err.toEnvelope();
    return traceId && !envelope.traceId ? { ...envelope, traceId } : envelope;
  }
  const message = err instanceof Error ? err.message : 'Unexpected contract error';
  return {
    schemaVersion: CONTRACT_SCHEMA_VERSION,
    code: 'INTERNAL_CONTRACT_ERROR',
    message,
    retryable: false,
    ...(traceId ? { traceId } : {}),
  };
}
