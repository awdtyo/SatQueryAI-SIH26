/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_TRANSPORT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
