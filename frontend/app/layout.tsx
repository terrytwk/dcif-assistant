import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "MIT DCIF Assistant",
  description: "Assistant for MIT DCIF instruments, guides, training, and facility information"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
