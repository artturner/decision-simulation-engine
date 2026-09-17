/**
 * Student-name comparison helpers.
 *
 * TypeScript port of services/api/app/services/names.py — keep the two in
 * sync (and the copies in the essay-grader repo). Casefolds, collapses
 * whitespace, and folds "Last, First" to "first last" so the same student
 * matches across apps whose rosters disagree only on order or case.
 *
 * Limitation: comma-suffixed names ("Smith, Jr., John") fold wrong;
 * acceptable under the identical-roster-spellings convention.
 */

export function normalizeStudentName(value: string | null | undefined): string {
  if (!value) return "";
  return value.split(/\s+/).filter(Boolean).join(" ");
}

export function studentNameKey(value: string | null | undefined): string {
  let s = normalizeStudentName(value).toLowerCase();
  const comma = s.indexOf(",");
  if (comma !== -1) {
    const last = s.slice(0, comma).trim();
    const first = s.slice(comma + 1).trim();
    s = `${first} ${last}`;
  }
  return s.split(/\s+/).filter(Boolean).join(" ");
}

export function namesEquivalent(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  const ka = studentNameKey(a);
  return ka.length > 0 && ka === studentNameKey(b);
}
