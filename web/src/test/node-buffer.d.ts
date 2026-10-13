/**
 * Minimal typing for Node's buffer module, which this project's tsconfig does
 * not include in `types` (only vite/client). The test suite needs its File
 * class to bridge the jsdom/undici Blob realm split; the runtime resolves the
 * real module in Node.
 */
declare module "node:buffer" {
  export class File extends Blob {
    constructor(parts: BlobPart[], name: string, options?: { type?: string });
  }
}
