import { useId } from "react";
import { DOT, LETTER_PATH, LETTER_STROKE, WORDMARK_BOX, WORDMARK_PATH } from "@/lib/brand-art";

/**
 * Значок приложения: индиго-плитка, белая буква «Л» и шафрановая точка.
 * Рисуется тем же контуром, что и значок на телефоне (design/make_brand_assets.py), поэтому они совпадают.
 * Пример: <BrandMark size={44} /> в меню, <BrandMark size={104} pulse /> на экране загрузки.
 * pulse — точка «дышит»: видно, что приложение работает, а не зависло.
 */
export function BrandMark({ size = 40, pulse = false }: { size?: number; pulse?: boolean }) {
  // Уникальный идентификатор градиента: на странице может быть несколько значков
  const gradientId = `lad-g-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 512 512" width={size} height={size} role="img" aria-label="Лад">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3c48b5" />
          <stop offset="1" stopColor="#232a74" />
        </linearGradient>
      </defs>
      <rect width="512" height="512" rx="116" fill={`url(#${gradientId})`} />
      <path
        d={LETTER_PATH}
        fill="none"
        stroke="#fff"
        strokeWidth={LETTER_STROKE}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx={DOT[0]} cy={DOT[1]} r={DOT[2]} fill="#f2a22e" className={pulse ? "lad-dot" : undefined} />
    </svg>
  );
}

/**
 * Надпись «Лад» шрифтом Lora, нарисованная контуром: не зависит от загрузки шрифтов, поэтому видна сразу.
 * height — высота в пикселях, цвет берётся из текста (currentColor).
 */
export function Wordmark({ height = 28 }: { height?: number }) {
  const [x, y, width, boxHeight] = WORDMARK_BOX;
  return (
    <svg
      viewBox={`${x} ${y} ${width} ${boxHeight}`}
      height={height}
      width={(height * width) / boxHeight}
      role="img"
      aria-label="Лад"
      fill="currentColor"
    >
      <path d={WORDMARK_PATH} />
    </svg>
  );
}
