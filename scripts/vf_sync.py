"""Relève Shopify -> data/vendredi-fou.json (bloc 2026 : heure par heure + formations).

Lecture seule des commandes du 27 au 30 nov. 2026 (heure de Montréal). N'écrit que des totaux :
commandes, ventes nettes (après rabais, avant taxes), ventes avec taxes et inscriptions, par heure;
et le top 10 des formations. Aucune donnée client n'est écrite. Les données 2025 ne bougent pas.
Sans le secret SHOPIFY_TOKEN, le script s'arrête sans rien changer.
"""
import json, os, sys, urllib.parse, time, datetime as dt, urllib.request, urllib.error
from zoneinfo import ZoneInfo
def _jeton():
    t = os.environ.get("SHOPIFY_TOKEN")
    if t: return t
    cid, sec = os.environ.get("SHOPIFY_CLIENT_ID"), os.environ.get("SHOPIFY_CLIENT_SECRET")
    if not (cid and sec): return None
    shop = os.environ.get("SHOPIFY_SHOP") or "groupe-contech.myshopify.com"
    if not shop.endswith(".myshopify.com"): shop += ".myshopify.com"
    body = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}).encode()
    req = urllib.request.Request(f"https://{shop}/admin/oauth/access_token", data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())["access_token"]
TOKEN = _jeton()
if not TOKEN:
    print("SHOPIFY_TOKEN absent : relevé Vendredi fou sauté."); sys.exit(0)
SHOP = os.environ.get("SHOPIFY_SHOP") or "groupe-contech.myshopify.com"
if not SHOP.endswith(".myshopify.com"): SHOP += ".myshopify.com"
VER = os.environ.get("SHOPIFY_API_VERSION") or "2026-07"
TZ = ZoneInfo("America/Toronto")
DEB = dt.datetime(2026, 11, 27, tzinfo=TZ); FIN = dt.datetime(2026, 12, 1, tzinfo=TZ)
DATA = os.path.join(os.path.dirname(__file__), "..", "data", "vendredi-fou.json")

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
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if essai == 4: raise
            time.sleep(3 * (essai + 1))

champs = "id,created_at,cancelled_at,financial_status,current_subtotal_price,current_total_price,line_items,test"
url = (f"https://{SHOP}/admin/api/{VER}/orders.json?status=any&limit=250&fields={champs}"
       f"&created_at_min={DEB.isoformat()}&created_at_max={FIN.isoformat()}")
heures, prod = {}, {}
while url:
    j, link = get(url)
    for o in j.get("orders", []):
        if o.get("test") or o.get("cancelled_at") or o.get("financial_status") in ("voided", "refunded"):
            continue
        t = dt.datetime.fromisoformat(o["created_at"]).astimezone(TZ).replace(minute=0, second=0, microsecond=0)
        k = t.isoformat(timespec="minutes")
        h = heures.setdefault(k, {"t": k, "commandes": 0, "ht": 0.0, "ttc": 0.0, "qte": 0})
        h["commandes"] += 1; h["ht"] += float(o.get("current_subtotal_price") or 0); h["ttc"] += float(o.get("current_total_price") or 0)
        for li in o.get("line_items", []):
            q = int(li.get("current_quantity", li.get("quantity", 0)) or 0)
            if q <= 0: continue
            h["qte"] += q
            rab = sum(float(d.get("amount") or 0) for d in li.get("discount_allocations", []))
            v = float(li.get("price") or 0) * q - rab
            p = prod.setdefault(li.get("title") or "", [0, 0.0]); p[0] += q; p[1] += v
    url = None
    if 'rel="next"' in link:
        for part in link.split(","):
            if 'rel="next"' in part: url = part[part.index("<") + 1:part.index(">")]
d = json.load(open(DATA, encoding="utf-8"))
d["releve"] = dt.datetime.now(TZ).isoformat(timespec="minutes")
d["source"] = "Shopify (commandes, relevé automatique) · ventes nettes = après le rabais de 50 %, avant taxes"
d["periodes"]["2026"]["heures"] = [dict(v, ht=round(v["ht"], 2), ttc=round(v["ttc"], 2)) for k, v in sorted(heures.items())]
top = sorted(prod.items(), key=lambda x: (-x[1][0], -x[1][1]))[:10]
d["produits"] = [{"titre": t.split("***", 1)[-1], "date": t.split("***", 1)[0] if "***" in t else "", "inscriptions": n, "ht": round(v, 2)} for t, (n, v) in top]
json.dump(d, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("Vendredi fou :", sum(v["commandes"] for v in heures.values()), "commandes", round(sum(v["ht"] for v in heures.values()), 2), "$")
