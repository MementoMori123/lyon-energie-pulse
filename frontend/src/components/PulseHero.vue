<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { fetchPulse } from '../api/pulse'
import type { PulseResponse } from '../types/pulse'

const data = ref<PulseResponse | null>(null)
const loading = ref(true)
const refreshing = ref(false)
const error = ref<string | null>(null)
const lastUpdated = ref<Date | null>(null)

// Vérifie périodiquement si ODRE a publié un nouveau créneau (pas du temps réel).
const POLL_MS = 60_000

let timer: ReturnType<typeof setInterval> | undefined

const prevSlotKey = ref<string | null>(null)
const slotChanged = ref(false)
const pollCount = ref(0)

async function load() {
  const initial = !data.value
  if (initial) loading.value = true
  else refreshing.value = true
  error.value = null
  try {
    const next = await fetchPulse()
    const slotKey = `${next.timestamp}|${next.metrics.consumption_mw}`
    slotChanged.value =
      prevSlotKey.value !== null && prevSlotKey.value !== slotKey
    prevSlotKey.value = slotKey
    pollCount.value += 1
    data.value = next
    lastUpdated.value = new Date()
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function fmtOdreTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'Europe/Paris',
    }).format(d)
  } catch {
    return iso
  }
}

const fmtTime = computed(() => fmtOdreTime(data.value?.timestamp))
const fmtRenewablesTime = computed(() =>
  fmtOdreTime(data.value?.renewables_timestamp ?? data.value?.timestamp),
)

const staleDetail = computed(() => {
  const f = data.value?.freshness
  if (!f) return null
  const parts: string[] = []
  if (f.metro_slot_age_hours != null) {
    parts.push(`consommation · publiée il y a ~${f.metro_slot_age_hours} h`)
  }
  if (f.renewables_slot_age_hours != null) {
    parts.push(`EnR région · publiée il y a ~${f.renewables_slot_age_hours} h`)
  }
  if (f.trailing_null_slots > 0) {
    parts.push(
      `${f.trailing_null_slots} créneaux récents encore vides chez ODRE`,
    )
  }
  return parts.length ? parts.join(' · ') : null
})

const fmtMw = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return '—'
  if (v === 0) return '0'
  return new Intl.NumberFormat('fr-FR', {
    maximumFractionDigits: v >= 100 ? 0 : 1,
  }).format(v)
}

const barMax = computed(() => {
  const b = data.value?.breakdown
  if (!b) return 1
  const vals = [b.solar, b.biomass, b.wind].filter((x): x is number => x != null)
  const m = Math.max(1, ...vals)
  return m
})

function barPct(v: number | null | undefined): number {
  if (v == null) return 0
  return Math.min(100, (v / barMax.value) * 100)
}

const fmtLastFetched = computed(() => {
  if (!lastUpdated.value) return '—'
  return new Intl.DateTimeFormat('fr-FR', {
    timeStyle: 'medium',
    timeZone: 'Europe/Paris',
  }).format(lastUpdated.value)
})

onMounted(() => {
  void load()
  timer = setInterval(() => void load(), POLL_MS)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <div class="pulse">
    <header class="pulse__head">
      <p class="pulse__eyebrow">RTE / ODRE · éCO2mix</p>
      <h1 class="pulse__title">Dernier créneau publié</h1>
      <p class="pulse__tagline">Métropole de Lyon — pas une mesure «&nbsp;en direct&nbsp;»</p>
      <p class="pulse__sub">
        Vérification toutes les {{ POLL_MS / 1000 }}&nbsp;s si un nouveau créneau est disponible
        <span v-if="refreshing" class="pulse__sync">…</span>
        <button
          v-else-if="data"
          type="button"
          class="pulse__refresh"
          :disabled="refreshing"
          @click="load"
        >
          Vérifier ODRE
        </button>
      </p>
    </header>

    <section v-if="loading && !data" class="pulse__card pulse__card--muted">
      <p>Chargement…</p>
    </section>

    <section v-else-if="error" class="pulse__card pulse__card--error">
      <h2>Impossible de joindre l’API</h2>
      <p class="pulse__err">{{ error }}</p>
      <button type="button" class="pulse__btn" @click="load">Réessayer</button>
    </section>

    <template v-else-if="data">
      <div class="pulse__live" aria-live="polite">
        <section class="pulse__scope" aria-label="Périmètre des données">
          <h2 class="pulse__scope-title">Ce que montre cette page</h2>
          <ul class="pulse__scope-list">
            <li>
              <strong>Consommation</strong> — dernier créneau de 15&nbsp;min publié pour la
              {{ data.mapping.consumption_geo }} (ODRE ne remplit pas toujours les créneaux récents).
            </li>
            <li>
              <strong>EnR</strong> — solaire, éolien et biomasse pour la
              {{ data.mapping.renewables_geo }} (échelle régionale, pas la ville seule).
            </li>
            <li>
              Grille ODRE&nbsp;: un point toutes les 15&nbsp;min ; l’affichage n’avance que lorsque
              RTE publie la valeur.
            </li>
          </ul>
          <p v-if="staleDetail" class="pulse__stale" role="status">{{ staleDetail }}</p>
        </section>

        <section class="pulse__grid">
        <article class="pulse__card pulse__hero">
          <p class="pulse__label">Consommation publiée · {{ data.mapping.consumption_geo }}</p>
          <p
            class="pulse__mega"
            :class="{ 'pulse__mega--changed': slotChanged }"
            :key="`${data.timestamp}-${data.metrics.consumption_mw}`"
          >
            {{ fmtMw(data.metrics.consumption_mw) }}
            <span class="pulse__unit">MW</span>
          </p>
          <p class="pulse__meta">Créneau publié · {{ fmtTime }} (heure Paris)</p>
          <p class="pulse__meta pulse__meta--sub">
            Dernière vérification · {{ fmtLastFetched }}
            <span v-if="pollCount > 1 && !slotChanged"> · aucun créneau plus récent chez ODRE</span>
          </p>
          <p v-if="data.odre?.nature" class="pulse__tag">{{ data.odre.nature }}</p>
        </article>

        <article class="pulse__card">
          <p class="pulse__label">
            EnR publiés · {{ data.mapping.renewables_geo }}
          </p>
          <p class="pulse__meta">Créneau publié · {{ fmtRenewablesTime }} (heure Paris)</p>
          <p class="pulse__big">
            {{ fmtMw(data.metrics.regional_renewables_mw ?? null) }}
            <span class="pulse__unit">MW</span>
          </p>
          <p class="pulse__hint">Somme solaire + éolien + biomasse (région, créneau ci-dessus).</p>
        </article>
      </section>

      <section class="pulse__card pulse__bars">
        <h2 class="pulse__h2">Détail EnR publié (région)</h2>
        <div class="pulse__row">
          <span class="pulse__k">Solaire</span>
          <div class="pulse__track"><div class="pulse__fill solar" :style="{ width: barPct(data.breakdown.solar) + '%' }" /></div>
          <span class="pulse__v">{{ fmtMw(data.breakdown.solar ?? null) }}</span>
        </div>
        <div class="pulse__row">
          <span class="pulse__k">Biomasse</span>
          <div class="pulse__track"><div class="pulse__fill bio" :style="{ width: barPct(data.breakdown.biomass) + '%' }" /></div>
          <span class="pulse__v">{{ fmtMw(data.breakdown.biomass ?? null) }}</span>
        </div>
        <div class="pulse__row">
          <span class="pulse__k">Éolien</span>
          <div class="pulse__track"><div class="pulse__fill wind" :style="{ width: barPct(data.breakdown.wind) + '%' }" /></div>
          <span class="pulse__v">{{ fmtMw(data.breakdown.wind ?? null) }}</span>
        </div>
      </section>

      <section class="pulse__card pulse__extras">
        <div class="pulse__kv">
          <span>Échanges physiques (métropole)</span>
          <strong>{{ fmtMw(data.metrics.physical_exchanges_mw ?? null) }} MW</strong>
        </div>
        <div class="pulse__kv">
          <span>Production ODRE (métropole, brut)</span>
          <strong>{{ data.odre?.production ?? '—' }}</strong>
        </div>
        <div class="pulse__kv">
          <span>Source</span>
          <strong>{{ data.source }}</strong>
        </div>
      </section>

      <footer class="pulse__foot">
        <p>
          Jeux de données&nbsp;:
          <code>{{ data.mapping.consumption_dataset }}</code> (conso. métropole),
          <code>{{ data.mapping.renewables_dataset }}</code> (mix régional).
        </p>
      </footer>
      </div>
    </template>
  </div>
</template>

<style scoped>
.pulse {
  max-width: 42rem;
  margin: 0 auto;
  padding: 2rem 1.25rem 4rem;
  text-align: left;
}

.pulse__head {
  margin-bottom: 1.75rem;
}

.pulse__eyebrow {
  margin: 0;
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--muted);
}

.pulse__title {
  margin: 0.25rem 0 0;
  font-size: clamp(2.25rem, 6vw, 3rem);
  font-weight: 700;
  letter-spacing: -0.03em;
  color: var(--heading);
}

.pulse__tagline {
  margin: 0.35rem 0 0;
  font-size: 0.95rem;
  color: var(--muted);
}

.pulse__scope {
  margin-bottom: 1rem;
  padding: 1rem 1.1rem;
  border-radius: 0.75rem;
  border: 1px solid var(--border);
  background: rgba(255, 255, 255, 0.03);
}

.pulse__scope-title {
  margin: 0 0 0.6rem;
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--heading);
}

.pulse__scope-list {
  margin: 0;
  padding-left: 1.15rem;
  font-size: 0.8rem;
  line-height: 1.5;
  color: var(--muted);
}

.pulse__scope-list li + li {
  margin-top: 0.35rem;
}

.pulse__scope-list strong {
  color: var(--text);
  font-weight: 600;
}

.pulse__scope .pulse__stale {
  margin: 0.75rem 0 0;
}

.pulse__sub {
  margin: 0.35rem 0 0;
  font-size: 0.9rem;
  color: var(--muted);
}

.pulse__stale {
  margin: 0 0 1rem;
  padding: 0.65rem 0.85rem;
  border-radius: 0.5rem;
  font-size: 0.8rem;
  line-height: 1.45;
  color: #fcd34d;
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.35);
}

.pulse__sync {
  margin-left: 0.5rem;
  font-size: 0.8rem;
  color: var(--accent);
  font-weight: 500;
}

.pulse__refresh {
  margin-left: 0.5rem;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--heading);
  font-size: 0.75rem;
  padding: 0.2rem 0.55rem;
  border-radius: 0.35rem;
  vertical-align: middle;
}

.pulse__refresh:hover {
  border-color: var(--accent);
}

.pulse__mega--changed {
  animation: pulse-flash 0.6s ease;
}

@keyframes pulse-flash {
  0% {
    color: var(--accent);
  }
  100% {
    color: var(--heading);
  }
}

.pulse__meta--sub {
  margin-top: 0.25rem;
  font-size: 0.8rem;
}

.pulse__live {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.pulse__grid {
  display: grid;
  gap: 1rem;
}

@media (min-width: 640px) {
  .pulse__grid {
    grid-template-columns: 1fr 1fr;
    align-items: stretch;
  }
}

.pulse__card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 1rem;
  padding: 1.25rem 1.35rem;
  box-shadow: var(--shadow);
}

.pulse__card--muted {
  color: var(--muted);
}

.pulse__card--error {
  border-color: var(--danger-border);
  background: var(--danger-bg);
}

.pulse__err {
  margin: 0.5rem 0 1rem;
  font-family: var(--mono);
  font-size: 0.85rem;
  word-break: break-word;
}

.pulse__btn {
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--card);
  color: var(--heading);
  padding: 0.5rem 1rem;
  border-radius: 0.5rem;
  font-size: 0.95rem;
}

.pulse__btn:hover {
  border-color: var(--accent);
}

.pulse__hero {
  grid-column: 1 / -1;
}

@media (min-width: 640px) {
  .pulse__hero {
    grid-column: 1;
  }
}

.pulse__label {
  margin: 0;
  font-size: 0.85rem;
  color: var(--muted);
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
}

.pulse__pill {
  font-size: 0.7rem;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--muted);
}

.pulse__pill[data-ok='true'] {
  border-color: var(--ok-border);
  color: var(--ok);
  background: var(--ok-bg);
}

.pulse__mega {
  margin: 0.6rem 0 0;
  font-size: clamp(2.75rem, 10vw, 4rem);
  font-weight: 700;
  letter-spacing: -0.04em;
  line-height: 1;
  color: var(--heading);
  font-variant-numeric: tabular-nums;
}

.pulse__big {
  margin: 0.6rem 0 0;
  font-size: clamp(1.75rem, 5vw, 2.35rem);
  font-weight: 600;
  letter-spacing: -0.03em;
  color: var(--heading);
  font-variant-numeric: tabular-nums;
}

.pulse__unit {
  font-size: 1.1rem;
  font-weight: 500;
  color: var(--muted);
  margin-left: 0.2rem;
}

.pulse__meta {
  margin: 0.5rem 0 0;
  font-size: 0.85rem;
  color: var(--muted);
}

.pulse__tag {
  display: inline-block;
  margin: 0.75rem 0 0;
  font-size: 0.75rem;
  padding: 0.2rem 0.55rem;
  border-radius: 0.35rem;
  background: var(--tag-bg);
  color: var(--tag-fg);
}

.pulse__proxy {
  margin: 0.75rem 0 0;
  font-size: 0.9rem;
  color: var(--text);
}

.pulse__hint {
  margin: 0.5rem 0 0;
  font-size: 0.75rem;
  line-height: 1.45;
  color: var(--muted);
}

.pulse__h2 {
  margin: 0 0 1rem;
  font-size: 1rem;
  font-weight: 600;
  color: var(--heading);
}

.pulse__row {
  display: grid;
  grid-template-columns: 5.5rem 1fr 3.5rem;
  gap: 0.5rem 0.75rem;
  align-items: center;
  margin-bottom: 0.65rem;
}

.pulse__k {
  font-size: 0.8rem;
  color: var(--muted);
}

.pulse__track {
  height: 0.5rem;
  background: var(--track);
  border-radius: 999px;
  overflow: hidden;
}

.pulse__fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.4s ease;
}

.pulse__fill.solar {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}

.pulse__fill.bio {
  background: linear-gradient(90deg, #16a34a, #4ade80);
}

.pulse__fill.wind {
  background: linear-gradient(90deg, #0ea5e9, #38bdf8);
}

.pulse__v {
  font-size: 0.8rem;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--heading);
}

.pulse__extras {
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.pulse__kv {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.85rem;
  color: var(--muted);
}

.pulse__kv strong {
  color: var(--heading);
  font-weight: 600;
  text-align: right;
}

.pulse__foot {
  margin-top: 0.5rem;
  padding-top: 1.25rem;
  border-top: 1px solid var(--border);
  font-size: 0.75rem;
  line-height: 1.5;
  color: var(--muted);
}

.pulse__foot code {
  font-size: 0.7rem;
  padding: 0.1rem 0.3rem;
  border-radius: 0.25rem;
  background: var(--code-bg);
  color: var(--heading);
}
</style>
