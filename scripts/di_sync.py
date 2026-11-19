"""Relève Dialog Insight -> os/data.json (bloc infolettres.derniers).

Appelle Sendings.GetBatches (envois des 45 derniers jours) puis Messages.Get
pour le nom de chaque message. N'écrit que des statistiques agrégées par envoi :
aucune donnée de contact. La clé vient des secrets GitHub (DI_IDKEY, DI_KEY).
"""
import json, os, sys, datetime as dt, urllib.request

BASE = "https://app.dialoginsight.com/webservices/ofc4/"
ID_PROJECT = int(os.environ.get("DI_IDPROJECT", "7991"))  # Contech TC
AUTH = {"idKey": int(os.environ.get("DI_IDKEY") or 34368), "Key": os.environ["DI_KEY"]}
DATA = os.path.join(os.path.dirname(__file__), "..", "os", "data.json")


def call(service, method, payload):
    body = json.dumps({"AuthKey": AUTH, **payload}).encode()
    req = urllib.request.Request(f"{BASE}{service}.ashx?method={method}", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.loads(r.read().decode("utf-8-sig"))
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
                    "dtCreated_Min": (now - dt.timedelta(days=45)).strftime(fmt),
                    "dtCreated_Max": now.strftime(fmt)}})
batches = [b for b in res.get("BatchInfos") or []
           if not b.get("isTestBach") and not b.get("isCancelled") and b.get("dtFirstMessage")]

names = {}
for idm in {b["idMessage"] for b in batches}:
    try:
        m = call("messages", "Get", {"idProject": ID_PROJECT, "idMessage": idm}).get("Message") or {}
        names[idm] = m.get("Name") or f"Message {idm}"
    except SystemExit as e:
        print("Nom introuvable", idm, e)
        names[idm] = f"Message {idm}"

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
        and b["dtLaunch"][:16] < now.strftime("%Y.%m.%d %H:%M")]
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
    if sept:
        data["infolettres"]["sept_jours"] = sept
    data["infolettres"]["source"] = "Dialog Insight (API, relevé automatique)"
data["infolettres"]["releve"] = now.isoformat(timespec="minutes")
data["infolettres"]["alertes"] = [f"Envoi prévu le {b['dtLaunch'][:16]} pas encore parti (approbation?)" for b in late]
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"{len(rows)} envois écrits.")
