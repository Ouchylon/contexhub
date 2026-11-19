from datetime import timedelta
"""Relève Dialog Insight -> os/data.json (bloc infolettres.derniers).

Appelle Sendings.GetBatches (envois des 45 derniers jours) puis Messages.Get
pour le nom de chaque message. N'écrit que des statistiques agrégées par envoi :
aucune donnée de contact. La clé vient des secrets GitHub (DI_IDKEY, DI_KEY).
"""
import json, os, sys, datetime as dt, urllib.request, urllib.error

BASE = "https://app.dialoginsight.com/webservices/ofc4/"
ID_PROJECT = int(os.environ.get("DI_IDPROJECT", "7991"))  # Contech TC
AUTH = {"idKey": int(os.environ.get("DI_IDKEY") or 34368), "Key": os.environ["DI_KEY"]}
DATA = os.path.join(os.path.dirname(__file__), "..", "os", "data.json")


def call(service, method, payload):
    body = json.dumps({"AuthKey": AUTH, **payload}).encode()
    req = urllib.request.Request(f"{BASE}{service}.ashx?method={method}", data=body,
                                 headers={"Content-Type": "application/json"})
    import time
    for essai in range(5):  # le serveur coupe parfois la connexion : on réessaie
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                res = json.loads(r.read().decode("utf-8-sig"))
            break
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            if essai == 4:
                raise
            print("Nouvel essai après erreur réseau :", e)
            time.sleep(3 * (essai + 1))
    if not res.get("Success"):
        sys.exit(f"{service}.{method} : {res.get('ErrorCode')} {res.get('ErrorMessage')}")
    return res


def pick(d, *needles, exclude=()):
    """Premier champ numérique dont le nom contient tous les mots donnés."""
    for k, v in d.items():
        kl = k.lower()
        if isinstance(v, (int, float)) and not isinstance(v, bool) \
                and all(n in kl for n in needles) and not any(x in kl for x in exclude):
            return v
    return None


now = dt.datetime.now(dt.timezone(dt.timedelta(hours=-5)))
fmt = "%Y.%m.%d %H:%M:%S"
res = call("sendings", "GetBatches", {
    "idProject": ID_PROJECT,
    "batchFilter": {"BatchFilterMode": "dtCreated",
                    "dtCreated_Min": (now - dt.timedelta(days=90)).strftime(fmt),
                    "dtCreated_Max": now.strftime(fmt)}})
batches = [b for b in res.get("BatchInfos") or []
           if not b.get("isTestBach") and not b.get("isCancelled") and b.get("dtFirstMessage")]

names, contents = {}, {}
for idm in {b["idMessage"] for b in batches}:
    try:
        m = call("messages", "Get", {"idProject": ID_PROJECT, "idMessage": idm}).get("Message") or {}
        names[idm] = m.get("Name") or f"Message {idm}"
        try:
            contents[idm] = m["MessageVersions"][0]["MessageBodies"][0]["Content"]
        except (KeyError, IndexError, TypeError):
            pass
    except SystemExit as e:
        print("Message introuvable", idm, e)
        names[idm] = f"Message {idm}"

# Aperçus : on remplace les images de la librairie par leur adresse publique,
# on retire les liens suivis et les balises de personnalisation.
OSDIR = os.path.join(os.path.dirname(__file__), "..", "os")
IMG = json.load(open(os.path.join(OSDIR, "di_images.json")))
GENERIC = {"2215", "1871", "1872", "1873", "2332", "1888", "2310"}
import re
def render(idm, html):
    missing = []
    def img(mo):
        u = IMG.get(mo.group(1))
        if not u:
            missing.append(mo.group(1))
            return "data:image/gif;base64,R0lGODlhAQABAAAAACw="
        return u
    h = re.sub(r"\[\[[^\]]*?Hosting\.Image\(\s*['\"]?(\d+)[^\]]*\]\]", img, html)
    autres = sorted(set(re.findall(r"\[\[[^\]]{0,80}\]\]", h)))[:8]
    if autres: print(idm, "balises restantes :", autres)
    h = re.sub(r"\[\[=?\s*Message\.Link\([^\]]*\)\s*\]\]", "#", h)
    h = re.sub(r"<!--\[\[.*?\]\]-->", "", h, flags=re.S)
    h = re.sub(r"\[\[.*?\]\]", "", h, flags=re.S)
    h = h.replace("<head>", '<head><meta name="robots" content="noindex"><base target="_blank">', 1)
    path = os.path.join(OSDIR, "nl", f"{idm}.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w", encoding="utf-8").write(h)
    ids = re.findall(r"Hosting\.Image\(\s*['\"]?(\d+)", html)
    thumb = next((IMG[i] for i in ids if i in IMG and i not in GENERIC), None)
    if missing:
        print(f"{idm} : images sans adresse connue {sorted(set(missing))}")
    return f"nl/{idm}.html", thumb
previews = {idm: render(idm, c) for idm, c in contents.items()}

rows = []
for b in sorted(batches, key=lambda b: b["dtFirstMessage"], reverse=True)[:12]:
    sent = b.get("Stats_DeliveredCount") or 0
    pct = lambda n: round(100 * n / sent, 1) if sent else None
    rows.append({"date": b["dtFirstMessage"][:10].replace(".", "-"),
                 "nom": names.get(b["idMessage"]),
                 "envoyes": sent,
                 "ouverture": pct(b.get("Stats_ViewCount_Uniques") or 0),
                 "clic": pct(b.get("Stats_ClickCount_Uniques") or 0),
                 "desabonnements": b.get("Stats_OptoutCount") or 0})

# Alerte : un envoi dont l'heure est passée mais qui n'est pas parti (non approuvé)
late = [b for b in res.get("BatchInfos") or [] if not b.get("isTestBach") and not b.get("isCancelled")
        and not b.get("dtFirstMessage") and b.get("dtLaunch")
        and (now - timedelta(days=3)).strftime("%Y.%m.%d %H:%M") < b["dtLaunch"][:16] < now.strftime("%Y.%m.%d %H:%M")]

# Liste complète, une ligne par infolettre (les envois d'une même infolettre sont additionnés)
agg = {}
for b in batches:
    a = agg.setdefault(b["idMessage"], {"d": b["dtFirstMessage"], "dl": 0, "op": 0, "cl": 0, "ou": 0})
    a["d"] = min(a["d"], b["dtFirstMessage"])
    a["dl"] += b.get("Stats_DeliveredCount") or 0
    a["op"] += b.get("Stats_ViewCount_Uniques") or 0
    a["cl"] += b.get("Stats_ClickCount_Uniques") or 0
    a["ou"] += b.get("Stats_OptoutCount") or 0
tous = []
for idm, a in agg.items():
    nom = names.get(idm) or ""
    ap, th = previews.get(idm, (None, None))
    tous.append({"id": idm, "date": a["d"][:10].replace(".", "-"), "nom": nom,
                 "categorie": "Formations" if re.search(r"hebdo|formation", nom, re.I) else "Expos",
                 "envoyes": a["dl"], "ouverture": round(100 * a["op"] / a["dl"], 1) if a["dl"] else None,
                 "clic": round(100 * a["cl"] / a["dl"], 1) if a["dl"] else None,
                 "desabonnements": a["ou"], "vignette": th, "apercu": ap})
# Moyennes des 7 derniers jours (pondérées par le nombre de courriels livrés)
wk = [b for b in batches if b["dtFirstMessage"][:10] >= (now - dt.timedelta(days=7)).strftime("%Y.%m.%d")]
dl = sum(b.get("Stats_DeliveredCount") or 0 for b in wk)
if dl:
    pr = sum(b.get("Stats_ProcessedCount") or 0 for b in wk)
    op = sum(b.get("Stats_ViewCount_Uniques") or 0 for b in wk)
    cl = sum(b.get("Stats_ClickCount_Uniques") or 0 for b in wk)
    ou = sum(b.get("Stats_OptoutCount") or 0 for b in wk)
    sept = {"livraison": round(100 * dl / pr, 1) if pr else None, "ouverture": round(100 * op / dl, 1),
            "clics": round(100 * cl / dl, 1), "ctor": round(100 * cl / op, 1) if op else None,
            "desabonnements": round(100 * ou / dl, 1)}
else:
    sept = None

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
if rows:
    data["infolettres"]["derniers"] = rows
if tous:
    prev = {x.get("id"): x for x in data["infolettres"].get("tous", [])}
    for x in tous:  # garder les captures déjà associées (ex. bilan Expos)
        if prev.get(x["id"], {}).get("capture"):
            x["capture"] = prev[x["id"]]["capture"]
    pris = {(x["date"], x["categorie"]) for x in tous}
    keep = [x for x in prev.values() if (x.get("id") is None and (x["date"], x.get("categorie")) not in pris)
            or (x.get("id") is not None and x["id"] not in agg)]
    for x in tous:  # récupérer la capture d'une ancienne entrée sans id (même date, même catégorie)
        for y in prev.values():
            if y.get("id") is None and y.get("capture") and (y["date"], y.get("categorie")) == (x["date"], x["categorie"]):
                x.setdefault("capture", y["capture"])
    data["infolettres"]["tous"] = sorted(tous + keep, key=lambda x: x["date"], reverse=True)
    if sept:
        data["infolettres"]["sept_jours"] = sept
    data["infolettres"]["source"] = "Dialog Insight (API, relevé automatique)"
data["infolettres"]["releve"] = now.isoformat(timespec="minutes")
data["infolettres"]["alertes"] = [f"Envoi prévu le {b['dtLaunch'][:16]} pas encore parti (approbation?)" for b in late]
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"{len(rows)} envois écrits.")
