/** findLastIndex для WebView без ES2023 (миниапп MAX и старые Safari). */
export function findLastIndex<T>(
  arr: readonly T[],
  predicate: (item: T, index: number) => boolean,
): number {
  const native = (Array.prototype as { findLastIndex?: typeof findLastIndex }).findLastIndex;
  if (typeof native === "function") {
    return native.call(arr, predicate);
  }
  for (let i = arr.length - 1; i >= 0; i--) {
    if (predicate(arr[i], i)) return i;
  }
  return -1;
}
