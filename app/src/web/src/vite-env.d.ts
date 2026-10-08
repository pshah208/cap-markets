/// <reference types="vite/client" />

declare module "virtual:bank-config" {
  const config: Readonly<{
    schemaVersion: 1;
    bankName: string;
    bankShortName: string;
    primaryColor: string;
    accentColor: string;
    logo?: "logo.png";
  }>;
  export default config;
}

interface ImportMetaEnv {
  readonly VITE_AAD_TENANT_ID?: string;
  readonly VITE_AAD_CLIENT_ID?: string;
  readonly VITE_API_SCOPE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
