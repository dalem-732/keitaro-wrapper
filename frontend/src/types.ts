export type OfferStatus = 'active' | 'archived'
export type OfferBadge = 'active' | 'new' | 'removed_pending' | 'restored_pending' | 'archived'

export interface Named {
  id: number
  name: string
}

export interface Offer extends Named {
  country: string[]
}

export interface Meta {
  domains: Named[]
  groups: Named[]
  traffic_sources: Named[]
  defaults: { domain_id: number | null; group_id: number | null; traffic_source_id: number | null }
  campaign_name_prefix: string
  write_allowed_prefix: string
  keitaro_admin_url: string
  countries: Record<string, string>
}

export interface StreamOffer {
  id: number
  offer_id: number
  offer_name: string
  status: OfferStatus
  share: number
  pinned: boolean
  published_status: OfferStatus | null
  published_share: number | null
  is_dirty: boolean
  badge: OfferBadge
}

export interface Issue {
  code: string
  message: string
}

export interface Stream {
  id: number
  kt_id: number
  name: string
  position: number
  type: string | null
  schema: string | null
  accepts_offers: boolean
  is_dirty: boolean
  issues: Issue[]
  active_share_sum: number
  last_pushed_at: string | null
  offers: StreamOffer[]
}

export interface Campaign {
  id: number
  kt_id: number
  name: string
  alias: string | null
  domain: string | null
  group_name: string | null
  last_fetched_at: string | null
  writable: boolean
  keitaro_url: string
  streams: Stream[]
}

export interface KtCampaign {
  kt_id: number
  name: string
  domain: string | null
  group: string | null
  state: string | null
  local_id: number | null
}

export interface PushResult {
  stream_id: number
  changed: boolean
  message: string
}
