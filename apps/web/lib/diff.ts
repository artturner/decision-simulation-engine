/**
 * Word-level diff (Myers O(ND) greedy algorithm) for the attempt-history
 * view.  No dependency needed; reflections are small enough that worst-case
 * performance is a non-issue.
 */

export interface DiffPart {
  type: "same" | "added" | "removed";
  text: string;
}

function tokenize(text: string): string[] {
  // Split into words and whitespace runs so the diff can rejoin text
  // exactly as written.
  return text.split(/(\s+)/).filter((token) => token !== "");
}

export function diffWords(oldText: string, newText: string): DiffPart[] {
  const a = tokenize(oldText);
  const b = tokenize(newText);
  const n = a.length;
  const m = b.length;
  if (n === 0 && m === 0) return [];
  if (n === 0) return [{ type: "added", text: b.join("") }];
  if (m === 0) return [{ type: "removed", text: a.join("") }];

  const max = n + m;
  const offset = max;
  const v = new Array<number>(2 * max + 1).fill(0);
  const trace: number[][] = [];

  let found = false;
  for (let d = 0; d <= max && !found; d++) {
    trace.push(v.slice());
    for (let k = -d; k <= d; k += 2) {
      let x: number;
      if (k === -d || (k !== d && v[offset + k - 1] < v[offset + k + 1])) {
        x = v[offset + k + 1];
      } else {
        x = v[offset + k - 1] + 1;
      }
      let y = x - k;
      while (x < n && y < m && a[x] === b[y]) {
        x++;
        y++;
      }
      v[offset + k] = x;
      if (x >= n && y >= m) {
        found = true;
        break;
      }
    }
  }

  // Backtrack from (n, m) through the stored V arrays, emitting reversed parts.
  const reversed: DiffPart[] = [];
  let x = n;
  let y = m;
  for (let d = trace.length - 1; d >= 0 && (x > 0 || y > 0); d--) {
    const vPrev = trace[d];
    const k = x - y;
    let prevK: number;
    if (k === -d || (k !== d && vPrev[offset + k - 1] < vPrev[offset + k + 1])) {
      prevK = k + 1;
    } else {
      prevK = k - 1;
    }
    const prevX = vPrev[offset + prevK];
    const prevY = prevX - prevK;

    while (x > prevX && y > prevY) {
      reversed.push({ type: "same", text: a[x - 1] });
      x--;
      y--;
    }
    if (d > 0) {
      if (x === prevX) {
        reversed.push({ type: "added", text: b[prevY] });
      } else {
        reversed.push({ type: "removed", text: a[prevX] });
      }
      x = prevX;
      y = prevY;
    }
  }

  // Merge adjacent parts of the same type for compact rendering.
  const parts: DiffPart[] = [];
  for (let i = reversed.length - 1; i >= 0; i--) {
    const part = reversed[i];
    const last = parts[parts.length - 1];
    if (last && last.type === part.type) {
      last.text += part.text;
    } else {
      parts.push({ ...part });
    }
  }
  return parts;
}
