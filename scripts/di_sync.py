"""Relève Dialog Insight -> os/data.json (bloc infolettres.derniers).

Appelle Sendings.GetBatches (envois des 45 derniers jours) puis Messages.Get
pour le nom de chaque message. N'écrit que des statistiques agrégées par envoi :
aucune donnée de contact. La clé vient des secrets GitHub (DI_IDKEY, DI_KEY).
"""
import json, os, sys, datetime as dt, urllib.request

BASE = "https://app.dialoginsight.com/webservices/ofc4/"
ID_PROJECT = int(os.environ.get("DI_IDPROJECT", "7991"))  # Contech TC
AUTH = {"idKey": int(os.environ["DI_IDKEY"]), "Key": os.environ["DI_KEY"]}
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
if batches:  # trace utile au premier passage : noms des champs seulement, aucune valeur
    print("Champs BatchInfo :", sorted(batches[0].keys()))

names = {}
for idm in {b["idMessage"] for b in batches}:
    try:
        m = call("messages", "Get", {"idProject": ID_PROJECT, "idMessage": idm}).get("Message") or {}
        names[idm] = m.get("Name") or m.get("Description") or f"Message {idm}"
    except SystemExit as e:
        print("Nom introuvable", idm, e)
        names[idm] = f"Message {idm}"

rows = []
for b in sorted(batches, key=lambda b: b["dtFirstMessage"], reverse=True)[:12]:
    sent = pick(b, "deliver") or pick(b, "sent", exclude=("test",)) or pick(b, "nb", "message")
    opens = pick(b, "open", "unique") or pick(b, "open")
    clicks = pick(b, "click", "unique") or pick(b, "click")
    pct = lambda n: round(100 * n / sent, 1) if sent and n is not None else None
    rows.append({"date": b["dtFirstMessage"][:10].replace(".", "-"),
                 "nom": names.get(b["idMessage"]),
                 "envoyes": sent, "ouverture": pct(opens), "clic": pct(clicks)})

with open(DATA, encoding="utf-8") as f:
    data = json.load(f)
if rows:
    data["infolettres"]["derniers"] = rows
    data["infolettres"]["source"] = "Dialog Insight (API, relevé automatique)"
data["infolettres"]["releve"] = now.isoformat(timespec="minutes")
with open(DATA, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=1)
print(f"{len(rows)} envois écrits.")
