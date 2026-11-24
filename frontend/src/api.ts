import type { Campaign, KtCampaign, Meta, Offer, PushResult, Stream } from './types'

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const response = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (response.status === 204) return undefined as T
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    const error = data?.error
    throw new ApiError(response.status, error?.code ?? 'error', error?.message ?? response.statusText)
  }
  return data as T
}

export const api = {
  meta: () => request<Meta>('GET', '/api/meta'),
  searchOffers: (q: string) =>
    request<Offer[]>('GET', `/api/offers/search?limit=15&q=${encodeURIComponent(q)}`),
  keitaroCampaigns: () => request<KtCampaign[]>('GET', '/api/keitaro/campaigns'),
  createCampaign: (body: {
    name: string
    geo: string
    offer_ids: number[]
    domain_id: number | null
    group_id: number | null
    traffic_source_id: number | null
  }) => request<Campaign>('POST', '/api/creator/campaigns', body),
  importCampaign: (kt_id: number) => request<Campaign>('POST', '/api/campaigns/import', { kt_id }),
  campaign: (id: number) => request<Campaign>('GET', `/api/campaigns/${id}`),
  fetchCampaign: (id: number) => request<Campaign>('POST', `/api/campaigns/${id}/fetch`),
  pushCampaign: (id: number, force = false) =>
    request<{ results: PushResult[]; campaign: Campaign }>(
      'POST',
      `/api/campaigns/${id}/push${force ? '?force=true' : ''}`,
    ),
  addOffer: (streamId: number, offerId: number) =>
    request<Stream>('POST', `/api/streams/${streamId}/offers`, { offer_id: offerId }),
  removeOffer: (streamId: number, linkId: number) =>
    request<Stream>('POST', `/api/streams/${streamId}/offers/${linkId}/remove`),
  restoreOffer: (streamId: number, linkId: number) =>
    request<Stream>('POST', `/api/streams/${streamId}/offers/${linkId}/restore`),
  updateOffer: (streamId: number, linkId: number, body: { pinned?: boolean; share?: number }) =>
    request<Stream>('PATCH', `/api/streams/${streamId}/offers/${linkId}`, body),
  rebalance: (streamId: number) => request<Stream>('POST', `/api/streams/${streamId}/rebalance`),
  cancel: (streamId: number) => request<Stream>('POST', `/api/streams/${streamId}/cancel`),
  push: (streamId: number, force = false) =>
    request<{ result: PushResult; stream: Stream }>(
      'POST',
      `/api/streams/${streamId}/push${force ? '?force=true' : ''}`,
    ),
}
