"""Relève Shopify -> os/data.json (bloc « shopify »).

Lit les commandes de la boutique (lecture seule) et n'écrit que des totaux :
- par jour : montant encaissé (avant taxes et avec taxes) et nombre de commandes;
- par formation (produit) : nombre d'inscriptions payées.
Aucune donnée client (nom, courriel, adresse) n'est écrite.
Le jeton vient du secret GitHub SHOPIFY_TOKEN; sans jeton, le script s'arrête sans rien changer.
"""
import json, os, sys, re, time, datetime as dt, urllib.request, urllib.error
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("SHOPIFY_TOKEN")
if not TOKEN:
    print("SHOPIFY_TOKEN absent : relevé Shopify sauté.")
    sys.exit(0)
SHOP = os.environ.get("SHOPIFY_SHOP") or "groupe-contech.myshopify.com"
VER = os.environ.get("SHOPIFY_API_VERSION") or "2026-07"
DEPUIS = os.environ.get("SHOPIFY_DEPUIS") or "2026-01-01"
TZ = ZoneInfo("America/Toronto")
DATA = os.path.join(os.path.dirname(__file__), "..", "os", "data.json")
PAYE = {"paid", "partially_refunded", "partially_paid"}


def get(url):
    req = urllib.request.Request(url, headers={"X-Shopify-Access-Token": TOKEN, "Accept": "application/json"})
    for essai in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode()), r.headers.get("Link") or ""
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and essai < 4:
                time.sleep(3 * (essai + 1)); continue
            sys.exit(f"Shopify {e.code} : {e.read()[:300]!r}")
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            if essai == 4:
                raise
            time.sleep(3 * (essai + 1))


champs = "id,processed_at,created_at,cancelled_at,financial_status,current_subtotal_price,current_total_price,line_items,test"
url = (f"https://{SHOP}/admin/api/{VER}/orders.json?status=any&limit=250"
       f"&created_at_min={DEPUIS}T00:00:00-05:00&fields={champs}")
commandes = []
while url:
    page, link = get(url)
    commandes += page.get("orders", [])
    m = re.search(r'<([^>]+)>;\s*rel="next"', link)
    url = m.group(1) if m else None
print(len(commandes), "commandes lues")

jours, produits = {}, {}
for c in commandes:
    if c.get("test") or c.get("cancelled_at") or c.get("financial_status") not in PAYE:
        continue
    quand = dt.datetime.fromisoformat((c.get("processed_at") or c["created_at"]).replace("Z", "+00:00")).astimezone(TZ)
    j = jours.setdefault(quand.date().isoformat(), {"ht": 0.0, "ttc": 0.0, "commandes": 0})
    j["ht"] += float(c.get("current_subtotal_price") or 0)
    j["ttc"] += float(c.get("current_total_price") or 0)
    j["commandes"] += 1
    for li in c.get("line_items") or []:
        q = li.get("current_quantity", li.get("quantity")) or 0
        if q <= 0:
            continue
        t = (li.get("title") or "").strip()
        p = produits.setdefault(str(li.get("product_id") or t), {"titre": t, "inscriptions": 0})
        p["inscriptions"] += q

now = dt.datetime.now(TZ)
bloc = {
    "releve": now.isoformat(timespec="minutes"),
    "source": "Shopify (API, lecture seule)",
    "note": "Commandes payées, annulations et remboursements déduits. HT = avant taxes.",
    "jours": [{"date": d, "ht": round(v["ht"], 2), "ttc": round(v["ttc"], 2), "commandes": v["commandes"]}
              for d, v in sorted(jours.items())],
    "produits": sorted(produits.values(), key=lambda p: -p["inscriptions"]),
}
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data["shopify"] = bloc
data.setdefault("fraicheur", {})
data["fraicheur"]["ventes"] = {"mode": "auto", "src": "shopify", "source": "Shopify (API) + Coûts et revenus 2026 (SharePoint)"}
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"{len(bloc['jours'])} jours, {len(bloc['produits'])} produits écrits.")
