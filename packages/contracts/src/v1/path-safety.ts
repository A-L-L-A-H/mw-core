import path from 'node:path';
import { ContractError } from './errors.js';

const WINDOWS_DRIVE_PATTERN = /^[a-zA-Z]:/;

export function isSafeSegment(segment: string): boolean {
  if (!segment || segment === '.' || segment === '..') {
    return false;
  }
  if (segment.includes('\0') || segment.includes('/') || segment.includes('\\')) {
    return false;
  }
  return !WINDOWS_DRIVE_PATTERN.test(segment);
}

export function assertSafeRelativePath(candidatePath: string): string {
  if (typeof candidatePath !== 'string' || candidatePath.trim().length === 0) {
    throw new ContractError({
      code: 'PATH_TRAVERSAL_DENIED',
      message: 'Relative path must be a non-empty string',
    });
  }
  if (candidatePath.includes('\0')) {
    throw new ContractError({
      code: 'PATH_TRAVERSAL_DENIED',
      message: 'Path must not contain null bytes',
    });
  }

  const normalized = candidatePath.replace(/\\/g, '/');
  if (normalized.startsWith('/') || WINDOWS_DRIVE_PATTERN.test(normalized)) {
    throw new ContractError({
      code: 'PATH_TRAVERSAL_DENIED',
      message: `Absolute path is not allowed: ${candidatePath}`,
    });
  }

  const segments = normalized.split('/').filter((segment) => segment.length > 0);
  if (segments.length === 0 || segments.some((segment) => !isSafeSegment(segment))) {
    throw new ContractError({
      code: 'PATH_TRAVERSAL_DENIED',
      message: `Unsafe path traversal segment detected: ${candidatePath}`,
    });
  }

  return segments.join('/');
}

export function resolveWithinRoot(rootDir: string, relativePath: string): string {
  const safeRelative = assertSafeRelativePath(relativePath);
  const resolvedRoot = path.resolve(rootDir);
  const resolvedTarget = path.resolve(resolvedRoot, safeRelative);
  const relativeCheck = path.relative(resolvedRoot, resolvedTarget);

  if (
    relativeCheck.startsWith('..') ||
    path.isAbsolute(relativeCheck) ||
    relativeCheck.includes('\0')
  ) {
    throw new ContractError({
      code: 'PATH_TRAVERSAL_DENIED',
      message: `Resolved path escapes root directory: ${relativePath}`,
    });
  }

  return resolvedTarget;
}
