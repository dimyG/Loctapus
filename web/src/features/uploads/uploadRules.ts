/** Upload limits mirroring the backend's uploads endpoint. */
export const MAX_UPLOAD_MB = 25;

const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

export const ALLOWED_EXTENSIONS = [".pdf", ".docx"] as const;

/**
 * Mirrors the server's upload checks so invalid files never leave the browser.
 * The copy matches the server's 422 messages exactly.
 */
export function uploadRejection(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ALLOWED_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return "Only PDF and DOCX files are supported.";
  }
  if (file.size === 0) {
    return "The file is empty.";
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `The file is too large. The maximum size is ${MAX_UPLOAD_MB} MB.`;
  }
  return null;
}
