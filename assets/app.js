(() => {
  const $ = id => document.getElementById(id);
  const brl = v => (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  const mil = v => 'R$ ' + Math.round((v || 0) / 1000).toLocaleString('pt-BR') + ' mil';
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const faixa = n => n == null ? ['nd', 'Sem dados'] : n >= 70 ? ['good', 'Eficiente'] : n >= 45 ? ['warn', 'Atenção'] : ['bad', 'Baixa eficiência'];
  const cor = n => `var(--${faixa(n)[0]})`;
  const RISCO = { baixo: ['good', 'Risco baixo', 1], moderado: ['warn', 'Risco moderado', 2], alto: ['bad', 'Risco alto', 3] };
  const ini = n => n.split(' ').filter(w => w.length > 2).slice(0, 2).map(w => w[0]).join('');
  const titleCase = s => s.toLowerCase().replace(/(^|\s)\S/g, c => c.toUpperCase());

  let IDX = null, ORD = [], atual = null, aba = 'top', limite = 15;
  const cacheDep = {};

  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  function gauge(n) {
    const cx = 120, cy = 118;
    const pt = (t, R) => [cx + R * Math.cos(t), cy - R * Math.sin(t)];
    const ang = v => Math.PI - (v / 100) * Math.PI;
    const arc = (f, t, R, c, w, extra = '') => {
      const [p, q] = pt(ang(f), R), [u, v] = pt(ang(t), R);
      return `<path d="M${p.toFixed(1)} ${q.toFixed(1)} A${R} ${R} 0 0 1 ${u.toFixed(1)} ${v.toFixed(1)}" stroke="${c}" stroke-width="${w}" fill="none" ${extra}/>`;
    };
    return `${arc(0, 44.5, 100, 'var(--bad)', 4, 'opacity=".5"')}${arc(45.5, 69.5, 100, 'var(--warn)', 4, 'opacity=".5"')}${arc(70.5, 100, 100, 'var(--good)', 4, 'opacity=".5"')}
      ${arc(0, 100, 84, 'var(--line)', 14, 'stroke-linecap="round"')}
      ${n > 0 ? arc(0, n, 84, cor(n), 14, 'stroke-linecap="round"') : ''}
      <text x="120" y="112" text-anchor="middle" font-family="var(--display)" font-weight="800" font-size="44" fill="var(--ink)">${n ?? '–'}</text>
      <text x="120" y="132" text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">de 100</text>
      <text x="16" y="136" font-family="var(--mono)" font-size="10" fill="var(--muted)">0</text>
      <text x="212" y="136" font-family="var(--mono)" font-size="10" fill="var(--muted)">100</text>`;
  }

  function chart(d) {
    const W = 360, H = 190, L = 40, Rt = 8, T = 10, B = 24, iw = W - L - Rt, ih = H - T - B;
    const meses = IDX.periodo.meses;
    const max = Math.max(10000, Math.ceil(Math.max(d.teto || 0, ...d.mensal) / 10000) * 10000);
    const y = v => T + ih - (Math.max(0, v) / max) * ih, bw = iw / 12;
    const passo = max > 60000 ? 20000 : 10000;
    let s = '';
    for (let v = 0; v <= max; v += passo) s += `<line x1="${L}" x2="${W - Rt}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + 3.5}" text-anchor="end" font-size="9.5" font-family="var(--mono)" fill="var(--muted)">${v / 1000}k</text>`;
    d.mensal.forEach((v, i) => {
      const x = L + i * bw + bw * .18;
      s += `<rect x="${x}" y="${y(v)}" width="${bw * .64}" height="${T + ih - y(v)}" rx="2" fill="var(--accent)" opacity="${i === 11 ? 1 : .8}"><title>${meses[i]}: ${brl(v)}</title></rect><text x="${x + bw * .32}" y="${H - 8}" text-anchor="middle" font-size="9" font-family="var(--mono)" fill="var(--muted)">${meses[i].split('/')[0]}</text>`;
    });
    s += `<line x1="${L}" x2="${W - Rt}" y1="${y(IDX.media_mensal)}" y2="${y(IDX.media_mensal)}" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>`;
    if (d.teto) s += `<line x1="${L}" x2="${W - Rt}" y1="${y(d.teto)}" y2="${y(d.teto)}" stroke="var(--bad)" stroke-width="1.5"/>`;
    return s;
  }

  function alertas(d) {
    const out = [], cm = IDX.cat_media || {}, ref = IDX.referencias || {};
    const div = d.total > 0 ? (d.cats['Divulgação do mandato'] || 0) / d.total : 0;
    const noTeto = d.teto ? d.mensal.filter(v => v >= d.teto * .9).length : 0;
    if (noTeto >= 3) out.push(['bad', 'Cota no limite', `Usou 90% ou mais do teto em ${noTeto} dos 12 meses.`]);
    const mdiv = cm['Divulgação do mandato'] || 0;
    if (mdiv && div > mdiv * 1.5 && div > .15) out.push(['bad', 'Gasto alto com divulgação', `${Math.round(div * 100)}% da cota foi para divulgação do mandato. A média da Câmara é ${Math.round(mdiv * 100)}%.`]);
    if (d.presenca && d.presenca.total) {
      const p = d.presenca.presente / d.presenca.total, falt = d.presenca.total - d.presenca.presente;
      if (p < .75) out.push(['bad', 'Muitas ausências', `Faltou a ${falt} de ${d.presenca.total} ${d.presenca.metodo}.`]);
      else if (p < .85) out.push(['warn', 'Ausências acima do normal', `Faltou a ${falt} de ${d.presenca.total} ${d.presenca.metodo}.`]);
    }
    if (ref.prod_p25 != null && d.props.n <= ref.prod_p25) out.push(['warn', 'Pouca produção legislativa', `Apresentou ${d.props.n} proposições como primeiro autor em 12 meses. A mediana da Câmara é ${ref.prod_mediana}.`]);
    if (d.meses_ativos && d.medio < IDX.media_mensal * .8) out.push(['good', 'Gasto abaixo da média', `Gastou em média ${mil(d.medio)} por mês, ${Math.round((1 - d.medio / IDX.media_mensal) * 100)}% abaixo da média da Câmara.`]);
    if (ref.efet_p75 && d.props.avancadas >= Math.max(1, ref.efet_p75)) out.push(['good', 'Proposições que avançam', `${d.props.avancadas} proposições aprovadas, enviadas ao Senado ou prontas para votação.`]);
    if (!out.length) out.push(['good', 'Nenhum alerta', 'Nenhum critério fora do padrão no período.']);
    return out.map(([c, t, p]) => `<div class="alert ${c}"><b>${t}</b><p>${p}</p></div>`).join('');
  }

  const tagSit = s => /norma jur|sanç|senado|aprovad|promulg|pronta para pauta/i.test(s) ? 'v-good' : /arquiv|retirad|prejudic|devolvid/i.test(s) ? 'v-bad' : 'v-warn';

  function render(d) {
    const [fc, fl] = faixa(d.nota);
    $('av').innerHTML = d.foto ? `<img src="${esc(d.foto)}" alt="" loading="lazy" onerror="this.replaceWith(document.createTextNode('${esc(ini(d.nome))}'))">` : esc(ini(d.nome));
    $('nome').textContent = d.nome;
    $('meta').textContent = `Deputado(a) federal · ${d.partido} · ${d.uf}`;
    $('facts').innerHTML = `<span class="chip">${IDX.periodo.meses[0]} a ${IDX.periodo.meses[11]}</span><a class="chip" href="https://www.camara.leg.br/deputados/${d.id}" target="_blank" rel="noopener">Página oficial na Câmara ↗</a>`;
    $('gauge').innerHTML = gauge(d.nota);
    $('gauge').setAttribute('aria-label', `Índice ${d.nota ?? 'indisponível'} de 100`);
    $('verdict').className = 'verdict v-' + fc; $('verdict').textContent = fl;
    const pos = ORD.findIndex(x => x.id === d.id) + 1;
    const doUF = ORD.filter(x => x.uf === d.uf); const posUF = doUF.findIndex(x => x.id === d.id) + 1;
    $('rank').textContent = pos ? `${pos}º de ${ORD.length} no Brasil · ${posUF}º de ${doUF.length} em ${d.uf}` : '';

    const S = d.scores || {}, P = IDX.pesos || {};
    const comps = [];
    if ('pres' in P) comps.push(['Presença', P.pres, S.pres, d.presenca ? `${d.presenca.presente} de ${d.presenca.total} ${d.presenca.metodo}` : 'Sem registro de presença no período']);
    if ('econ' in P) comps.push(['Uso responsável da cota', P.econ, S.econ, d.meses_ativos ? `Média de ${mil(d.medio)}/mês, teto de ${mil(d.teto)}` : 'Sem gastos registrados no período']);
    if ('prod' in P) comps.push(['Produção legislativa', P.prod, S.prod, `${d.props.n} proposições como primeiro autor`]);
    if ('efet' in P) comps.push(['Efetividade', P.efet, S.efet, `${d.props.avancadas} aprovadas, no Senado ou prontas para votação`]);
    $('comps').innerHTML = comps.map(([n, w, s, t]) => `<div class="comp"><div class="row"><div><strong>${n}</strong><span class="peso">peso ${Math.round(w * 100)}%</span></div><span class="num" style="color:${cor(s)}">${s ?? '–'}</span></div><div class="bar"><i style="width:${s ?? 0}%;background:${cor(s)}"></i></div><p>${t}</p></div>`).join('');

    $('alerts').innerHTML = alertas(d);

    const [rc, rl, rn] = RISCO[d.risco.nivel] || RISCO.baixo;
    $('riskpill').className = 'riskpill v-' + rc; $('riskpill').textContent = `${rl} de irregularidade`;
    $('riskLvl').textContent = `${rl} · ${d.risco.pontos} ${d.risco.pontos === 1 ? 'ponto' : 'pontos'}`; $('riskLvl').style.color = `var(--${rc})`;
    document.querySelectorAll('#riskMeter i').forEach((el, j) => el.style.background = j < rn ? `var(--${rc})` : 'var(--line)');
    const tx = { good: 'OK', warn: 'Atenção', bad: 'Risco', nd: 'Sem dados', breve: 'Em breve' };
    const dotc = { good: 'good', warn: 'warn', bad: 'bad', nd: 'nd', breve: 'nd' };
    $('checks').innerHTML = d.risco.checks.map(c => `<div class="check"><span class="dot" style="background:var(--${dotc[c.status]})"></span><div><div class="ct"><b>${esc(c.titulo)}</b><span class="tag v-${c.status}">${tx[c.status]}</span></div><p>${esc(c.texto)}</p></div></div>`).join('');
    const maxf = Math.max(1, ...d.fornecedores.map(f => f.pct));
    $('forn').innerHTML = d.fornecedores.length ? d.fornecedores.map(f => {
      const sub = [f.categoria, f.cnpj ? 'CNPJ ' + f.cnpj.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5') : ''].filter(Boolean).join(' · ');
      return `<div class="fitem"><div class="fhead"><span class="fname">${esc(titleCase(f.nome))}</span><span class="num fval">${brl(f.valor)}</span></div><div class="bar"><i style="width:${f.pct / maxf * 100}%;background:${f.flags.length ? 'var(--bad)' : 'var(--accent)'}"></i></div><div class="fsub"><span>${esc(sub)}</span><span class="num">${f.pct.toLocaleString('pt-BR')}% da cota</span></div>${f.flags.length ? `<div class="flags">${f.flags.map(s => `<span>${esc(s)}</span>`).join('')}</div>` : ''}</div>`;
    }).join('') : '<p class="meta">Nenhum gasto registrado no período.</p>';

    $('gTotal').textContent = brl(d.total);
    $('gPct').textContent = d.teto && d.meses_ativos ? Math.round(d.total / (d.teto * d.meses_ativos) * 100) + '%' : '–';
    $('chart').innerHTML = chart(d);

    const cats = Object.entries(d.cats);
    const maxc = Math.max(1, ...cats.map(c => c[1])), cm = IDX.cat_media || {};
    $('cats').innerHTML = cats.length ? cats.slice(0, 8).map(([nome, v]) => {
      const share = d.total > 0 ? v / d.total : 0, med = cm[nome] || 0;
      const alto = med && share > med * 1.5 && share > .1;
      return `<div class="cat"><div class="row"><span>${esc(nome)}</span><span class="num">${brl(v)}</span></div><div class="bar"><i style="width:${v / maxc * 100}%;background:${alto ? 'var(--bad)' : 'var(--accent)'}"></i></div><em>${Math.round(share * 100)}% do total · média da Câmara ${Math.round(med * 100)}%${alto ? ' · <b style="color:var(--bad)">acima da média</b>' : ''}</em></div>`;
    }).join('') : '<p class="meta">Nenhum gasto registrado no período.</p>';

    if (d.presenca && d.presenca.total) {
      const pr = d.presenca.presente, tot = d.presenca.total, au = tot - pr;
      $('presBig').innerHTML = `<div><span class="num">${Math.round(pr / tot * 100)}%</span><span class="meta">de presença</span></div><div><span class="num">${au}</span><span class="meta">ausências</span></div>`;
      $('presBar').innerHTML = `<i style="width:${pr / tot * 100}%;background:var(--good)"></i><i style="width:${au / tot * 100}%;background:var(--bad)"></i>`;
      $('presNote').textContent = `Base: ${tot} ${d.presenca.metodo}. Os dados abertos não informam se a falta foi justificada (missão oficial, licença médica).`;
    } else {
      $('presBig').innerHTML = '<div><span class="num">–</span><span class="meta">sem registros no período</span></div>';
      $('presBar').innerHTML = ''; $('presNote').textContent = '';
    }

    $('propBig').innerHTML = `<div><span class="num">${d.props.n}</span><span class="meta">apresentadas</span></div><div><span class="num">${d.props.avancadas}</span><span class="meta">avançaram</span></div>`;
    $('props').innerHTML = d.props.lista.length ? d.props.lista.map(p => `<a class="prop" href="${esc(p.url)}" target="_blank" rel="noopener"><div class="ph"><code>${esc(p.tipo)} ${esc(p.numero)}/${esc(p.ano)}</code><span class="tag ${tagSit(p.situacao)}">${esc(p.situacao || 'Em tramitação')}</span></div><span class="t">${esc(p.ementa)}</span></a>`).join('') : '<p class="meta">Nenhuma proposição como primeiro autor no período.</p>';

    renderRank();
  }

  async function abrir(id, rolar = true) {
    atual = +id;
    try {
      const d = cacheDep[id] || (cacheDep[id] = await getJSON(`data/dep/${id}.json`));
      $('perfil').hidden = false; $('loading').hidden = true;
      render(d);
      if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
      document.title = `${d.nome} · Radar Político`;
      if (rolar) window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      $('loading').hidden = false; $('loading').textContent = 'Não foi possível carregar a ficha deste deputado.';
    }
  }

  function lista() {
    const uf = $('ufSel').value;
    let l = ORD.filter(x => !uf || x.uf === uf);
    if (aba === 'bottom') l = l.filter(x => x.nota != null).reverse();
    if (aba === 'risco') l = [...l].sort((a, b) => b.pontos - a.pontos || (a.nota ?? 0) - (b.nota ?? 0));
    return l;
  }

  function renderRank() {
    const l = lista();
    $('ranklist').innerHTML = l.slice(0, limite).map((x, i) => {
      const r = RISCO[x.risco] || RISCO.baixo;
      const val = aba === 'risco' ? `<span class="verdict v-${r[0]}" style="font-size:11px;padding:2px 8px">${x.pontos} pts</span>` : `<span class="bar"><i style="width:${x.nota ?? 0}%;background:${cor(x.nota)}"></i></span>`;
      return `<button type="button" data-id="${x.id}" class="${x.id === atual ? 'on' : ''}"><span class="n">${i + 1}</span><span class="nm"><span>${esc(x.nome)}</span><small>${esc(x.partido)} · ${esc(x.uf)}</small></span>${val}<span class="num" style="color:${cor(x.nota)};text-align:right">${x.nota ?? '–'}</span></button>`;
    }).join('');
    $('more').hidden = l.length <= limite;
  }

  function sugerir() {
    const t = norm($('q').value.trim());
    const sg = $('sugg');
    if (!t) { sg.hidden = true; return; }
    const m = IDX.deputados.filter(d => norm(d.nome).includes(t) || norm(d.partido) === t || norm(d.uf) === t).slice(0, 12);
    sg.innerHTML = m.length ? m.map(d => `<button type="button" data-id="${d.id}"><span>${esc(d.nome)}</span><small>${esc(d.partido)} · ${esc(d.uf)} · nota ${d.nota ?? '–'}</small></button>`).join('') : '<button type="button" disabled><span>Nenhum deputado encontrado</span><small>Tente outro nome</small></button>';
    sg.hidden = false;
  }

  async function iniciar() {
    try {
      IDX = await getJSON('data/index.json');
    } catch (e) {
      $('loading').innerHTML = 'Os dados ainda estão sendo gerados pelo robô de atualização.<br>Volte em alguns minutos.';
      return;
    }
    ORD = IDX.deputados.filter(d => d.nota != null);
    const [a, h] = (IDX.atualizado || '').split(' ');
    $('upd').textContent = a ? `Dados atualizados em ${a.split('-').reverse().join('/')} às ${h}` : '';
    if (IDX.fontes && IDX.fontes.presenca) $('mPres').textContent = IDX.fontes.presenca;
    if (IDX.referencias && IDX.referencias.prod_p90) $('mProd').textContent = `${IDX.referencias.prod_p90} ou mais no período (nível dos 10% mais produtivos)`;
    const ufs = [...new Set(IDX.deputados.map(d => d.uf))].sort();
    $('ufSel').innerHTML += ufs.map(u => `<option value="${u}">${u}</option>`).join('');
    $('rankCard').hidden = false;

    const alvo = location.hash.replace('#', '');
    const ok = IDX.deputados.some(d => String(d.id) === alvo);
    await abrir(ok ? alvo : (ORD[0] || IDX.deputados[0]).id, false);
  }

  $('q').addEventListener('input', sugerir);
  $('q').addEventListener('keydown', e => {
    if (e.key === 'Enter') { const b = $('sugg').querySelector('button[data-id]'); if (b) b.click(); }
  });
  $('sugg').addEventListener('click', e => {
    const b = e.target.closest('button[data-id]'); if (!b) return;
    $('q').value = ''; $('sugg').hidden = true; $('q').blur(); abrir(b.dataset.id);
  });
  $('ranklist').addEventListener('click', e => { const b = e.target.closest('button[data-id]'); if (b) abrir(b.dataset.id); });
  $('tabs').addEventListener('click', e => {
    const b = e.target.closest('button[data-t]'); if (!b) return;
    aba = b.dataset.t; limite = 15;
    $('tabs').querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b));
    renderRank();
  });
  $('ufSel').addEventListener('change', () => { limite = 15; renderRank(); });
  $('more').addEventListener('click', () => { limite += 30; renderRank(); });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) $('sugg').hidden = true; });
  window.addEventListener('hashchange', () => { const id = location.hash.slice(1); if (id && +id !== atual) abrir(id); });

  iniciar();
})();
