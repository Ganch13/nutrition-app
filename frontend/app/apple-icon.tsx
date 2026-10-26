import { ImageResponse } from "next/og";

// Размер и формат значка, как требует соглашение Next.js
export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Значок приложения для iPhone: белая буква B на зелёном фоне. */
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#047857",
          color: "white",
          fontSize: 110,
          fontWeight: 700,
        }}
      >
        B
      </div>
    ),
    { ...size },
  );
}