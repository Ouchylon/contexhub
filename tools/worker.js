// Relais Cloudflare : lit les inscriptions de l'Expo Contech Montréal dans Eventmaker
// et renvoie seulement des totaux (aucune donnée personnelle), au même format que data/live.json.
// La clé Eventmaker est gardée dans le secret EM_TOKEN du Worker.
const EV = '697b1e2241451e597e73023b', JOUR_J = '2026-11-12', TTL = 60;
const ORIGINES = ['https://ouchylon.github.io'];
const LAB = { visiteurs: 'Visiteurs', etudiants: 'Étudiants', exposants: 'Exposants', representants: "Représentants d'exposants", conferenciers: 'Conférenciers' };
const grp = n => /visiteur/i.test(n) ? 'visiteurs' : /tudiant/i.test(n) ? 'etudiants' : /repr/i.test(n) ? 'representants'
  : /exposant/i.test(n) && !/sondage/i.test(n) ? 'exposants' : /conf/i.test(n) ? 'conferenciers' : null;
const day = s => new Date(new Date(s).getTime() - 5 * 3600e3).toISOString().slice(0, 10);
const src = s => { s = String(s || '').toLowerCase();
  if (!s || s === 'website' || s === 'direct') return 'Site web';
  if (/newsletter|infolettre|hs_email|dialog/.test(s)) return 'Infolettres';
  if (/facebook|^fb$|meta|instagram|^ig$/.test(s)) return 'Facebook (pubs et page)';
  if (/linkedin/.test(s)) return 'LinkedIn';
  if (/@groupecontex\.ca/.test(s)) return "Envois ciblés de l'équipe";
  if (s === 'eventmaker') return 'Courriels Eventmaker';
  if (/chatgpt|perplexity|gemini|copilot|claude/.test(s)) return 'ChatGPT et IA';
  if (/magic link/.test(s)) return "Connexion à l'app";
  return 'Autres'; };

async function em(env, path) {
  const sep = path.includes('?') ? '&' : '?';
  const r = await fetch(`https://app.eventmaker.io/api/v1${path}${sep}auth_token=${encodeURIComponent(env.EM_TOKEN)}`);
  if (!r.ok) throw new Error('Eventmaker ' + r.status);
  return r.json();
}

async function releve(env) {
  const now = new Date(), today = day(now.toISOString());
  const cats = await em(env, `/events/${EV}/guest_categories.json?locale=fr`);
  const cname = Object.fromEntries(cats.map(c => [c._id, c.name]));
  const all = [];
  for (let p = 1; p < 60; p++) {
    const r = await em(env, `/events/${EV}/guests.json?locale=fr&q=status%3Aregistered&page=${p}&per_page=500`);
    const arr = Array.isArray(r) ? r : (r.guests || r.data || []);
    all.push(...arr); if (arr.length < 500) break;
  }
  const ins = {}, ven = {}, perDay = {}, so = {};
  for (const g of all) {
    const G = grp(cname[g.guest_category_id] || ''); if (!G) continue;
    ins[G] = (ins[G] || 0) + 1;
    if (g.showed_up || (g.attended_dates && g.attended_dates.length)) ven[G] = (ven[G] || 0) + 1;
    if (G === 'visiteurs') {
      const d = day(g.registered_at || g.created_at); perDay[d] = (perDay[d] || 0) + 1;
      const s = src(g.utm_source || g.utm_medium); so[s] = (so[s] || 0) + 1;
    }
  }
  const out = { collecte: now.toISOString(), rythme: [], categories: [], sources: [] };
  for (const G of Object.keys(LAB)) out.categories.push({ expo: 'MTL', groupe: LAB[G], cle: G, inscrits: ins[G] || 0, venus: ven[G] || 0 });
  const J = new Date(JOUR_J + 'T12:00:00Z'), days = Object.keys(perDay).sort();
  for (let j = -60; j <= 0; j++) {
    const d = new Date(J.getTime() + j * 864e5).toISOString().slice(0, 10); if (d > today) break;
    const cumul = days.filter(x => x <= d).reduce((a, x) => a + perDay[x], 0);
    out.rythme.push({ expo: 'MTL', j, jour: d, n: perDay[d] || 0, cumul });
  }
  Object.entries(so).sort((a, b) => b[1] - a[1]).forEach(([s, n]) => out.sources.push({ expo: 'MTL', source: s, n }));
  return out;
}

export default {
  async fetch(req, env, ctx) {
    const o = req.headers.get('Origin') || '';
    const cors = { 'Access-Control-Allow-Origin': ORIGINES.includes(o) ? o : ORIGINES[0], 'Vary': 'Origin' };
    if (req.method === 'OPTIONS') return new Response(null, { headers: { ...cors, 'Access-Control-Allow-Methods': 'GET' } });
    const cache = caches.default, key = new Request('https://contexhub-live/releve');
    let res = await cache.match(key);
    if (!res) {
      try {
        const body = JSON.stringify(await releve(env));
        res = new Response(body, { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': `public, max-age=${TTL}` } });
        ctx.waitUntil(cache.put(key, res.clone()));
      } catch (e) {
        return new Response(JSON.stringify({ erreur: String(e.message || e) }), { status: 502, headers: { ...cors, 'Content-Type': 'application/json' } });
      }
    }
    const h = new Headers(res.headers); for (const [k, v] of Object.entries(cors)) h.set(k, v); h.set('Cache-Control', 'no-store');
    return new Response(res.body, { status: 200, headers: h });
  }
};
