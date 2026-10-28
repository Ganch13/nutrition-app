"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Badge, Button, Card, ErrorBanner, Loading, SelectField, SuccessNotice, TextField } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import {
  deleteProgressPhoto,
  getProgressPhotoFile,
  getProgressPhotos,
  getWeightRecords,
  updateProgressPhoto,
  uploadProgressPhoto,
} from "@/lib/endpoints";
import { formatNumber, formatShortDate, optionalText, PHOTO_ANGLE_LABELS, toOptions } from "@/lib/format";
import { prepareImage } from "@/lib/image";
import type { PhotoAngle, ProgressPhoto, WeightRecord } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

// ---------- Загрузка картинок с токеном ----------

// Уже скачанные фото: адрес на сервере → адрес объекта в памяти браузера (blob:...).
// Хранится не больше CACHE_LIMIT штук; самые старые освобождаются.
const CACHE_LIMIT = 60;
const imageCache = new Map<string, string>();

/** Возвращает адрес объекта для фото, скачивая его при первом обращении. */
async function loadPhotoUrl(serverUrl: string): Promise<string> {
  const cached = imageCache.get(serverUrl);
  if (cached) {
    // Перекладываем в конец: недавно использованное освобождается последним
    imageCache.delete(serverUrl);
    imageCache.set(serverUrl, cached);
    return cached;
  }
  const blob = await getProgressPhotoFile(serverUrl);
  const objectUrl = URL.createObjectURL(blob);
  imageCache.set(serverUrl, objectUrl);
  if (imageCache.size > CACHE_LIMIT) {
    const oldest = imageCache.keys().next().value;
    if (oldest !== undefined) {
      URL.revokeObjectURL(imageCache.get(oldest)!);
      imageCache.delete(oldest);
    }
  }
  return objectUrl;
}

/** Картинка, которой нужен токен. Скачивается, когда блок появляется на экране. */
function AuthImage({
  serverUrl,
  alt,
  className,
  fit = "cover",
}: {
  serverUrl: string;
  alt: string;
  className?: string;
  // cover — заполнить рамку с обрезкой краёв (миниатюры); contain — показать фото целиком (крупный просмотр)
  fit?: "cover" | "contain";
}) {
  const holder = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  // Ждём, пока блок окажется рядом с видимой областью: так страница с сотней фото не качает всё сразу
  useEffect(() => {
    const node = holder.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    loadPhotoUrl(serverUrl).then(
      (url) => {
        if (!cancelled) setSrc(url);
      },
      () => {
        if (!cancelled) setFailed(true);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [visible, serverUrl]);

  return (
    <div ref={holder} className={`flex items-center justify-center bg-slate-100 ${className ?? ""}`}>
      {src ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={src} alt={alt} className={`h-full w-full ${fit === "contain" ? "object-contain" : "object-cover"}`} />
      ) : (
        <span className="px-2 text-center text-xs text-slate-400">{failed ? "Фото недоступно" : "Загрузка..."}</span>
      )}
    </div>
  );
}

// ---------- Вспомогательные расчёты ----------

/** Вес на дату: последняя запись не позже этой даты. Пример: записи 10.10 и 20.10, дата 15.10 → запись 10.10. */
function weightOnDate(records: WeightRecord[], date: string): number | null {
  let best: WeightRecord | null = null;
  for (const record of records) {
    if (record.measurement_date <= date && (best === null || record.measurement_date > best.measurement_date)) {
      best = record;
    }
  }
  return best ? Number(best.weight_kg) : null;
}

/** Число дней между датами: ("2026-09-01", "2026-10-01") → 30. */
function daysBetween(from: string, to: string): number {
  return Math.round((new Date(`${to}T00:00:00Z`).getTime() - new Date(`${from}T00:00:00Z`).getTime()) / 86_400_000);
}

/** Подпись изменения веса: −3,2 кг / +0,5 кг. */
function formatDelta(kg: number): string {
  const sign = kg > 0 ? "+" : kg < 0 ? "−" : "";
  return `${sign}${formatNumber(Math.abs(kg), 1)} кг`;
}

// ---------- Блок «Фото прогресса» ----------

/** Блок «Фото прогресса»: загрузка, галерея по датам, просмотр, сравнение двух снимков. */
export default function ProgressPhotos({ userId, today }: { userId: number; today: string }) {
  const loadPhotos = useCallback(() => getProgressPhotos(userId), [userId]);
  const loadWeights = useCallback(() => getWeightRecords(userId), [userId]);
  const photos = useAsyncData(loadPhotos);
  const weights = useAsyncData(loadWeights);

  const [angleFilter, setAngleFilter] = useState<"all" | PhotoAngle>("all");
  const [openId, setOpenId] = useState<number | null>(null);
  // Фото, выбранные для сравнения (не больше двух, в порядке выбора)
  const [compareIds, setCompareIds] = useState<number[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  const all = photos.data ?? [];
  const visible = angleFilter === "all" ? all : all.filter((photo) => photo.angle === angleFilter);
  const weightRecords = weights.data ?? [];
  const opened = all.find((photo) => photo.id === openId) ?? null;

  function toggleCompare(photoId: number) {
    setCompareIds((current) => {
      if (current.includes(photoId)) return current.filter((id) => id !== photoId);
      // Третье фото заменяет самое раннее из выбранных
      return current.length >= 2 ? [current[1], photoId] : [...current, photoId];
    });
  }

  const compared = compareIds
    .map((id) => all.find((photo) => photo.id === id))
    .filter((photo): photo is ProgressPhoto => photo !== undefined)
    // Слева более раннее фото, справа более позднее
    .sort((a, b) => (a.taken_on === b.taken_on ? a.id - b.id : a.taken_on < b.taken_on ? -1 : 1));

  return (
    <div className="space-y-6">
      <UploadCard
        userId={userId}
        today={today}
        onUploaded={() => {
          setMessage("Фото добавлено.");
          photos.reload();
        }}
      />

      {message && <SuccessNotice message={message} />}
      {photos.error && <ErrorBanner message={photos.error} onRetry={photos.reload} />}
      {photos.loading && photos.data === null && <Loading />}

      {compared.length === 2 && (
        <CompareCard
          before={compared[0]}
          after={compared[1]}
          weightBefore={weightOnDate(weightRecords, compared[0].taken_on)}
          weightAfter={weightOnDate(weightRecords, compared[1].taken_on)}
          onClose={() => setCompareIds([])}
        />
      )}

      {photos.data && (
        <Card
          title="Галерея"
          action={
            <div className="w-44">
              <SelectField
                label="Ракурс"
                value={angleFilter}
                onChange={(value) => setAngleFilter(value as "all" | PhotoAngle)}
                options={[["all", "Все"], ...toOptions(PHOTO_ANGLE_LABELS)]}
              />
            </div>
          }
        >
          {visible.length === 0 ? (
            <p className="text-sm text-slate-600">
              {all.length === 0
                ? "Фото пока нет. Делайте снимок раз в одну-две недели в одинаковых условиях: тот же свет, место и время дня."
                : "Нет фото с таким ракурсом."}
            </p>
          ) : (
            <>
              <p className="mb-3 text-xs text-slate-500">
                Отметьте два снимка галочкой «Сравнить» — они откроются рядом. Нажмите на фото, чтобы увеличить его.
              </p>
              <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {visible.map((photo) => (
                  <li key={photo.id} className="overflow-hidden rounded-xl border border-slate-200">
                    <button type="button" onClick={() => setOpenId(photo.id)} className="block w-full">
                      <AuthImage
                        serverUrl={photo.url}
                        alt={`Фото от ${formatShortDate(photo.taken_on)}`}
                        className="aspect-[3/4] w-full"
                      />
                    </button>
                    <div className="space-y-1 px-2 py-2 text-xs">
                      <p className="font-medium text-slate-700">{formatShortDate(photo.taken_on)}</p>
                      <p className="text-slate-500">
                        {PHOTO_ANGLE_LABELS[photo.angle]}
                        {(() => {
                          const kg = weightOnDate(weightRecords, photo.taken_on);
                          return kg === null ? "" : ` · ${formatNumber(kg, 1)} кг`;
                        })()}
                      </p>
                      <label className="flex items-center gap-1.5 text-slate-600">
                        <input
                          type="checkbox"
                          checked={compareIds.includes(photo.id)}
                          onChange={() => toggleCompare(photo.id)}
                        />
                        Сравнить
                      </label>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}

      {opened && (
        <PhotoViewer
          key={opened.id}
          userId={userId}
          photo={opened}
          weight={weightOnDate(weightRecords, opened.taken_on)}
          today={today}
          onClose={() => setOpenId(null)}
          onChanged={() => photos.reload()}
          onDeleted={() => {
            setOpenId(null);
            setCompareIds((current) => current.filter((id) => id !== opened.id));
            setMessage("Фото удалено.");
            photos.reload();
          }}
        />
      )}
    </div>
  );
}

/** Форма загрузки: выбор файла, уменьшение в браузере, отправка. */
function UploadCard({ userId, today, onUploaded }: { userId: number; today: string; onUploaded: () => void }) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [takenOn, setTakenOn] = useState(today);
  const [angle, setAngle] = useState<PhotoAngle>("front");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) return;
    setSaving(true);
    setError(null);
    try {
      // Сначала уменьшаем: на телефоне это превращает 5 МБ в 300 КБ и ускоряет загрузку
      const prepared = await prepareImage(file);
      await uploadProgressPhoto(userId, prepared, takenOn, angle, optionalText(note));
      setFile(null);
      setNote("");
      if (fileInput.current) fileInput.current.value = "";
      onUploaded();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Добавить фото">
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <ErrorBanner message={error} />}
        <label className="block space-y-1.5">
          <span className="text-sm font-medium text-slate-700">Файл</span>
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            className="block w-full text-sm text-slate-700 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <TextField label="Дата съёмки" type="date" value={takenOn} max={today} onChange={setTakenOn} required />
          <SelectField
            label="Ракурс"
            value={angle}
            onChange={(value) => setAngle(value as PhotoAngle)}
            options={toOptions(PHOTO_ANGLE_LABELS)}
          />
        </div>
        <TextField label="Подпись (необязательно)" value={note} maxLength={300} onChange={setNote} />
        <p className="text-xs text-slate-500">
          Фото уменьшается на вашем устройстве, метаданные (в том числе место съёмки) удаляются. Видите его только вы.
        </p>
        <Button type="submit" loading={saving} disabled={!file}>
          {saving ? "Загружаем..." : "Загрузить"}
        </Button>
      </form>
    </Card>
  );
}

/** Сравнение «было — стало»: два снимка рядом, разница по дням и по весу. */
function CompareCard({
  before,
  after,
  weightBefore,
  weightAfter,
  onClose,
}: {
  before: ProgressPhoto;
  after: ProgressPhoto;
  weightBefore: number | null;
  weightAfter: number | null;
  onClose: () => void;
}) {
  const days = daysBetween(before.taken_on, after.taken_on);
  return (
    <Card title="Сравнение" action={<Button variant="secondary" onClick={onClose}>Закрыть</Button>}>
      <p className="mb-3 text-sm text-slate-600">
        Между снимками: {days} дн.
        {weightBefore !== null && weightAfter !== null && <> · вес {formatDelta(weightAfter - weightBefore)}</>}
        {before.angle !== after.angle && (
          <span className="ml-2 text-amber-700">Ракурсы разные — для честного сравнения берите один и тот же.</span>
        )}
      </p>
      <div className="grid grid-cols-2 gap-3">
        {[
          { photo: before, weight: weightBefore, title: "Было" },
          { photo: after, weight: weightAfter, title: "Стало" },
        ].map(({ photo, weight, title }) => (
          <figure key={photo.id}>
            <AuthImage
              serverUrl={photo.url}
              alt={`${title}: ${formatShortDate(photo.taken_on)}`}
              className="aspect-[3/4] w-full overflow-hidden rounded-xl"
            />
            <figcaption className="mt-2 text-sm">
              <span className="font-medium">{title}</span> · {formatShortDate(photo.taken_on)}
              {weight !== null && <> · {formatNumber(weight, 1)} кг</>}
            </figcaption>
          </figure>
        ))}
      </div>
    </Card>
  );
}

/** Окно просмотра одного фото: крупная картинка, правка даты/ракурса/подписи, удаление. */
function PhotoViewer({
  userId,
  photo,
  weight,
  today,
  onClose,
  onChanged,
  onDeleted,
}: {
  userId: number;
  photo: ProgressPhoto;
  weight: number | null;
  today: string;
  onClose: () => void;
  onChanged: () => void;
  onDeleted: () => void;
}) {
  const [takenOn, setTakenOn] = useState(photo.taken_on);
  const [angle, setAngle] = useState<PhotoAngle>(photo.angle);
  const [note, setNote] = useState(photo.note ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Esc закрывает окно
  useEffect(() => {
    function handleKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [onClose]);

  async function handleSave() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await updateProgressPhoto(userId, photo.id, { taken_on: takenOn, angle, note: optionalText(note) });
      setSaved(true);
      onChanged();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Удалить это фото безвозвратно?")) return;
    setBusy(true);
    setError(null);
    try {
      await deleteProgressPhoto(userId, photo.id);
      onDeleted();
    } catch (err) {
      setError(getErrorText(err));
      setBusy(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Просмотр фото"
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 sm:items-center sm:p-6"
      onClick={onClose}
    >
      <div
        className="max-h-full w-full max-w-3xl overflow-y-auto rounded-t-2xl bg-white p-4 sm:rounded-2xl sm:p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-bold">{formatShortDate(photo.taken_on)}</h3>
            <Badge>{PHOTO_ANGLE_LABELS[photo.angle]}</Badge>
            {weight !== null && <Badge tone="green">{formatNumber(weight, 1)} кг</Badge>}
          </div>
          <Button variant="secondary" onClick={onClose}>
            Закрыть
          </Button>
        </div>

        <AuthImage
          serverUrl={photo.url}
          alt={`Фото от ${formatShortDate(photo.taken_on)}`}
          fit="contain"
          className="mx-auto aspect-[3/4] w-full max-w-sm overflow-hidden rounded-xl"
        />

        <div className="mt-4 space-y-3">
          {error && <ErrorBanner message={error} />}
          {saved && <SuccessNotice message="Сохранено." />}
          <div className="grid gap-3 sm:grid-cols-2">
            <TextField label="Дата съёмки" type="date" value={takenOn} max={today} onChange={setTakenOn} required />
            <SelectField
              label="Ракурс"
              value={angle}
              onChange={(value) => setAngle(value as PhotoAngle)}
              options={toOptions(PHOTO_ANGLE_LABELS)}
            />
          </div>
          <TextField label="Подпись" value={note} maxLength={300} onChange={setNote} />
          <div className="flex flex-wrap gap-2">
            <Button onClick={handleSave} loading={busy}>
              Сохранить
            </Button>
            <Button variant="danger" onClick={handleDelete} disabled={busy}>
              Удалить
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
