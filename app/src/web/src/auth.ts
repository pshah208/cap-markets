import {
  PublicClientApplication,
  type AccountInfo,
  type Configuration,
} from "@azure/msal-browser";

const tenantId = import.meta.env.VITE_AAD_TENANT_ID ?? "";
const clientId = import.meta.env.VITE_AAD_CLIENT_ID ?? "";
export const apiScope = import.meta.env.VITE_API_SCOPE ?? "";

/** Auth is optional so the UI can run against a mock BFF with no Entra setup. */
export const authEnabled = Boolean(tenantId && clientId && apiScope);

const config: Configuration = {
  auth: {
    clientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: window.location.origin,
    postLogoutRedirectUri: window.location.origin,
    navigateToLoginRequestUrl: false,
  },
  cache: {
    // sessionStorage keeps demo sign-ins from leaking between browser sessions.
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie: false,
  },
};

export const msal = new PublicClientApplication(config);

export async function initAuth(): Promise<void> {
  if (!authEnabled) return;
  await msal.initialize();
  const result = await msal.handleRedirectPromise();
  if (result?.account) msal.setActiveAccount(result.account);
  else {
    const [first] = msal.getAllAccounts();
    if (first) msal.setActiveAccount(first);
  }
}

export function account(): AccountInfo | null {
  return authEnabled ? msal.getActiveAccount() : null;
}

export async function login(): Promise<void> {
  await msal.loginRedirect({ scopes: [apiScope], prompt: "select_account" });
}

export async function logout(): Promise<void> {
  await msal.logoutRedirect();
}

/**
 * Access token for the BFF. Silent first; falls back to a redirect when the
 * user needs to consent or re-authenticate.
 */
export async function getToken(): Promise<string> {
  if (!authEnabled) return "";
  const acct = account();
  if (!acct) throw new Error("Not signed in.");
  try {
    const res = await msal.acquireTokenSilent({ scopes: [apiScope], account: acct });
    return res.accessToken;
  } catch {
    await msal.acquireTokenRedirect({ scopes: [apiScope], account: acct });
    return "";
  }
}
