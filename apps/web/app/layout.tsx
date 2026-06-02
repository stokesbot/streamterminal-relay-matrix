import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "StreamTerminal Relay Matrix",
  description: "Control plane for MediaMTX + stream-failover-relay",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body>{children}</body>
    </html>
  );
}
