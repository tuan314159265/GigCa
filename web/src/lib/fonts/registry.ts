import localFont from "next/font/local";

// Use the same Geist family as the template, from its installed package.
// No Google Fonts request is needed to start the offline preview.
const geist = localFont({
  src: "../../../node_modules/geist/dist/fonts/geist-sans/Geist-Variable.woff2",
  variable: "--font-geist",
  weight: "100 900",
  display: "swap",
});
const geistMono = localFont({
  src: "../../../node_modules/geist/dist/fonts/geist-mono/GeistMono-Variable.woff2",
  variable: "--font-geist-mono",
  weight: "100 900",
  display: "swap",
});
export const fontRegistry = {
  geist: { label: "Geist", font: geist },
  geistMono: { label: "Geist Mono", font: geistMono },
} as const;
export type FontKey = keyof typeof fontRegistry;
export const fontKeys = Object.keys(fontRegistry) as FontKey[];
export const fontVars = Object.values(fontRegistry)
  .map(({ font }) => font.variable)
  .join(" ");
export const fontOptions = fontKeys.map((key) => ({ key, label: fontRegistry[key].label }));
