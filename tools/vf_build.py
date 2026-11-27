"""Construit data/vendredi-fou.json (ventes Vendredi fou -> Cyber lundi, 2026 vs 2025).

Entrée : un fichier JSON {"releve": iso, "h2026": [[iso_utc, commandes, ht, ttc, qte], ...],
"h2025": [...], "produits": [[titre, inscriptions, ht], ...]} (lignes horaires non nulles,
tirées des rapports Shopify Analytics, ventes nettes = après rabais, avant taxes).
Aucune donnée client n'est écrite.
"""
import json, sys, datetime as dt
from zoneinfo import ZoneInfo
TZ = ZoneInfo("America/Toronto")
src = json.load(open(sys.argv[1], encoding="utf-8"))
def heures(rows):
    out = []
    for t, c, ht, ttc, q in rows:
        d = dt.datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone(TZ)
        out.append({"t": d.isoformat(timespec="minutes"), "commandes": int(c), "ht": round(float(ht), 2),
                    "ttc": round(float(ttc), 2), "qte": int(q)})
    return out
data = {
    "releve": src["releve"],
    "source": "Shopify (rapports Analytics) · ventes nettes = après le rabais de 50 %, avant taxes",
    "periodes": {
        "2026": {"debut": "2026-11-27", "jours": ["2026-11-27", "2026-11-28", "2026-11-29", "2026-11-30"], "heures": heures(src["h2026"])},
        "2025": {"debut": "2025-11-28", "jours": ["2025-11-28", "2025-11-29", "2025-11-30", "2025-12-01"], "heures": heures(src["h2025"])},
    },
    "produits": [{"titre": t.split("***", 1)[-1], "date": t.split("***", 1)[0] if "***" in t else "", "inscriptions": int(n), "ht": float(v)}
                 for t, n, v in src["produits"]],
}
out = sys.argv[2] if len(sys.argv) > 2 else "data/vendredi-fou.json"
json.dump(data, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("écrit", out, len(data["periodes"]["2026"]["heures"]), "h 2026")
