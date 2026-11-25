import type { ChatMetadata } from './api'

export type ChatItem =
  | { id: string; kind: 'user'; content: string }
  | { id: string; kind: 'assistant'; content: string; metadata: ChatMetadata }
  | { id: string; kind: 'error'; message: string; status: number | null; retryText: string; retried?: boolean }

export const FAILURE_PRESETS = ['key_1=429', 'key_1=500', 'key_1=429,key_2=500', '*=429'] as const
