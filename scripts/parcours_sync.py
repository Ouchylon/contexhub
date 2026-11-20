"""Relève du parcours client -> os/data.json (bloc « parcours »).

Pour chaque commande payée de la boutique Shopify, lit le résumé du parcours que Shopify garde
(première et dernière visite : source, UTM, page d'arrivée) et n'écrit que des totaux par canal.
Aucun nom, courriel, adresse ni numéro de commande n'est écrit.
Même jeton que shopify_sync.py (secret SHOPIFY_TOKEN, portée read_orders); sans jeton, le script s'arrête.
"""
import json, os, sys, time, datetime as dt, urllib.request, urllib.error
from collections import Counter, defaultdict
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(__file__))
from canaux import canal, ORDRE

TOKEN = os.environ.get("SHOPIFY_TOKEN")
if not TOKEN:
    print("SHOPIFY_TOKEN absent : parcours sauté.")
    sys.exit(0)
SHOP = os.environ.get("SHOPIFY_SHOP") or "groupe-contech.myshopify.com"
VER = os.environ.get("SHOPIFY_API_VERSION") or "2026-07"
DEPUIS = os.environ.get("SHOPIFY_DEPUIS") or "2026-01-01"
TZ = ZoneInfo("America/Toronto")
DATA = os.path.join(os.path.dirname(__file__), "..", "os", "data.json")

VISITE = "source sourceType referrerUrl landingPage occurredAt utmParameters { source medium campaign content term }"
Q = """query($after:String,$q:String){orders(first:100,after:$after,query:$q,sortKey:CREATED_AT){
 pageInfo{hasNextPage endCursor}
 nodes{createdAt test cancelledAt displayFinancialStatus
  currentSubtotalPriceSet{shopMoney{amount}}
  lineItems(first:20){nodes{currentQuantity title product{id}}}
  customerJourneySummary{ready daysToConversion momentsCount{count}
   firstVisit{%s} lastVisit{%s}}}}}""" % (VISITE, VISITE)


def gql(variables):
    body = json.dumps({"query": Q, "variables": variables}).encode()
    req = urllib.request.Request(f"https://{SHOP}/admin/api/{VER}/graphql.json", data=body,
                                 headers={"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"})
    for essai in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read().decode())
            if res.get("errors"):
                if any("THROTTLED" in json.dumps(e) for e in res["errors"]) and essai < 4:
                    time.sleep(4 * (essai + 1)); continue
                sys.exit(f"Shopify GraphQL : {json.dumps(res['errors'])[:400]}")
            return res["data"]["orders"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and essai < 4:
                time.sleep(3 * (essai + 1)); continue
            sys.exit(f"Shopify {e.code} : {e.read()[:300]!r}")
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if essai == 4:
                raise
            time.sleep(3 * (essai + 1))


def page(url):
    p = urlparse(url or "").path or "/"
    return p if len(p) < 120 else p[:117] + "…"


commandes, after = [], None
while True:
    o = gql({"after": after, "q": f"created_at:>={DEPUIS}"})
    commandes += o["nodes"]
    if not o["pageInfo"]["hasNextPage"]:
        break
    after = o["pageInfo"]["endCursor"]
print(len(commandes), "commandes lues")

PAYE = {"PAID", "PARTIALLY_REFUNDED", "PARTIALLY_PAID"}
prem, dern = defaultdict(lambda: {"commandes": 0, "ht": 0.0, "inscriptions": 0}), defaultdict(lambda: {"commandes": 0, "ht": 0.0, "inscriptions": 0})
mois = defaultdict(Counter)
campagnes, arrivees, produits = Counter(), Counter(), Counter()
delais, moments, sans = [], [], 0
for c in commandes:
    if c.get("test") or c.get("cancelledAt") or c.get("displayFinancialStatus") not in PAYE:
        continue
    ht = float(((c.get("currentSubtotalPriceSet") or {}).get("shopMoney") or {}).get("amount") or 0)
    insc = sum(max(0, li.get("currentQuantity") or 0) for li in (c.get("lineItems") or {}).get("nodes") or [])
    j = c.get("customerJourneySummary") or {}
    fv, lv = j.get("firstVisit"), j.get("lastVisit") or j.get("firstVisit")
    if not fv:
        sans += 1
        cf = cl = "Direct / inconnu"
    else:
        cf = canal(fv.get("utmParameters"), fv.get("referrerUrl"), fv.get("source"))
        cl = canal(lv.get("utmParameters"), lv.get("referrerUrl"), lv.get("source"))
        camp = ((lv.get("utmParameters") or {}).get("campaign") or "").strip()
        if camp:
            campagnes[(cl, camp)] += 1
        arrivees[page(fv.get("landingPage"))] += 1
        if j.get("daysToConversion") is not None:
            delais.append(j["daysToConversion"])
        if (j.get("momentsCount") or {}).get("count") is not None:
            moments.append(j["momentsCount"]["count"])
    for li in (c.get("lineItems") or {}).get("nodes") or []:
        if (li.get("currentQuantity") or 0) > 0:
            produits[(cl, (li.get("title") or "").strip())] += li["currentQuantity"]
    for b, k in ((prem, cf), (dern, cl)):
        b[k]["commandes"] += 1; b[k]["ht"] += ht; b[k]["inscriptions"] += insc
    m = dt.datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00")).astimezone(TZ).strftime("%Y-%m")
    mois[m][cl] += 1


def liste(b):
    return [{"canal": k, "commandes": b[k]["commandes"], "inscriptions": b[k]["inscriptions"], "ht": round(b[k]["ht"], 2)}
            for k in ORDRE if k in b]


def mediane(x):
    x = sorted(x)
    return None if not x else (x[len(x) // 2] if len(x) % 2 else (x[len(x) // 2 - 1] + x[len(x) // 2]) / 2)


n = sum(v["commandes"] for v in prem.values())
bloc = {
    "releve": dt.datetime.now(TZ).isoformat(timespec="minutes"),
    "source": "Shopify (parcours client des commandes, lecture seule)",
    "depuis": DEPUIS,
    "commandes": n,
    "sansParcours": sans,
    "premiereVisite": liste(prem),
    "derniereVisite": liste(dern),
    "parMois": [{"mois": m, "canaux": dict(v)} for m, v in sorted(mois.items())],
    "delaiMedianJours": mediane(delais),
    "visitesMedianes": mediane(moments),
    "campagnes": [{"canal": k[0], "campagne": k[1], "commandes": v} for k, v in campagnes.most_common(15)],
    "pagesArrivee": [{"page": k, "commandes": v} for k, v in arrivees.most_common(10)],
    "formationsParCanal": [{"canal": k[0], "formation": k[1], "inscriptions": v} for k, v in produits.most_common(40)],
}
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data["parcours"] = bloc
data.setdefault("fraicheur", {})["parcours"] = {"mode": "auto", "src": "parcours", "source": "Shopify + Google Analytics + Search Console (API)"}
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"Parcours : {n} commandes, {sans} sans parcours.")
