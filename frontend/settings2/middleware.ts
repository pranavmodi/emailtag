import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (!pathname.startsWith("/pifstats") || pathname === "/pifstats/login") {
    return NextResponse.next();
  }

  const session = request.cookies.get("pifstats_session")?.value;
  if (session) {
    return NextResponse.next();
  }

  const loginUrl = request.nextUrl.clone();
  loginUrl.pathname = "/pifstats/login";
  loginUrl.search = "";
  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ["/pifstats/:path*"],
};
