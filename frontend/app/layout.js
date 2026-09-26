// layout.js wraps EVERY page in the app. It's where global CSS is loaded and
// where the <html>/<body> tags live. You rarely touch it for a small app.
import "./globals.css";
import Providers from "./providers";

export const metadata = {
  title: "Wardro",
  description: "Your personal styling assistant",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
