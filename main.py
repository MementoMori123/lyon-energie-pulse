from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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


def _regional_row_for_timestamp(ts: str) -> dict | None:
    r = requests.get(ODRE_REGION_URL, timeout=30)
    r.raise_for_status()
    rows = r.json().get("results") or []
    for row in rows:
        if row.get("date_heure") == ts:
            return row
    return None


@app.get("/api/pulse")
async def get_pulse():
    try:
        response = requests.get(ODRE_METRO_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('results'):
            raise HTTPException(status_code=404, detail="Data not available")

        record = next(
            (r for r in data["results"] if r.get("consommation") is not None),
            None,
        )
        if record is None:
            raise HTTPException(
                status_code=404,
                detail="No Lyon row with consommation in the latest window",
            )

        ts = record["date_heure"]
        regional = None
        try:
            regional = _regional_row_for_timestamp(ts)
        except requests.RequestException:
            regional = None

        # Métropole: consommation + échanges (eco2mix-metropoles-tr).
        consumption = _float_or_none(record.get("consommation")) or 0
        physical_exchanges = _float_or_none(record.get("echanges_physiques"))

        # Renewables: from eco2mix-regional-tr (whole région, same time slot).
        solar = _float_or_none((regional or {}).get("solaire"))
        bio = _float_or_none((regional or {}).get("bioenergies"))
        wind = _float_or_none((regional or {}).get("eolien"))
        renewables = [v for v in (solar, bio, wind) if v is not None]
        regional_renewables = sum(renewables) if renewables else None

        autonomy_proxy = None
        if regional_renewables is not None and consumption > 0:
            autonomy_proxy = round((regional_renewables / consumption) * 100, 2)

        return {
            "city": "Métropole de Lyon",
            "timestamp": ts,
            "metrics": {
                "consumption_mw": consumption,
                "regional_renewables_mw": regional_renewables,
                "autonomy_proxy_percent": autonomy_proxy,
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
                "autonomy_proxy_note": (
                    "regional_renewables_mw / métropole consumption — "
                    "different geographic scopes; illustrative only."
                ),
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
