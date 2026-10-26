import { ImageResponse } from "next/og";

/**
 * Возвращает PNG-иконку приложения. Размер берётся из адреса:
 * /pwa-icon?size=192 или /pwa-icon?size=512 (другие значения дают 512).
 */
export function GET(request: Request) {
  const requested = Number(new URL(request.url).searchParams.get("size"));
  const size = requested === 192 ? 192 : 512;

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
          fontSize: size * 0.6,
          fontWeight: 700,
        }}
      >
        B
      </div>
    ),
    { width: size, height: size },
  );
}