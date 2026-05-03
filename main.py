from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from datetime import datetime

app = FastAPI(title="Lyon Énergie Pulse API")

# Allow your future Frontend to talk to this Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ODRE_URL = (
    "https://odre.opendatasoft.com/api/explore/v2.1/catalog/datasets/"
    "eco2mix-metropoles-tr/records?"
    "where=search(libelle_metropole%2C%20%22Lyon%22)"
    "&order_by=date_heure%20desc&limit=1"
)

@app.get("/api/pulse")
async def get_pulse():
    try:
        response = requests.get(ODRE_URL)
        response.raise_for_status()
        data = response.json()
        
        if not data.get('results'):
            raise HTTPException(status_code=404, detail="Data not available")

        record = data['results'][0]
        
        # Data Normalization (Converting ODRE to your own Standard)
        consumption = record.get('cnsommation', 0)
        solar = record.get('solaire', 0) or 0
        bio = record.get('bioenergies', 0) or 0
        wind = record.get('eolien', 0) or 0
        local_prod = solar + bio + wind
        
        # Business Logic: Autonomy Rate
        autonomy_rate = round((local_prod / consumption * 100), 2) if consumption > 0 else 0

        return {
            "city": "Métropole de Lyon",
            "timestamp": record['date_heure'],
            "metrics": {
                "consumption_mw": consumption,
                "production_local_mw": local_prod,
                "autonomy_percent": autonomy_rate
            },
            "breakdown": {
                "solar": solar,
                "biomass": bio,
                "wind": wind
            },
            "source": "RTE / ODRE"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
