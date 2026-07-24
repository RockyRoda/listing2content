import type { Metadata } from "next";
import { Fraunces, Instrument_Sans } from "next/font/google";
import "./globals.css";

/** Display: a soft high-contrast serif for headings and the golden-ratio marks. */
const display = Fraunces({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  style: ["normal", "italic"],
  variable: "--font-display",
  display: "swap",
});

/** Body/UI: a clean, slightly warm grotesque for text and controls. */
const body = Instrument_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  variable: "--font-body",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Listing2Content",
  description:
    "Turn a resort listing into a full content package, drafted in your voice.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <div className="ambient" aria-hidden="true" />
        {children}
      </body>
    </html>
  );
}
