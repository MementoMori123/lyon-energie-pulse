from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import urllib.parse

import requests

app = FastAPI(title="Lyon Énergie Pulse API")

# Allow your future Frontend to talk to this Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ODRE_METRO_URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "eco2mix-metropoles-tr/records?"
    "where=search(libelle_metropole%2C%20%22Lyon%22)"
    # Newest rows are often still null for consommation; fetch a window and pick
    # the latest row that already has values (ODRE publishes 15-minute slots).
    "&order_by=date_heure%20desc&limit=100"
)

# Per-source generation exists at régional scale, not in eco2mix-metropoles-tr.
# Lyon métropole lies in Auvergne-Rhône-Alpes — join on date_heure with metro row.
_REGION_FILTER = urllib.parse.quote('libelle_region = "Auvergne-Rhône-Alpes"')
ODRE_REGION_URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "eco2mix-regional-tr/records?"
    f"where={_REGION_FILTER}"
    "&order_by=date_heure%20desc&limit=100"
)


def _float_or_none(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value.replace(",", "."))
        except ValueError:
            return None
    return None


def _first_row_with_values(rows: list[dict], keys: tuple[str, ...]) -> dict | None:
    for row in rows:
        if any(row.get(k) is not None for k in keys):
            return row
    return None


def _parse_odre_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _slot_age_hours(ts: str) -> float | None:
    slot = _parse_odre_ts(ts)
    if slot is None:
        return None
    now = datetime.now(timezone.utc)
    if slot.tzinfo is None:
        slot = slot.replace(tzinfo=timezone.utc)
    return round((now - slot).total_seconds() / 3600, 1)


def _fetch_odre_rows(url: str) -> list[dict]:
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json().get("results") or []


@app.get("/api/pulse")
async def get_pulse():
    try:
        metro_rows = _fetch_odre_rows(ODRE_METRO_URL)
        if not metro_rows:
            raise HTTPException(status_code=404, detail="Data not available")

        record = _first_row_with_values(metro_rows, ("consommation",))
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="No Lyon row with consommation in the latest window",
            )

        ts = record["date_heure"]
        metro_age_h = _slot_age_hours(ts)

        regional = None
        regional_renewables_row = None
        try:
            regional_rows = _fetch_odre_rows(ODRE_REGION_URL)
            regional = next(
                (r for r in regional_rows if r.get("date_heure") == ts),
                None,
            )
            # ODRE often leaves many trailing null rows; use the latest regional
            # créneau that actually has EnR values (not locked to stale metro slot).
            regional_renewables_row = _first_row_with_values(
                regional_rows,
                ("solaire", "eolien", "bioenergies"),
            )
        except requests.RequestException:
            regional_rows = []

        renew_row = regional_renewables_row or regional or {}

        # Métropole: consommation + échanges (eco2mix-metropoles-tr).
        consumption = _float_or_none(record.get("consommation")) or 0
        physical_exchanges = _float_or_none(record.get("echanges_physiques"))

        # Renewables: latest regional row with EnR data (may differ from metro slot).
        solar = _float_or_none(renew_row.get("solaire"))
        bio = _float_or_none(renew_row.get("bioenergies"))
        wind = _float_or_none(renew_row.get("eolien"))
        renewables_ts = renew_row.get("date_heure")
        renewables_age_h = (
            _slot_age_hours(renewables_ts) if renewables_ts else None
        )
        renewables = [v for v in (solar, bio, wind) if v is not None]
        regional_renewables = sum(renewables) if renewables else None

        stale_after_h = 2.0
        payload = {
            "city": "Métropole de Lyon",
            "timestamp": ts,
            "renewables_timestamp": renewables_ts,
            "freshness": {
                "metro_slot_age_hours": metro_age_h,
                "renewables_slot_age_hours": renewables_age_h,
                "metro_stale": metro_age_h is not None and metro_age_h > stale_after_h,
                "renewables_stale": renewables_age_h is not None
                and renewables_age_h > stale_after_h,
                "trailing_null_slots": sum(
                    1 for r in metro_rows if r.get("consommation") is None
                ),
            },
            "metrics": {
                "consumption_mw": consumption,
                "regional_renewables_mw": regional_renewables,
                "physical_exchanges_mw": physical_exchanges,
            },
            "breakdown": {
                "solar": solar,
                "biomass": bio,
                "wind": wind,
            },
            "source": "RTE / ODRE",
            "odre": {
                "nature": record.get("nature"),
                "production": record.get("production"),
            },
            "mapping": {
                "consumption_dataset": "eco2mix-metropoles-tr",
                "consumption_geo": "Métropole de Lyon",
                "renewables_dataset": "eco2mix-regional-tr",
                "renewables_geo": "Auvergne-Rhône-Alpes",
                "join_key": "date_heure",
                "regional_row_matched": regional is not None,
                "renewables_same_slot_as_metro": renewables_ts == ts,
            },
            "story": (
                "Affiche le dernier créneau de 15 minutes publié par ODRE pour la "
                "consommation métropolitaine, et le dernier créneau régional avec "
                "données EnR — pas une vue temps réel."
            ),
        }
        return JSONResponse(
            content=payload,
            headers={"Cache-Control": "no-store"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
