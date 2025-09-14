from datetime import datetime, date
from math import floor
import os
import logging

# FastMCP server
from fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("moon_mcp")

mcp = FastMCP("moon_mcp") 

# ---------- Utility: moon calculation ----------
def moon_phase_from_date(d: date):
    """Compute approximate moon age and illumination."""
    y = d.year
    m = d.month
    day = d.day
    if m < 3:
        y -= 1
        m += 12
    a = floor(y / 100)
    b = 2 - a + floor(a / 4)
    jd = floor(365.25 * (y + 4716)) + floor(30.6001 * (m + 1)) + day + b - 1524.5
    days_since_new = jd - 2451550.1
    synodic_month = 29.53058867
    new_moons = days_since_new / synodic_month
    fraction = new_moons - floor(new_moons)
    age = fraction * synodic_month
    illumination = (1 - abs((age / (synodic_month / 2)) - 1)) * 100
    if age < 1.84566:
        phase = "New Moon"
    elif age < 5.53699:
        phase = "Waxing Crescent"
    elif age < 9.22831:
        phase = "First Quarter"
    elif age < 12.91963:
        phase = "Waxing Gibbous"
    elif age < 16.61096:
        phase = "Full Moon"
    elif age < 20.30228:
        phase = "Waning Gibbous"
    elif age < 23.99361:
        phase = "Last Quarter"
    elif age < 27.68493:
        phase = "Waning Crescent"
    else:
        phase = "New Moon"
    return {
        "date": d.isoformat(),
        "age_days": round(age, 2),
        "illumination_pct": round(illumination, 1),
        "phase": phase,
    }

# ---------- Tool: moon_phase ----------
@mcp.tool()
def moon_phase(date: str = None) -> dict:
    """
    Devuelve la fase lunar para una fecha ISO (YYYY-MM-DD).
    - date: opcional, formato 'YYYY-MM-DD'. Si no se pasa, usa la fecha UTC actual.
    Retorna: dict {date, phase, age_days, illumination_pct}
    """
    if date:
        try:
            d = datetime.strptime(date, "%Y-%m-%d").date()
        except Exception:
            raise ValueError("Formato inválido: use YYYY-MM-DD")
    else:
        d = datetime.utcnow().date()
    return moon_phase_from_date(d)

@mcp.tool(name="mcp.server.shutdown")
def mcp_server_shutdown() -> dict:
    """Indica que el servidor acepta una petición de apagado (no forzamos exit desde aquí)."""
    logger.info("Shutdown requested via mcp.server.shutdown — returning acknowledgement.")
    return {"shutdown": True}

# ---------- uvicorn ----------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("moon_mcp:mcp", host="0.0.0.0", port=port)

