export function productTaskProgressTranslationKey(state: string):
  | 'liveVoice.formal.taskStateAccepted'
  | 'liveVoice.formal.taskStateRunning'
  | 'liveVoice.formal.taskState' {
  if (state === 'accepted') return 'liveVoice.formal.taskStateAccepted';
  if (state === 'running') return 'liveVoice.formal.taskStateRunning';
  return 'liveVoice.formal.taskState';
}
