"use client";

import { useCallback, useState, type FormEvent } from "react";
import { Badge, Button, Card, ErrorBanner, Loading, PageHeader, SuccessNotice, TextField } from "@/components/ui";
import type { Tone } from "@/components/ui";
import { getErrorText } from "@/lib/api";
import {
  changeMemberRole,
  createHousehold,
  createHouseholdInvite,
  deleteHouseholdInvite,
  getHouseholdInvites,
  getHouseholdMembers,
  getHouseholds,
  joinHousehold,
  removeHouseholdMember,
} from "@/lib/endpoints";
import { formatDateTime, formatShortDate } from "@/lib/format";
import { useProfile } from "@/lib/profile-context";
import type { HouseholdInvite, HouseholdMember, HouseholdRole, UserHousehold } from "@/lib/types";
import { useAsyncData } from "@/lib/use-async-data";

const ROLE_LABELS: Record<HouseholdRole, string> = {
  owner: "Владелец",
  admin: "Администратор",
  member: "Участник",
};

const ROLE_TONES: Record<HouseholdRole, Tone> = {
  owner: "green",
  admin: "amber",
  member: "slate",
};

/** Код для показа: "K7M29QXP" → "K7M2-9QXP". */
function formatInviteCode(code: string): string {
  return `${code.slice(0, 4)}-${code.slice(4)}`;
}

/** Страница «Семья»: мои домохозяйства, участники, приглашения, создание и вступление. */
export default function FamilyPage() {
  // getHouseholds объявлена вне компонента, поэтому её можно передавать как есть
  const { data: households, loading, error, reload } = useAsyncData(getHouseholds);

  return (
    <>
      <PageHeader title="Семья" subtitle="Домохозяйства, участники и приглашения" />

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {loading && households === null && <Loading />}

      {households && (
        <div className="space-y-6">
          {households.length === 0 && (
            <Card>
              <p className="text-sm text-slate-600">
                Вы пока не состоите ни в одном домохозяйстве. Создайте своё или присоединитесь
                по коду приглашения. Без домохозяйства семейные финансы недоступны.
              </p>
            </Card>
          )}

          {households.map((household) => (
            <HouseholdCard key={household.id} household={household} onChanged={reload} />
          ))}

          <div className="grid gap-6 lg:grid-cols-2">
            <CreateHouseholdCard onDone={reload} />
            <JoinHouseholdCard onDone={reload} />
          </div>
        </div>
      )}
    </>
  );
}

/** Форма создания домохозяйства. Создатель становится владельцем. */
function CreateHouseholdCard({ onDone }: { onDone: () => void }) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /** Отправляет название на backend. Пример: name = "Дом" → POST /households {"name": "Дом"}. */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Введите название, например «Дом».");
      return;
    }
    setError(null);
    setSaving(true);
    try {
      await createHousehold(trimmed);
      setName("");
      onDone();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Создать домохозяйство">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-slate-500">
          Вы станете владельцем и сможете пригласить близких по коду.
        </p>
        <TextField label="Название" value={name} onChange={setName} maxLength={100} placeholder="Например, Дом" />
        <Button type="submit" loading={saving}>
          Создать
        </Button>
        {error && <ErrorBanner message={error} />}
      </form>
    </Card>
  );
}

/** Форма вступления в домохозяйство по коду приглашения. */
function JoinHouseholdCard({ onDone }: { onDone: () => void }) {
  const [code, setCode] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [joinedName, setJoinedName] = useState<string | null>(null);

  /** Отправляет код. Пример: code = "k7m2-9qxp" → POST /households/join {"code": "k7m2-9qxp"}. */
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!code.trim()) {
      setError("Введите код приглашения.");
      return;
    }
    setError(null);
    setJoinedName(null);
    setSaving(true);
    try {
      const household = await joinHousehold(code);
      setJoinedName(household.name);
      setCode("");
      onDone();
    } catch (err) {
      setError(getErrorText(err));
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Присоединиться по коду">
      <form onSubmit={handleSubmit} className="space-y-4">
        <p className="text-sm text-slate-500">
          Код вам присылает владелец или администратор домохозяйства. Он одноразовый и действует 7 дней.
        </p>
        <TextField
          label="Код приглашения"
          value={code}
          onChange={setCode}
          placeholder="K7M2-9QXP"
          autoCapitalize="characters"
          autoComplete="off"
        />
        <Button type="submit" loading={saving}>
          Присоединиться
        </Button>
        {error && <ErrorBanner message={error} />}
        {joinedName && <SuccessNotice message={`Готово! Вы присоединились к домохозяйству «${joinedName}».`} />}
      </form>
    </Card>
  );
}

/** Карточка одного домохозяйства: участники и (для владельца/администратора) приглашения. */
function HouseholdCard({ household, onChanged }: { household: UserHousehold; onChanged: () => void }) {
  const { profile } = useProfile();
  const isOwner = household.role === "owner";
  const canManage = isOwner || household.role === "admin";

  // Участники загружаются отдельно для каждой карточки
  const loadMembers = useCallback(() => getHouseholdMembers(household.id), [household.id]);
  const { data: members, error: membersError, reload: reloadMembers } = useAsyncData(loadMembers);

  const [actionError, setActionError] = useState<string | null>(null);
  // id участника, над которым сейчас выполняется действие (блокирует его кнопки)
  const [busyUserId, setBusyUserId] = useState<number | null>(null);

  /** Выполняет действие над участником; при ошибке показывает её, при успехе вызывает afterSuccess. */
  async function runAction(userId: number, action: () => Promise<unknown>, afterSuccess: () => void) {
    setActionError(null);
    setBusyUserId(userId);
    try {
      await action();
      afterSuccess();
    } catch (err) {
      setActionError(getErrorText(err));
    } finally {
      setBusyUserId(null);
    }
  }

  /** Назначает роль. Пример: (2, "admin") → PATCH /households/1/members/2 {"role": "admin"}. */
  function handleRoleChange(userId: number, role: "admin" | "member") {
    void runAction(userId, () => changeMemberRole(household.id, userId, role), reloadMembers);
  }

  /** Удаляет участника или выводит из семьи вас самого (после подтверждения). */
  function handleRemove(member: HouseholdMember) {
    const isSelf = member.user_id === profile.id;
    const question = isSelf
      ? `Покинуть домохозяйство «${household.name}»?`
      : `Удалить участника ${member.name} из «${household.name}»?`;
    if (!window.confirm(question)) return;
    // Если вышли сами, карточка исчезнет, поэтому обновляем весь список семей
    void runAction(member.user_id, () => removeHouseholdMember(household.id, member.user_id), isSelf ? onChanged : reloadMembers);
  }

  /** Можно ли текущему пользователю удалить этого участника (те же правила, что на backend). */
  function canRemove(target: HouseholdMember): boolean {
    if (target.role === "owner") return false;
    if (target.user_id === profile.id) return true;
    if (isOwner) return true;
    return household.role === "admin" && target.role === "member";
  }

  return (
    <Card
      title={household.name}
      action={<Badge tone={ROLE_TONES[household.role]}>Ваша роль: {ROLE_LABELS[household.role].toLowerCase()}</Badge>}
    >
      {membersError && <ErrorBanner message={membersError} onRetry={reloadMembers} />}
      {members === null && !membersError && <Loading />}

      {members && (
        <ul className="divide-y divide-slate-100">
          {members.map((member) => {
            const isSelf = member.user_id === profile.id;
            const busy = busyUserId === member.user_id;
            return (
              <li key={member.user_id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div>
                  <p className="font-medium">
                    {member.name}
                    {isSelf && " (вы)"}
                  </p>
                  <p className="text-xs text-slate-500">С {formatShortDate(member.joined_at.slice(0, 10))}</p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={ROLE_TONES[member.role]}>{ROLE_LABELS[member.role]}</Badge>
                  {isOwner && member.role !== "owner" && (
                    <Button
                      variant="secondary"
                      loading={busy}
                      onClick={() => handleRoleChange(member.user_id, member.role === "admin" ? "member" : "admin")}
                    >
                      {member.role === "admin" ? "Сделать участником" : "Сделать администратором"}
                    </Button>
                  )}
                  {canRemove(member) && (
                    <Button variant="danger" loading={busy} onClick={() => handleRemove(member)}>
                      {isSelf ? "Покинуть" : "Удалить"}
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {actionError && (
        <div className="mt-4">
          <ErrorBanner message={actionError} />
        </div>
      )}

      {canManage && <InvitesSection householdId={household.id} />}
    </Card>
  );
}

/** Блок приглашений: создать код, скопировать, отозвать. Виден владельцу и администратору. */
function InvitesSection({ householdId }: { householdId: number }) {
  const loadInvites = useCallback(() => getHouseholdInvites(householdId), [householdId]);
  const { data: invites, error, reload } = useAsyncData(loadInvites);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  // id кода, который только что скопировали (для подписи «Скопировано»)
  const [copiedId, setCopiedId] = useState<number | null>(null);

  /** Создаёт новый код и обновляет список. */
  async function handleCreate() {
    setActionError(null);
    setBusy(true);
    try {
      await createHouseholdInvite(householdId);
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    } finally {
      setBusy(false);
    }
  }

  /** Отзывает код. Пример: inviteId = 5 → DELETE /households/1/invites/5. */
  async function handleRevoke(inviteId: number) {
    setActionError(null);
    try {
      await deleteHouseholdInvite(householdId, inviteId);
      reload();
    } catch (err) {
      setActionError(getErrorText(err));
    }
  }

  /** Копирует код в буфер обмена. Без HTTPS на телефоне браузер может не разрешить. */
  async function handleCopy(invite: HouseholdInvite) {
    try {
      await navigator.clipboard.writeText(invite.code);
      setCopiedId(invite.id);
    } catch {
      setActionError("Не удалось скопировать автоматически. Выделите код и скопируйте вручную.");
    }
  }

  return (
    <div className="mt-6 border-t border-slate-100 pt-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="font-bold">Приглашения</h3>
        <Button onClick={handleCreate} loading={busy}>
          Создать код
        </Button>
      </div>
      <p className="mb-4 text-sm text-slate-500">
        Код одноразовый и действует 7 дней. Отправьте его близкому: он вводит код на этой странице в блоке
        «Присоединиться по коду».
      </p>

      {error && <ErrorBanner message={error} onRetry={reload} />}
      {invites && invites.length === 0 && <p className="text-sm text-slate-500">Действующих кодов нет.</p>}

      {invites && invites.length > 0 && (
        <ul className="space-y-2">
          {invites.map((invite) => (
            <li key={invite.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-slate-50 px-4 py-3">
              <div>
                <code className="font-mono text-lg font-bold tracking-widest">{formatInviteCode(invite.code)}</code>
                <p className="text-xs text-slate-500">Действует до {formatDateTime(invite.expires_at)}</p>
              </div>
              <div className="flex items-center gap-2">
                {copiedId === invite.id && <span className="text-xs text-emerald-700">Скопировано</span>}
                <Button variant="secondary" onClick={() => handleCopy(invite)}>
                  Копировать
                </Button>
                <Button variant="danger" onClick={() => handleRevoke(invite.id)}>
                  Отозвать
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {actionError && (
        <div className="mt-4">
          <ErrorBanner message={actionError} />
        </div>
      )}
    </div>
  );
}