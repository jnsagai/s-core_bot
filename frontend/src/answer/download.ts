/** Saves text as a local file through a Blob URL; nothing is uploaded or stored. */
export function download(content: string, filename: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function exportStamp(iso: string): string {
  return iso.replace(/[-:]/g, "").replace(/\.\d+Z$/, "Z");
}
