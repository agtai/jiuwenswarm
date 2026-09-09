import type { GoalAction, GoalControlTarget, GoalRecord } from '../types/goal';

/** Capture what the user observed; never substitute the execution revision. */
export function captureGoalTarget(
  sessionId: string,
  goal: Pick<GoalRecord, 'session_id' | 'goal_id' | 'control_revision'> | null | undefined,
): GoalControlTarget {
  if (
    !goal ||
    !sessionId ||
    goal.session_id !== sessionId ||
    !goal.goal_id ||
    goal.goal_id.trim() !== goal.goal_id ||
    typeof goal.control_revision !== 'number' ||
    !Number.isSafeInteger(goal.control_revision) ||
    (goal.control_revision ?? 0) < 1
  ) {
    throw new Error('Goal state is unavailable. Refresh the goal before controlling it.');
  }
  return { session_id: sessionId, goal_id: goal.goal_id, control_revision: goal.control_revision };
}

export interface GoalCommandParams {
  sessionId: string;
  action: GoalAction | 'get';
  objective?: string;
  mode?: string;
  target?: GoalControlTarget;
}

export function goalCommandPayload({ sessionId, action, objective, mode, target }: GoalCommandParams) {
  const control = action === 'get' || (action === 'set' && target === undefined) ? undefined : captureGoalTarget(sessionId, target);
  return {
    session_id: sessionId,
    action,
    mode: mode ?? 'agent',
    ...(control ? { expected_goal_id: control.goal_id, expected_control_revision: control.control_revision } : {}),
    ...(action === 'set' ? { objective, overwrite_confirmed: control !== undefined } : {}),
  };
}
