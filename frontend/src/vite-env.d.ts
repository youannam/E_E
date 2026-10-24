// Types for the environment variables Vite injects (only the ones this project uses).
interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Importing a stylesheet (Vite bundles it).
declare module "*.css";
