/**
 * Attach the Supabase access token to every request to our own API.
 *
 * The backend identifies the user from this token (never from a user_id
 * sent by the browser), so every /api/ call must carry it. Many components
 * call fetch("/api/v1/...") directly; patching fetch once here covers all
 * of them. Requests to other origins are passed through untouched, so the
 * token is never sent to third parties.
 */

import { supabase } from "../supabaseClient";

const API_PATH_PREFIX = "/api/";

function requestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function isOwnApiRequest(input: RequestInfo | URL): boolean {
  try {
    const url = new URL(requestUrl(input), window.location.origin);
    return (
      url.origin === window.location.origin &&
      url.pathname.startsWith(API_PATH_PREFIX)
    );
  } catch {
    return false;
  }
}

let installed = false;

export function installAuthFetch(): void {
  if (installed) return;
  installed = true;

  const originalFetch = window.fetch.bind(window);

  window.fetch = async (
    input: RequestInfo | URL,
    init?: RequestInit
  ): Promise<Response> => {
    if (!isOwnApiRequest(input)) {
      return originalFetch(input, init);
    }

    const headers = new Headers(
      init?.headers ?? (input instanceof Request ? input.headers : undefined)
    );

    if (!headers.has("Authorization")) {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (session?.access_token) {
        headers.set("Authorization", `Bearer ${session.access_token}`);
      }
    }

    return originalFetch(input, { ...init, headers });
  };
}
