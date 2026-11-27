import { describe, expect, test } from 'bun:test';
import path from 'node:path';
import {
  CONTRACT_SCHEMA_VERSION,
  ContractError,
  REDACTED_PLACEHOLDER,
  assertSafeRelativePath,
  isExecutionPacket,
  isGatewayUsageEvent,
  isPcwEnvelope,
  isRiskDecision,
  isSafeSegment,
  isWorktreeLease,
  redactObject,
  redactString,
  resolveWithinRoot,
  toContractErrorEnvelope,
} from '../src/index.js';

describe('@moonwitness/contracts v1 wire contracts', () => {
  test('validates ExecutionPacket', () => {
    const packet = {
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      packetId: 'pkt-01',
      traceId: 'trc-01',
      actorId: 'usr-01',
      tenantId: 'tnt-01',
      targetRepo: 'mw-xv',
      command: 'test',
      args: ['--watch=false'],
      issuedAt: '2026-11-27T00:00:00Z',
      expiresAt: '2026-11-27T00:05:00Z',
    };
    expect(isExecutionPacket(packet)).toBe(true);
    expect(isExecutionPacket({ ...packet, schemaVersion: '2.0.0' })).toBe(false);
    expect(isExecutionPacket({ ...packet, args: [123] })).toBe(false);
  });

  test('validates RiskDecision', () => {
    const decision = {
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      decisionId: 'dec-01',
      packetId: 'pkt-01',
      tier: 'R2',
      verdict: 'allow',
      reason: 'verified policy match',
      policyRef: 'policy://default/v1',
      decidedAt: '2026-11-27T00:00:01Z',
    };
    expect(isRiskDecision(decision)).toBe(true);
    expect(isRiskDecision({ ...decision, tier: 'R9' })).toBe(false);
    expect(isRiskDecision({ ...decision, verdict: 'skip' })).toBe(false);
  });

  test('validates WorktreeLease', () => {
    const lease = {
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      leaseId: 'lse-01',
      repo: 'mw-xv',
      branch: 'feat/w11',
      relativePath: 'worktrees/w11',
      holderId: 'agent-01',
      state: 'active',
      acquiredAt: '2026-11-27T00:00:00Z',
      expiresAt: '2026-11-27T01:00:00Z',
    };
    expect(isWorktreeLease(lease)).toBe(true);
    expect(isWorktreeLease({ ...lease, state: 'unknown' })).toBe(false);
  });

  test('validates PcwEnvelope', () => {
    const envelope = {
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      envelopeId: 'env-01',
      kind: 'task.dispatched',
      source: 'mw-dock',
      correlationId: 'corr-01',
      timestamp: '2026-11-27T00:00:00Z',
      payload: { taskId: 'C07' },
    };
    expect(isPcwEnvelope(envelope)).toBe(true);
    expect(isPcwEnvelope({ ...envelope, payload: 'not-an-object' })).toBe(false);
  });

  test('validates GatewayUsageEvent', () => {
    const event = {
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      eventId: 'evt-01',
      tenantId: 'tnt-01',
      service: 'mw-rocksoul',
      model: 'gemini-2.5-pro',
      inputTokens: 1200,
      outputTokens: 350,
      latencyMs: 420,
      statusCode: 200,
      recordedAt: '2026-11-27T00:00:02Z',
    };
    expect(isGatewayUsageEvent(event)).toBe(true);
    expect(isGatewayUsageEvent({ ...event, inputTokens: -1 })).toBe(false);
  });
});

describe('@moonwitness/contracts errors, redaction, and path-safety', () => {
  test('formats ContractError and generic Error into envelopes', () => {
    const contractErr = new ContractError({
      code: 'RISK_POLICY_DENIED',
      message: 'Blocked by R3 policy',
      retryable: false,
      traceId: 'trc-99',
    });
    expect(toContractErrorEnvelope(contractErr)).toEqual({
      schemaVersion: CONTRACT_SCHEMA_VERSION,
      code: 'RISK_POLICY_DENIED',
      message: 'Blocked by R3 policy',
      retryable: false,
      traceId: 'trc-99',
    });

    const fallback = toContractErrorEnvelope(new Error('boom'), 'trc-100');
    expect(fallback.code).toBe('INTERNAL_CONTRACT_ERROR');
    expect(fallback.traceId).toBe('trc-100');
  });

  test('redacts bearer tokens, JWTs, and sensitive object keys', () => {
    const sampleJwt = 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ1c3ItMSJ9.c2lnbmF0dXJlMTIzNDU';
    expect(redactString(`Authorization: Bearer ${sampleJwt}`)).toBe(
      `Authorization: ${REDACTED_PLACEHOLDER}`,
    );
    expect(redactString(`token=${sampleJwt}`)).toBe(`token=${REDACTED_PLACEHOLDER}`);

    const redacted = redactObject({
      actor: 'usr-1',
      apiKey: 'sk_live_1234567890abcdef',
      nested: { authorization: 'Bearer secret-val', note: 'safe' },
    }) as Record<string, unknown>;
    expect(redacted.actor).toBe('usr-1');
    expect(redacted.apiKey).toBe(REDACTED_PLACEHOLDER);
    expect((redacted.nested as Record<string, unknown>).authorization).toBe(REDACTED_PLACEHOLDER);
    expect((redacted.nested as Record<string, unknown>).note).toBe('safe');
  });

  test('enforces path-safety against traversal, absolute paths, and null bytes', () => {
    expect(isSafeSegment('valid-name.ts')).toBe(true);
    expect(isSafeSegment('..')).toBe(false);
    expect(assertSafeRelativePath('packages\\contracts\\index.ts')).toBe(
      'packages/contracts/index.ts',
    );
    expect(() => assertSafeRelativePath('../etc/passwd')).toThrow(ContractError);
    expect(() => assertSafeRelativePath('/etc/passwd')).toThrow(ContractError);
    expect(() => assertSafeRelativePath('C:\\Windows\\System32')).toThrow(ContractError);
    expect(() => assertSafeRelativePath('safe\0file.txt')).toThrow(ContractError);

    const root = path.resolve('z:/repo/mw-core');
    const target = resolveWithinRoot(root, 'packages/contracts/package.json');
    expect(target.startsWith(root)).toBe(true);
  });
});
