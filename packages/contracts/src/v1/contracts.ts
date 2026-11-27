export const CONTRACT_SCHEMA_VERSION = '1.0.0' as const;

export type ContractSchemaVersion = typeof CONTRACT_SCHEMA_VERSION;

export type RiskTier = 'R0' | 'R1' | 'R2' | 'R3';

export type RiskVerdict = 'allow' | 'deny' | 'escalate';

export type LeaseState = 'active' | 'released' | 'expired' | 'revoked';

export interface ExecutionPacket {
  readonly schemaVersion: ContractSchemaVersion;
  readonly packetId: string;
  readonly traceId: string;
  readonly actorId: string;
  readonly tenantId: string;
  readonly targetRepo: string;
  readonly command: string;
  readonly args: readonly string[];
  readonly issuedAt: string;
  readonly expiresAt: string;
}

export interface RiskDecision {
  readonly schemaVersion: ContractSchemaVersion;
  readonly decisionId: string;
  readonly packetId: string;
  readonly tier: RiskTier;
  readonly verdict: RiskVerdict;
  readonly reason: string;
  readonly policyRef: string;
  readonly decidedAt: string;
}

export interface WorktreeLease {
  readonly schemaVersion: ContractSchemaVersion;
  readonly leaseId: string;
  readonly repo: string;
  readonly branch: string;
  readonly relativePath: string;
  readonly holderId: string;
  readonly state: LeaseState;
  readonly acquiredAt: string;
  readonly expiresAt: string;
}

export interface PcwEnvelope<TPayload = Record<string, unknown>> {
  readonly schemaVersion: ContractSchemaVersion;
  readonly envelopeId: string;
  readonly kind: string;
  readonly source: string;
  readonly correlationId: string;
  readonly timestamp: string;
  readonly payload: TPayload;
}

export interface GatewayUsageEvent {
  readonly schemaVersion: ContractSchemaVersion;
  readonly eventId: string;
  readonly tenantId: string;
  readonly service: string;
  readonly model: string;
  readonly inputTokens: number;
  readonly outputTokens: number;
  readonly latencyMs: number;
  readonly statusCode: number;
  readonly recordedAt: string;
}

const VALID_RISK_TIERS = new Set<string>(['R0', 'R1', 'R2', 'R3']);
const VALID_RISK_VERDICTS = new Set<string>(['allow', 'deny', 'escalate']);
const VALID_LEASE_STATES = new Set<string>(['active', 'released', 'expired', 'revoked']);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function isNonNegativeNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0;
}

function hasVersion(record: Record<string, unknown>): boolean {
  return record.schemaVersion === CONTRACT_SCHEMA_VERSION;
}

function hasNonEmptyStrings(record: Record<string, unknown>, keys: readonly string[]): boolean {
  return keys.every((key) => isNonEmptyString(record[key]));
}

export function isExecutionPacket(value: unknown): value is ExecutionPacket {
  if (!isRecord(value) || !hasVersion(value)) {
    return false;
  }
  const requiredStrings = [
    'packetId',
    'traceId',
    'actorId',
    'tenantId',
    'targetRepo',
    'command',
    'issuedAt',
    'expiresAt',
  ];
  if (!hasNonEmptyStrings(value, requiredStrings) || !Array.isArray(value.args)) {
    return false;
  }
  return value.args.every((entry) => typeof entry === 'string');
}

export function isRiskDecision(value: unknown): value is RiskDecision {
  if (!isRecord(value) || !hasVersion(value)) {
    return false;
  }
  const requiredStrings = ['decisionId', 'packetId', 'tier', 'verdict', 'reason', 'policyRef', 'decidedAt'];
  return (
    hasNonEmptyStrings(value, requiredStrings) &&
    VALID_RISK_TIERS.has(String(value.tier)) &&
    VALID_RISK_VERDICTS.has(String(value.verdict))
  );
}

export function isWorktreeLease(value: unknown): value is WorktreeLease {
  if (!isRecord(value) || !hasVersion(value)) {
    return false;
  }
  const requiredStrings = [
    'leaseId',
    'repo',
    'branch',
    'relativePath',
    'holderId',
    'state',
    'acquiredAt',
    'expiresAt',
  ];
  return hasNonEmptyStrings(value, requiredStrings) && VALID_LEASE_STATES.has(String(value.state));
}

export function isPcwEnvelope(value: unknown): value is PcwEnvelope {
  if (!isRecord(value) || !hasVersion(value)) {
    return false;
  }
  const requiredStrings = ['envelopeId', 'kind', 'source', 'correlationId', 'timestamp'];
  return hasNonEmptyStrings(value, requiredStrings) && isRecord(value.payload);
}

export function isGatewayUsageEvent(value: unknown): value is GatewayUsageEvent {
  if (!isRecord(value) || !hasVersion(value)) {
    return false;
  }
  const requiredStrings = ['eventId', 'tenantId', 'service', 'model', 'recordedAt'];
  const requiredNumbers = ['inputTokens', 'outputTokens', 'latencyMs', 'statusCode'];
  return (
    hasNonEmptyStrings(value, requiredStrings) &&
    requiredNumbers.every((key) => isNonNegativeNumber(value[key]))
  );
}
