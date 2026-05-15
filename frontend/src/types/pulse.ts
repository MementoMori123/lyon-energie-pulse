export interface PulseResponse {
  city: string
  timestamp: string
  renewables_timestamp?: string | null
  story?: string
  freshness?: {
    metro_slot_age_hours: number | null
    renewables_slot_age_hours: number | null
    metro_stale: boolean
    renewables_stale: boolean
    trailing_null_slots: number
  }
  metrics: {
    consumption_mw: number
    regional_renewables_mw: number | null
    physical_exchanges_mw: number | null
  }
  breakdown: {
    solar: number | null
    biomass: number | null
    wind: number | null
  }
  source: string
  odre: {
    nature?: string | null
    production?: string | null
  }
  mapping: {
    consumption_dataset: string
    consumption_geo: string
    renewables_dataset: string
    renewables_geo: string
    join_key: string
    regional_row_matched: boolean
    renewables_same_slot_as_metro?: boolean
  }
}
