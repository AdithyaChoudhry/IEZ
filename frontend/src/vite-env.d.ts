/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

/** From the git history at build time (vite.config.ts). */
declare const __APP_VERSION__: string;
