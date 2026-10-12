/**
 * What a path segment field lets through as it is typed: lowercase Latin letters, digits, hyphen
 * and underscore. Upper case is folded rather than dropped — "Python" typed becomes "python";
 * anything else (Cyrillic, spaces, punctuation) never reaches the field, so there is nothing to
 * correct after the fact.
 */
export function keepSegmentChars(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9_-]/g, '')
}
