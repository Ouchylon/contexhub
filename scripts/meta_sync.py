"""Relève Meta -> os/data.json (pubs en cours + statistiques des pubs, lecture seule).

Lit, avec le jeton d'un utilisateur système (ads_read, read_insights, pages_read_engagement) :
- les campagnes actives ou programmées du compte publicitaire, leur budget et leurs dates;
- pour chaque pub active : portée, impressions, clics sur le lien, montant dépensé (aujourd'hui et depuis le début).
Sans jeton (secret META_TOKEN absent), le script s'arrête sans rien changer.
"""
import json, os, sys, time, datetime as dt, urllib.request, urllib.parse, urllib.error
from zoneinfo import ZoneInfo

TOKEN = os.environ.get("META_TOKEN")
if not TOKEN:
    print("META_TOKEN absent : relevé Meta sauté.")
    sys.exit(0)
ACT = os.environ.get("META_AD_ACCOUNT") or "act_2957431290951167"
VER = os.environ.get("META_API_VERSION") or "v23.0"
TZ = ZoneInfo("America/Toronto")
DATA = os.path.join(os.path.dirname(__file__), "..", "os", "data.json")


def get(path, **params):
    params["access_token"] = TOKEN
    url = f"https://graph.facebook.com/{VER}/{path}?" + urllib.parse.urlencode(params)
    out = []
    while url:
        for essai in range(5):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    res = json.loads(r.read().decode())
                break
            except urllib.error.HTTPError as e:
                body = e.read()[:300]
                if e.code in (429, 500, 502, 503) and essai < 4:
                    time.sleep(5 * (essai + 1)); continue
                sys.exit(f"Meta {e.code} : {body!r}")
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                if essai == 4:
                    raise
                time.sleep(5 * (essai + 1))
        if "data" not in res:
            return res
        out += res["data"]
        url = (res.get("paging") or {}).get("next")
    return out


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


camps = get(f"{ACT}/campaigns", fields="id,name,effective_status,start_time,stop_time,daily_budget,lifetime_budget,objective",
            effective_status=json.dumps(["ACTIVE", "SCHEDULED", "IN_PROCESS", "WITH_ISSUES"]), limit=100)
pubs = []
for c in camps:
    ads = get(f"{c['id']}/ads", fields="id,name,effective_status,creative{effective_object_story_id}", limit=100)
    for a in ads:
        def ins(preset):
            r = get(f"{a['id']}/insights", fields="reach,impressions,inline_link_clicks,spend,actions,action_values", date_preset=preset)
            r = r[0] if isinstance(r, list) and r else {}
            act = {x.get("action_type"): num(x.get("value")) for x in r.get("actions") or []}
            val = {x.get("action_type"): num(x.get("value")) for x in r.get("action_values") or []}
            def ev(d, nom):  # pixel de la boutique d'abord, sinon le total Meta
                return d.get(f"offsite_conversion.fb_pixel_{nom}", d.get(nom, 0))
            return {"portee": int(num(r.get("reach"))), "impressions": int(num(r.get("impressions"))),
                    "clics": int(num(r.get("inline_link_clicks"))), "depense": round(num(r.get("spend")), 2),
                    "visites": int(act.get("landing_page_view", 0)), "paniers": int(ev(act, "add_to_cart")),
                    "paiements": int(ev(act, "initiate_checkout")), "achats": int(ev(act, "purchase")),
                    "valeurAchats": round(ev(val, "purchase"), 2)}
        story = ((a.get("creative") or {}).get("effective_object_story_id") or "")
        post = f"https://www.facebook.com/{story.replace('_', '/posts/')}/" if story else ""
        pubs.append({"campagne": c["name"], "pub": a["name"], "statut": a.get("effective_status"),
                     "post": post, "aujourdhui": ins("today"), "total": ins("maximum")})

now = dt.datetime.now(TZ)
bloc = {"releve": now.isoformat(timespec="minutes"), "source": "Meta Marketing API (lecture seule)",
        "campagnes": [{"nom": c["name"], "statut": c.get("effective_status"), "debut": c.get("start_time"), "fin": c.get("stop_time"),
                       "budgetJour": round(num(c.get("daily_budget")) / 100, 2) if c.get("daily_budget") else None,
                       "budgetTotal": round(num(c.get("lifetime_budget")) / 100, 2) if c.get("lifetime_budget") else None,
                       "objectif": c.get("objective")} for c in camps],
        "pubs": pubs}
with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
data["meta"] = bloc
data.setdefault("fraicheur", {})
data["fraicheur"]["pubs"] = {"mode": "auto", "src": "meta", "source": "Meta (API)"}
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"{len(camps)} campagnes, {len(pubs)} pubs écrites.")
