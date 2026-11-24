/**
 * Typed Backend API Client for Excel Auto Grader.
 * Automatically attaches Bearer JWT from active teacher session.
 * Includes Render cold-start auto-retry & background wake-up ping.
 * NEVER stores or reads Google OAuth tokens in Local Storage.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

const BACKEND_ROOT_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
const SESSION_TOKEN_KEY = "eag_teacher_session_jwt";

export function getSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return sessionStorage.getItem(SESSION_TOKEN_KEY) || localStorage.getItem(SESSION_TOKEN_KEY);
}

export function setSessionToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) {
    localStorage.setItem(SESSION_TOKEN_KEY, token);
  } else {
    localStorage.removeItem(SESSION_TOKEN_KEY);
    sessionStorage.removeItem(SESSION_TOKEN_KEY);
  }
}

/** Fire-and-forget ping to keep Render backend warm continuously. */
export function wakeUpBackend(): void {
  if (typeof window === "undefined") return;
  fetch(`${BACKEND_ROOT_URL}/ping`, { method: "GET", cache: "no-store" }).catch(() => {
    fetch(`${BACKEND_ROOT_URL}/health`, { method: "GET", cache: "no-store" }).catch(() => {});
  });
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getSessionToken();
  const headers = new Headers(options.headers || {});
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  if (!(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const method = (options.method || "GET").toUpperCase();
  const isSafeToRetry = method === "GET" || path.startsWith("/auth/");
  const retryDelays = isSafeToRetry ? [2000, 4000, 7000, 10000] : [2500, 5000, 8000];

  let res: Response | null = null;
  for (let attempt = 0; attempt <= retryDelays.length; attempt++) {
    try {
      res = await fetch(`${API_BASE_URL}${path}`, {
        cache: "no-store",
        ...options,
        headers,
      });
      // Render Free Tier returns 502/503/504 briefly while spinning up from sleep
      if ((res.status === 502 || res.status === 503 || res.status === 504) && attempt < retryDelays.length) {
        await sleep(retryDelays[attempt]);
        continue;
      }
      break;
    } catch {
      if (attempt < retryDelays.length) {
        await sleep(retryDelays[attempt]);
        continue;
      }
      throw new ApiError(
        "ไม่สามารถติดต่อเซิร์ฟเวอร์ Backend ได้ในขณะนี้ (Render Free Tier อาจกำลังปลุกเซิร์ฟเวอร์หรือประมวลผลไฟล์จำนวนมาก กรุณารอสักครู่แล้วกดลองใหม่)",
        0
      );
    }
  }

  if (!res) {
    throw new ApiError("ไม่สามารถติดต่อเซิร์ฟเวอร์ Backend ได้ กรุณาลองใหม่อีกครั้ง", 0);
  }

  if (!res.ok) {
    let msg = `เกิดข้อผิดพลาด (HTTP ${res.status})`;
    try {
      const errJson = await res.json();
      msg = errJson.detail || errJson.message || msg;
    } catch {
      // ignore parse failure
    }
    if (res.status === 401 && typeof window !== "undefined") {
      setSessionToken(null);
    }
    throw new ApiError(msg, res.status);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function downloadFileFromApi(path: string, filename: string): Promise<void> {
  const token = getSessionToken();
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    throw new ApiError("ไม่สามารถดาวน์โหลดไฟล์ได้", res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
