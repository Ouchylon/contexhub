# Usage : python3 tools/build_live.py '<json compact renvoyé par collect_eventmaker.js>'
import json, sys, datetime as dt
m = json.loads(sys.argv[1]); J = dt.date(2026, 11, 12)
LAB = {'visiteurs': 'Visiteurs', 'etudiants': 'Étudiants', 'exposants': 'Exposants', 'representants': "Représentants d'exposants", 'conferenciers': 'Conférenciers'}
live = {'collecte': m['collecte'],
        'rythme': [{'expo': 'MTL', 'j': j, 'jour': (J + dt.timedelta(days=j)).isoformat(), 'n': n, 'cumul': c} for j, n, c in m['r']],
        'categories': [{'expo': 'MTL', 'groupe': LAB[k], 'cle': k, 'inscrits': i, 'venus': v} for k, i, v in m['c']],
        'sources': [{'expo': 'MTL', 'source': s, 'n': n} for s, n in m['s']]}
assert live['rythme'] and live['categories'], 'données vides'
json.dump(live, open('data/live.json', 'w'), ensure_ascii=False)
print('ok', live['rythme'][-1], [c['inscrits'] for c in live['categories']])
