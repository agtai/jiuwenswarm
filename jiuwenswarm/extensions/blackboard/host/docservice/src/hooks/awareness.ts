// Carets show who a person is to the host, whatever their browser claims: the service stamps the
// token's user id and name onto every awareness state a person's connection sends, and a person
// can never appear as an agent.
export function stampAwareness({ states, context }: { states: Map<number, Record<string, any>>; context: any }): void {
  if (!context || context.kind !== 'person' || typeof context.userId !== 'string') return
  for (const [clientId, state] of states) {
    // Hocuspocus decodes into a scratch awareness whose own empty state is in the map too.
    if (!state || typeof state !== 'object' || Object.keys(state).length === 0) continue
    states.set(clientId, { ...state, user: { id: context.userId, name: String(context.name ?? '') } })
  }
}
