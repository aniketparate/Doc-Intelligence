import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Ultra Doc-Intelligence",
  description: "Multi-tenant RAG platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased" suppressHydrationWarning>
      <body className="min-h-full bg-slate-950 text-slate-100">{children}</body>
    </html>
  );
}
