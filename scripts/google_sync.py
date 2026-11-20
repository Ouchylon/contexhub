"""Relève Google Analytics 4 + Search Console -> os/data.json (blocs « ga4 » et « gsc »).

Un seul compte de service Google (secret GOOGLE_SA_JSON), ajouté en lecteur :
- sur la propriété GA4 de contech.qc.ca (secret GA4_PROPERTY_ID, ex. 123456789);
- sur la propriété Search Console (secret GSC_SITE, ex. sc-domain:contech.qc.ca).
N'écrit que des totaux (canaux, pages, mots-clés). Chaque partie est sautée si son secret manque.
"""
import json, os, re, sys, datetime as dt
from collections import defaultdict
from urllib.parse import quote
from zoneinfo import ZoneInfo
sys.path.insert(0, os.path.dirname(__file__))
from canaux import canal_ga4, ORDRE

SA = os.environ.get("GOOGLE_SA_JSON")
PROP = (os.environ.get("GA4_PROPERTY_ID") or "").replace("properties/", "").strip()
SITE = (os.environ.get("GSC_SITE") or "").strip()
if not SA or not (PROP or SITE):
    print("GOOGLE_SA_JSON / GA4_PROPERTY_ID / GSC_SITE absents : relevé Google sauté.")
    sys.exit(0)

from google.oauth2 import service_account
from google.auth.transport.requests import AuthorizedSession

TZ = ZoneInfo("America/Toronto")
DATA = os.path.join(os.path.dirname(__file__), "..", "os", "data.json")
now = dt.datetime.now(TZ)
cred = service_account.Credentials.from_service_account_info(json.loads(SA), scopes=[
    "https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/webmasters.readonly"])
S = AuthorizedSession(cred)

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data.setdefault("fraicheur", {})["parcours"] = {"mode": "auto", "src": "parcours", "source": "Shopify + Google Analytics + Search Console (API)"}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


# ---------- GA4 ----------
def rapport(dims, mets, jours=30, filtre=None, limite=50, tri=None):
    body = {"dateRanges": [{"startDate": f"{jours}daysAgo", "endDate": "today"}],
            "dimensions": [{"name": d} for d in dims], "metrics": [{"name": m} for m in mets], "limit": limite}
    if filtre:
        body["dimensionFilter"] = filtre
    if tri:
        body["orderBys"] = [{"metric": {"metricName": tri}, "desc": True}]
    r = S.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{PROP}:runReport", json=body, timeout=60)
    if r.status_code >= 400:
        print("GA4", dims, r.status_code, r.text[:300])
        return []
    out = []
    for row in r.json().get("rows", []):
        d = [x["value"] for x in row["dimensionValues"]]
        m = [num(x["value"]) for x in row["metricValues"]]
        out.append((d, m))
    return out


if PROP:
    M = ["sessions", "totalUsers", "addToCarts", "checkouts", "ecommercePurchases", "purchaseRevenue"]
    can = defaultdict(lambda: [0.0] * len(M))
    for d, m in rapport(["sessionDefaultChannelGroup", "sessionSource"], M, limite=500):
        k = canal_ga4(d[0], d[1])
        can[k] = [a + b for a, b in zip(can[k], m)]
    canaux = [{"canal": k, "sessions": int(v[0]), "visiteurs": int(v[1]), "paniers": int(v[2]), "paiements": int(v[3]),
               "achats": int(v[4]), "revenus": round(v[5], 2)} for k, v in sorted(can.items(), key=lambda kv: ORDRE.index(kv[0]) if kv[0] in ORDRE else 99)]
    fiches = rapport(["sessionDefaultChannelGroup", "sessionSource"], ["screenPageViews"], limite=500,
                     filtre={"filter": {"fieldName": "pagePath", "stringFilter": {"matchType": "BEGINS_WITH", "value": "/products/"}}})
    fc = defaultdict(int)
    for d, m in fiches:
        fc[canal_ga4(d[0], d[1])] += int(m[0])
    for c in canaux:
        c["fiches"] = fc.get(c["canal"], 0)
    ia = [{"source": d[0], "sessions": int(m[0]), "achats": int(m[1])} for d, m in rapport(
        ["sessionSource"], ["sessions", "ecommercePurchases"], jours=90, limite=20, tri="sessions",
        filtre={"filter": {"fieldName": "sessionSource", "stringFilter": {"matchType": "PARTIAL_REGEXP",
                                                                           "value": "chatgpt|openai|perplexity|gemini|copilot|claude|mistral|deepseek"}}})]
    pages = [{"page": d[0][:120], "sessions": int(m[0]), "achats": int(m[1])} for d, m in rapport(
        ["landingPage"], ["sessions", "ecommercePurchases"], limite=12, tri="sessions")]
    recherche = [{"terme": d[0], "fois": int(m[0])} for d, m in rapport(
        ["searchTerm"], ["eventCount"], jours=90, limite=25, tri="eventCount",
        filtre={"filter": {"fieldName": "eventName", "stringFilter": {"value": "view_search_results"}}}) if d[0] not in ("(not set)", "")]
    gads = [{"campagne": d[0], "sessions": int(m[0]), "cout": round(m[1], 2), "achats": int(m[2])} for d, m in rapport(
        ["sessionGoogleAdsCampaignName"], ["sessions", "advertiserAdCost", "ecommercePurchases"], limite=15, tri="sessions") if d[0] not in ("(not set)", "")]
    data["ga4"] = {"releve": now.isoformat(timespec="minutes"), "source": "Google Analytics 4 (API, lecture seule)", "periode": "30 derniers jours",
                   "canaux": canaux, "ia": ia, "pagesArrivee": pages, "rechercheInterne": recherche, "googleAds": gads}
    print(f"GA4 : {len(canaux)} canaux, {len(gads)} campagnes Google Ads.")

# ---------- Search Console ----------
if SITE:
    fin = (now - dt.timedelta(days=3)).date()
    deb = fin - dt.timedelta(days=89)

    def gsc(dims, limite):
        r = S.post(f"https://www.googleapis.com/webmasters/v3/sites/{quote(SITE, safe='')}/searchAnalytics/query",
                   json={"startDate": deb.isoformat(), "endDate": fin.isoformat(), "dimensions": dims, "rowLimit": limite}, timeout=60)
        if r.status_code >= 400:
            print("GSC", r.status_code, r.text[:300])
            return []
        return r.json().get("rows", [])

    centres = (data.get("contenus") or {}).get("centres") or []

    def centre(q):
        for c in centres:
            if any(re.search(m, q, re.I) for m in c.get("mots", [])):
                return c["nom"]
        return ""

    req = [{"requete": r["keys"][0], "clics": int(r["clicks"]), "impressions": int(r["impressions"]),
            "position": round(r["position"], 1), "centre": centre(r["keys"][0])} for r in gsc(["query"], 250)]
    marque = re.compile(r"contech|contex", re.I)
    pages = [{"page": r["keys"][0].split("contech.qc.ca")[-1][:120] or "/", "clics": int(r["clicks"]),
              "impressions": int(r["impressions"]), "position": round(r["position"], 1)} for r in gsc(["page"], 25)]
    par_centre = defaultdict(lambda: {"clics": 0, "impressions": 0, "requetes": 0})
    for q in req:
        if q["centre"]:
            p = par_centre[q["centre"]]; p["clics"] += q["clics"]; p["impressions"] += q["impressions"]; p["requetes"] += 1
    # Occasions : beaucoup d'impressions, position 5 à 30, hors nom de marque
    occ = sorted([q for q in req if not marque.search(q["requete"]) and 5 <= q["position"] <= 30], key=lambda q: -q["impressions"])[:15]
    data["gsc"] = {"releve": now.isoformat(timespec="minutes"), "source": "Google Search Console (API, lecture seule)",
                   "periode": f"{deb.isoformat()} au {fin.isoformat()}",
                   "totaux": {"clics": sum(q["clics"] for q in req), "impressions": sum(q["impressions"] for q in req),
                              "marque": sum(q["clics"] for q in req if marque.search(q["requete"]))},
                   "requetes": req[:60], "occasions": occ, "pages": pages,
                   "parCentre": [{"centre": k, **v} for k, v in sorted(par_centre.items(), key=lambda kv: -kv[1]["impressions"])]}
    print(f"Search Console : {len(req)} requêtes.")

with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
