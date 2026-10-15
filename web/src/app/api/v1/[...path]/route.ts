import { NextRequest, NextResponse } from "next/server";

import { AUTH_COOKIE } from "@/lib/auth";

export const runtime = "nodejs";

function failure(message: string, status: number) {
  return NextResponse.json({ error: { message } }, { status, headers: { "Cache-Control": "no-store" } });
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (
    !path.length ||
    path.some((part) => !/^[a-zA-Z0-9_-]+$/.test(part)) ||
    !["auth", "me", "sessions", "recommendations", "research", "cameras"].includes(path[0])
  ) {
    return failure("Endpoint không tồn tại.", 404);
  }
  const endpoint = path.join("/");
  const authenticating = endpoint === "auth/login" || endpoint === "auth/register";
  const loggingOut = endpoint === "auth/logout";
  if (request.method !== "GET") {
    const origin = request.headers.get("origin");
    // Next dev may normalize nextUrl.host to localhost even for 127.0.0.1.
    try {
      if (
        !origin ||
        new URL(origin).host !== request.headers.get("host") ||
        !["http:", "https:"].includes(new URL(origin).protocol)
      )
        return failure("Nguồn yêu cầu không hợp lệ.", 403);
    } catch {
      return failure("Nguồn yêu cầu không hợp lệ.", 403);
    }
  }
  const token = request.cookies.get(AUTH_COOKIE)?.value;
  if (!authenticating && !token) return failure("Vui lòng đăng nhập để tiếp tục.", 401);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token && !authenticating) headers.Authorization = `Bearer ${token}`;
  const idem = request.headers.get("Idempotency-Key");
  if (idem) headers["Idempotency-Key"] = idem;
  const maxSize = endpoint === "me/log-imports/preview" ? 1_048_576 : endpoint === "cameras/near-route" ? 65536 : 16384;
  let body: string | undefined;
  if (request.method !== "GET") {
    const length = Number(request.headers.get("content-length") || 0);
    if (length > maxSize) return failure("Yêu cầu quá lớn.", 413);
    body = await request.text();
    if (Buffer.byteLength(body, "utf8") > maxSize) return failure("Yêu cầu quá lớn.", 413);
  }
  try {
    const backend = process.env.GIGCA_API_URL || "http://127.0.0.1:8000";
    const upstream = await fetch(`${backend}/api/v1/${endpoint}${request.nextUrl.search}`, {
      method: request.method,
      headers,
      body,
      cache: "no-store",
      signal: AbortSignal.timeout(45000),
    });
    if (endpoint.startsWith("cameras/") && endpoint.endsWith("/image") && upstream.ok) {
      const contentType = upstream.headers.get("content-type") ?? "";
      if (!["image/jpeg", "image/png", "image/webp"].includes(contentType))
        return failure("Nguồn camera không trả ảnh hợp lệ.", 502);
      const bytes = await upstream.arrayBuffer();
      if (bytes.byteLength > 3 * 1024 * 1024) return failure("Ảnh camera quá lớn.", 502);
      return new NextResponse(bytes, {
        status: 200,
        headers: {
          "Content-Type": contentType,
          "Cache-Control": "private, max-age=20",
          "X-Content-Type-Options": "nosniff",
          "X-Camera-Fetched-At": upstream.headers.get("x-camera-fetched-at") ?? "",
        },
      });
    }
    const data = (await upstream.json()) as Record<string, unknown>;
    const secret = typeof data.token === "string" ? data.token : undefined;
    delete data.token;
    const response = NextResponse.json(data, {
      status: upstream.status,
      headers: { "Cache-Control": "no-store" },
    });
    if (authenticating && upstream.ok && secret) {
      response.cookies.set(AUTH_COOKIE, secret, {
        httpOnly: true,
        sameSite: "lax",
        secure: request.nextUrl.protocol === "https:",
        path: "/",
        maxAge: typeof data.expires_in_s === "number" ? data.expires_in_s : 7 * 86400,
      });
    }
    if (loggingOut || (!authenticating && upstream.status === 401)) response.cookies.delete(AUTH_COOKIE);
    return response;
  } catch {
    const response = failure("Không kết nối được backend GigCa. Vui lòng thử lại.", 503);
    if (loggingOut) response.cookies.delete(AUTH_COOKIE);
    return response;
  }
}

export { proxy as GET, proxy as POST, proxy as PATCH };
