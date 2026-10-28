// Подготовка фотографии к загрузке: уменьшение и пересохранение в JPEG прямо в браузере.

/** Максимальная длина большей стороны фото после уменьшения, пикселей. */
const MAX_SIDE = 1600;

/** Качество JPEG от 0 до 1: 0.85 почти не заметно глазу и в 5–10 раз меньше исходного файла. */
const JPEG_QUALITY = 0.85;

/** Загружает файл как картинку; браузер сам применяет поворот из EXIF. */
function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();
    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Не удалось открыть фото. Выберите изображение JPEG, PNG или WebP."));
    };
    image.src = url;
  });
}

/**
 * Уменьшает фото до 1600 пикселей по большей стороне и сохраняет как JPEG.
 *
 * Зачем: снимок с телефона весит 3–10 МБ, для сравнения прогресса хватает в разы меньшего.
 * Заодно пересохранение через canvas стирает метаданные (координаты, модель телефона).
 * Пример: фото 4032×3024 (5 МБ) → 1600×1200 (около 300 КБ).
 */
export async function prepareImage(file: File): Promise<Blob> {
  const image = await loadImage(file);
  const scale = Math.min(1, MAX_SIDE / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Браузер не смог обработать фото.");
  // Белый фон: у PNG с прозрачностью иначе получился бы чёрный
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, width, height);
  context.drawImage(image, 0, 0, width, height);

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("Браузер не смог сжать фото."))),
      "image/jpeg",
      JPEG_QUALITY,
    );
  });
}
