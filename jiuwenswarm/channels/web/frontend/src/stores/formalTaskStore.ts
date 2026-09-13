import { create } from 'zustand';
import type { FormalP3TaskExperienceOwner, FormalP3TaskExperienceSnapshot } from '../features/tasks/formalP3TaskExperience';
import type { FormalP3TaskRecord } from '../features/tasks/formalP3TaskExperience';

export type FormalTaskEntry = Readonly<{
  owner: FormalP3TaskExperienceOwner;
  snapshot: FormalP3TaskExperienceSnapshot;
}>;

export function selectScopedFormalTasks(
  snapshot: FormalP3TaskExperienceSnapshot,
  sessionId: string,
  projectId?: string,
): readonly FormalP3TaskRecord[] {
  if (snapshot.session_id !== sessionId) return [];
  const sessionTasks = snapshot.tasks.filter(task => task.session_id === sessionId);
  const projectIds = [...new Set(sessionTasks.map(task => task.project_id))];
  const scopedProjectId = projectId ?? (projectIds.length === 1 ? projectIds[0] : undefined);
  if (!scopedProjectId) return [];
  return sessionTasks.filter(task => task.project_id === scopedProjectId);
}

// A view of the existing Registry reader. Never persists a second Task or Todo.
export const useFormalTaskStore = create<{
  entries: Record<string, FormalTaskEntry>;
  bind: (session: string, owner: FormalP3TaskExperienceOwner) => void;
  publish: (session: string, owner: FormalP3TaskExperienceOwner, snapshot: FormalP3TaskExperienceSnapshot) => void;
  release: (session: string, owner: FormalP3TaskExperienceOwner) => void;
}>((set) => ({
  entries: {},
  bind: (session, owner) => set(state => ({ entries: { ...state.entries, [session]: { owner, snapshot: owner.snapshot() } } })),
  publish: (session, owner, snapshot) => set(state => {
    if (state.entries[session]?.owner !== owner || snapshot.session_id !== session) return state;
    return { entries: { ...state.entries, [session]: { owner, snapshot } } };
  }),
  release: (session, owner) => set(state => {
    if (state.entries[session]?.owner !== owner) return state;
    const entries = { ...state.entries };
    delete entries[session];
    return { entries };
  }),
}));
