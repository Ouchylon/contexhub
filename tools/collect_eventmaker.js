// Collecte Eventmaker — à exécuter dans un onglet app.eventmaker.io connecté.
// Renvoie seulement des totaux (aucune donnée personnelle) : catégories, rythme des visiteurs et sources.
(async () => {
  const EV = { MTL: ['697b1e2241451e597e73023b', '2026-11-12'], QC: ['697b1f374b62e82cf65bac6c', '2026-10-22'] };
  const grp = n => /visiteur/i.test(n) ? 'visiteurs' : /tudiant/i.test(n) ? 'etudiants' : /repr/i.test(n) ? 'representants'
    : /exposant/i.test(n) && !/sondage/i.test(n) ? 'exposants' : /conf/i.test(n) ? 'conferenciers' : null;
  const LAB = { visiteurs: 'Visiteurs', etudiants: 'Étudiants', exposants: 'Exposants', representants: "Représentants d'exposants", conferenciers: 'Conférenciers' };
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
  const now = new Date(); const today = day(now.toISOString());
  const out = { collecte: now.toISOString(), categories: [], rythme: [], sources: [] };
  for (const [k, [id, jj]] of Object.entries(EV)) {
    const cats = await (await fetch(`/api/v1/events/${id}/guest_categories.json?locale=fr`)).json();
    const cname = Object.fromEntries(cats.map(c => [c._id, c.name]));
    const all = [];
    for (let p = 1; p < 60; p++) {
      const r = await (await fetch(`/api/v1/events/${id}/guests.json?locale=fr&q=status%3Aregistered&page=${p}&per_page=500`)).json();
      const arr = Array.isArray(r) ? r : (r.guests || r.data || []);
      all.push(...arr); if (arr.length < 500) break;
    }
    const ins = {}, ven = {}, perDay = {}, so = {};
    for (const g of all) {
      const G = grp(cname[g.guest_category_id] || ''); if (!G) continue;
      ins[G] = (ins[G] || 0) + 1; if (g.showed_up || (g.attended_dates && g.attended_dates.length)) ven[G] = (ven[G] || 0) + 1;
      if (G === 'visiteurs') { const d = day(g.registered_at || g.created_at); perDay[d] = (perDay[d] || 0) + 1;
        const s = src(g.utm_source || g.utm_medium); so[s] = (so[s] || 0) + 1; }
    }
    for (const G of Object.keys(LAB)) out.categories.push({ expo: k, groupe: LAB[G], cle: G, inscrits: ins[G] || 0, venus: ven[G] || 0 });
    const J = new Date(jj + 'T12:00:00Z'); const days = Object.keys(perDay).sort();
    for (let j = -60; j <= 0; j++) {
      const d = new Date(J.getTime() + j * 864e5).toISOString().slice(0, 10); if (d > today) break;
      const cumul = days.filter(x => x <= d).reduce((a, x) => a + perDay[x], 0);
      out.rythme.push({ expo: k, j, jour: d, n: perDay[d] || 0, cumul });
    }
    Object.entries(so).sort((a, b) => b[1] - a[1]).forEach(([s, n]) => out.sources.push({ expo: k, source: s, n }));
  }
  // Format compact (Montréal seulement) pour le transfert
  const m = { collecte: out.collecte,
    r: out.rythme.filter(x => x.expo === 'MTL').map(x => [x.j, x.n, x.cumul]),
    c: out.categories.filter(x => x.expo === 'MTL').map(x => [x.cle, x.inscrits, x.venus]),
    s: out.sources.filter(x => x.expo === 'MTL').map(x => [x.source, x.n]) };
  return JSON.stringify(m);
})()
