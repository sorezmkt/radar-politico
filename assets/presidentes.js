(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, c = 1) => v == null ? '–' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
  const faixa = n => n == null ? 'nd' : n >= 67 ? 'good' : n >= 34 ? 'warn' : 'bad';
  const anoDe = s => s ? s.slice(0, 4) : 'hoje';
  const periodo = m => `${anoDe(m.inicio)}–${m.termino ? anoDe(m.termino) : 'hoje'}`;
  const ordinal = n => `${n}º`;

  let D = null;

  function areaBar(nome, nota) {
    return `<div class="abar"><span class="an">${esc(nome)}</span><span class="bar"><i style="width:${nota ?? 0}%;background:var(--${faixa(nota)})"></i></span><span class="av num">${nota ?? '–'}</span></div>`;
  }

  function placarTxt(m) {
    const p = m.placar; if (!p || !p.total) return '';
    const w = v => `${v / p.total * 100}%`;
    return `<div class="placar">
      <div class="pbar" aria-hidden="true"><i style="width:${w(p.melhor)};background:var(--good)"></i><i style="width:${w(p.igual)};background:var(--nd)"></i><i style="width:${w(p.pior)};background:var(--bad)"></i></div>
      <p>Entregou o país <b style="color:var(--good)">melhor em ${p.melhor}</b>${p.igual ? `, igual em ${p.igual}` : ''} e <b style="color:var(--bad)">pior em ${p.pior}</b> de ${p.total} indicadores</p>
    </div>`;
  }

  // ------------------------------------------------------------ lista
  function lista(area) {
    const ms = [...D.mandatos];
    if (area) ms.sort((a, b) => (b.areas[area] ?? -1) - (a.areas[area] ?? -1));
    $('ordemtxt').textContent = area
      ? `Ordenado pelo resultado em ${area.toLowerCase()}, do melhor para o pior entre os mandatos. Isso não é uma nota geral do presidente.`
      : 'Em ordem cronológica. Cada barra compara o mandato com os outros naquela área: cheia é o melhor resultado entre eles, vazia é o pior.';
    $('mlist').innerHTML = ms.map(m => `<li><a href="presidente.html?id=${m.id}">
      <div class="mh">
        <div><span class="mn">${esc(m.nome)}</span><small>${esc(m.rotulo)} · ${periodo(m)} · ${esc(m.partido)}</small></div>
        ${m.em_andamento ? '<span class="tag v-warn">Parcial</span>' : ''}
      </div>
      ${placarTxt(m)}
      ${area
        ? `<div class="mbig">${areaBar(area, m.areas[area])}</div>`
        : `<div class="mareas">${D.areas.map(a => areaBar(a, m.areas[a])).join('')}</div>`}
    </a></li>`).join('');
  }

  // cor contínua da nota: vermelho (0) → amarelo (50) → verde (100)
  const corNota = n => n == null ? 'var(--line)' : n >= 67 ? 'var(--good)' : n >= 34 ? 'var(--warn)' : 'var(--bad)';
  const opNota = n => n == null ? 1 : n >= 67 ? .45 + (n - 67) / 33 * .55 : n >= 34 ? .75 : .45 + (33 - n) / 33 * .55;

  function mapa() {
    const ms = D.mandatos, inds = D.indicadores.filter(i => i.melhor !== 'neutro');
    let h = `<thead><tr><th></th>${ms.map(m => `<th><a href="presidente.html?id=${m.id}">${esc(m.sigla || m.curto)}${m.em_andamento ? '*' : ''}</a></th>`).join('')}</tr></thead><tbody>`;
    D.areas.forEach(a => {
      const linhas = inds.filter(i => i.area === a); if (!linhas.length) return;
      h += `<tr class="hmarea"><th colspan="${ms.length + 1}">${esc(a)}</th></tr>`;
      linhas.forEach(ind => {
        h += `<tr><th>${esc(ind.nome)}</th>${ms.map(m => {
          const r = m.indicadores[ind.id], n = r ? r.nota : null;
          const tip = r ? `${m.sigla}: ${ind.nome} — ${r.posicao ? (r.posicao === 1 ? 'melhor' : r.posicao === r.total ? 'pior' : r.posicao + 'º melhor') + ' de ' + r.total : 'sem comparação'}` : `${m.sigla}: sem dados`;
          return `<td title="${esc(tip)}"><span style="background:${corNota(n)};opacity:${opNota(n)}"></span></td>`;
        }).join('')}</tr>`;
      });
    });
    $('hm').innerHTML = h + '</tbody>';
  }

  function duelo() {
    const A = D.mandatos.find(m => m.id === $('dA').value), B = D.mandatos.find(m => m.id === $('dB').value);
    if (!A || !B) return;
    let va = 0, vb = 0;
    const linha = (ind) => {
      const ra = A.indicadores[ind.id], rb = B.indicadores[ind.id];
      if (!ra && !rb) return '';
      const neutro = ind.melhor === 'neutro';
      let w = '';
      if (!neutro && ra && rb && ra.nota != null && rb.nota != null && ra.nota !== rb.nota) { w = ra.nota > rb.nota ? 'a' : 'b'; w === 'a' ? va++ : vb++; }
      const cel = (r, lado) => {
        if (!r) return `<div class="dc nd">sem dados</div>`;
        const ini = r.recebeu ? fmt(r.recebeu.valor, ind.casas) : '–', fim = r.entregou ? fmt(r.entregou.valor, ind.casas) : '–';
        const media = r.media != null ? `<small>média ${fmt(r.media, ind.casas)}</small>` : '';
        const vc = { melhor: 'good', pior: 'bad', igual: 'nd' }[r.veredito] || 'nd';
        return `<div class="dc ${w === lado ? 'win' : ''}"><span class="num">${ini} → ${fim}</span>${media}${r.veredito ? `<span class="tag v-${vc}">${r.veredito === 'melhor' ? 'Melhorou' : r.veredito === 'pior' ? 'Piorou' : 'Igual'}</span>` : ''}</div>`;
      };
      return `<div class="drow"><div class="dn">${esc(ind.nome)}<small>${esc(ind.unidade)}${neutro ? ' · sem selo' : ''}</small></div>${cel(ra, 'a')}${cel(rb, 'b')}</div>`;
    };
    let corpo = '';
    D.areas.forEach(a => {
      const rows = D.indicadores.filter(i => i.area === a).map(linha).join('');
      if (rows) corpo += `<div class="label dlab">${esc(a)}</div>${rows}`;
    });
    const nome = m => `${esc(m.sigla)} <small>${periodo(m)}</small>`;
    const tot = va + vb;
    $('dres').innerHTML = `<div class="dplacar">
        <div class="dp ${va > vb ? 'lead' : ''}"><span class="dpn">${nome(A)}</span><span class="dpv num">${va}</span></div>
        <div class="dp ${vb > va ? 'lead' : ''}"><span class="dpn">${nome(B)}</span><span class="dpv num">${vb}</span></div>
      </div>
      <div class="dbar" aria-hidden="true"><i style="width:${tot ? va / tot * 100 : 50}%"></i><i style="width:${tot ? vb / tot * 100 : 50}%"></i></div>
      <p class="note">Indicadores em que cada governo teve o melhor resultado na comparação entre todos os mandatos. ${A.em_andamento || B.em_andamento ? 'Mandato em andamento ainda tem dados parciais. ' : ''}Cada linha mostra como o governo recebeu → como entregou.</p>
      <div class="dhead"><span></span><span>${esc(A.sigla)}</span><span>${esc(B.sigla)}</span></div>${corpo}`;
  }

  function iniciarDuelo() {
    const curto = m => `${anoDe(m.inicio).slice(2)}–${m.termino ? anoDe(m.termino).slice(2) : 'hoje'}`;
    const opts = D.mandatos.map(m => `<option value="${m.id}">${esc(m.sigla)} ${curto(m)}</option>`).join('');
    $('dA').innerHTML = opts; $('dB').innerHTML = opts;
    const n = D.mandatos.length;
    $('dA').value = D.mandatos[n - 2].id; $('dB').value = D.mandatos[n - 1].id;
    $('dA').addEventListener('change', duelo); $('dB').addEventListener('change', duelo);
    duelo();
  }

  function iniciarLista() {
    iniciarDuelo();
    mapa();
    const sel = $('areasel');
    sel.innerHTML = [['', 'Linha do tempo'], ...D.areas.map(a => [a, a])]
      .map(([v, t], i) => `<button type="button" data-a="${esc(v)}" aria-pressed="${i === 0}">${esc(t)}</button>`).join('');
    sel.addEventListener('click', e => {
      const b = e.target.closest('button[data-a]'); if (!b) return;
      sel.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', x === b));
      lista(b.dataset.a);
    });
    lista('');
  }

  // ------------------------------------------------------------ detalhe
  function grafico(ind, m) {
    const s = D.series[ind.id]; if (!s || !s.brasil.length) return '';
    const br = s.brasil, rg = s.regiao || [];
    const anos = br.map(p => p[0]), a0 = Math.min(...anos), a1 = Math.max(...anos);
    const vals = [...br, ...rg.filter(p => p[0] >= a0)].map(p => p[1]);
    let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * .12 || 1; lo -= pad; hi += pad;
    if (lo > 0 && lo < (hi - lo) * .4) lo = 0;
    const W = 340, H = 130, L = 34, R = 8, T = 8, B = 20, iw = W - L - R, ih = H - T - B;
    const x = a => L + (a - a0) / Math.max(1, a1 - a0) * iw, y = v => T + ih - (v - lo) / (hi - lo) * ih;
    const path = pts => pts.filter(p => p[0] >= a0).map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join(' ');
    const ini = Math.max(a0, m.base), fim = Math.min(a1, m.fim || a1);
    let g = `<rect x="${x(ini)}" y="${T}" width="${Math.max(2, x(fim) - x(ini))}" height="${ih}" fill="var(--accent-soft)"/>`;
    [lo + (hi - lo) * .1, (lo + hi) / 2, hi - (hi - lo) * .1].forEach(v => {
      g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 4}" y="${y(v) + 3}" text-anchor="end" font-size="9" font-family="var(--mono)" fill="var(--muted)">${fmt(v, Math.abs(v) >= 100 ? 0 : 1)}</text>`;
    });
    const passo = a1 - a0 > 20 ? 10 : 5;
    for (let a = Math.ceil(a0 / passo) * passo; a <= a1; a += passo) g += `<text x="${x(a)}" y="${H - 5}" text-anchor="middle" font-size="9" font-family="var(--mono)" fill="var(--muted)">${a}</text>`;
    if (rg.length) g += `<path d="${path(rg)}" fill="none" stroke="var(--muted)" stroke-width="1.5" stroke-dasharray="4 3"/>`;
    g += `<path d="${path(br)}" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round"/>`;
    br.filter(p => p[0] >= ini && p[0] <= fim).forEach(p => { g += `<circle cx="${x(p[0])}" cy="${y(p[1])}" r="2.6" fill="var(--accent)"><title>${p[0]}: ${fmt(p[1], ind.casas)}</title></circle>`; });
    return `<div class="chartbox"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Série histórica de ${esc(ind.nome)}">${g}</svg></div>
      <div class="legend"><span><i style="background:var(--accent)"></i>Brasil</span>${rg.length ? '<span><i style="background:var(--muted);height:2px"></i>América Latina e Caribe</span>' : ''}<span><i style="background:var(--accent-soft)"></i>Período do mandato</span></div>`;
  }

  function cartaoIndicador(ind, r, m) {
    if (!r) return `<div class="ind"><div class="ih"><b>${esc(ind.nome)}</b><span class="tag v-nd">Sem dados</span></div><p class="note">${esc(ind.explica)} Não há dados para este período.</p></div>`;
    const bom = r.nota != null ? faixa(r.nota) : 'nd';
    let corpo;
    if (r.media != null) {
      corpo = `<div class="ival"><span class="num big2">${fmt(r.media, ind.casas)}</span><span class="meta">${esc(ind.unidade)}, média de ${r.anos[0]}${r.anos[1] !== r.anos[0] ? ' a ' + r.anos[1] : ''}</span></div>`;
      if (r.regiao_media != null) corpo += `<p class="cmp">América Latina e Caribe no mesmo período: <b class="num">${fmt(r.regiao_media, ind.casas)}</b></p>`;
    } else {
      const sub = r.variacao < 0;
      const melhorou = ind.melhor === 'menor' ? sub : !sub;
      const pct = r.variacao_pct != null ? ` (${r.variacao_pct > 0 ? '+' : ''}${fmt(r.variacao_pct, 0)}%)` : '';
      corpo = `<div class="ival"><span class="num big2">${fmt(r.inicio.valor, ind.casas)} → ${fmt(r.fim.valor, ind.casas)}</span><span class="meta">${esc(ind.unidade)}, de ${r.inicio.ano} a ${r.fim.ano}</span></div>
        <p class="delta ${r.variacao === 0 ? '' : melhorou ? 'up' : 'down'}">${r.variacao === 0 ? 'Ficou estável' : (sub ? 'Caiu ' : 'Subiu ') + (ind.pct && r.variacao_pct != null ? fmt(Math.abs(r.variacao_pct), 1) + '%' : fmt(Math.abs(r.variacao), ind.casas) + pct)}</p>`;
      if (r.regiao) {
        const rs = r.regiao.variacao < 0;
        corpo += `<p class="cmp">América Latina e Caribe no mesmo período: ${rs ? 'caiu' : 'subiu'} ${fmt(Math.abs(r.regiao.variacao), ind.casas)}${r.regiao.variacao_pct != null ? ` (${r.regiao.variacao_pct > 0 ? '+' : ''}${fmt(r.regiao.variacao_pct, 0)}%)` : ''}</p>`;
      }
    }
    const pos = r.posicao ? `<span class="tag v-${bom}">${r.posicao === 1 ? 'Melhor' : r.posicao === r.total ? 'Pior' : ordinal(r.posicao) + ' melhor'} de ${r.total}</span>` : '';
    return `<div class="ind"><div class="ih"><b>${esc(ind.nome)}</b>${pos}</div>${corpo}${grafico(ind, m)}<p class="note">${esc(ind.explica)} Fonte: ${esc(ind.fonte)}.</p></div>`;
  }

  function detalhe() {
    const id = new URLSearchParams(location.search).get('id');
    const i = D.mandatos.findIndex(m => m.id === id);
    if (i < 0) { location.replace('presidentes.html'); return; }
    const m = D.mandatos[i];
    document.title = `${m.nome} (${periodo(m)}) · Radar Político`;
    $('pnome').textContent = m.nome;
    $('pmeta').textContent = `${m.rotulo} · ${periodo(m)} · ${m.partido}`;
    $('pnota').innerHTML = [m.em_andamento ? 'Mandato em andamento: os números vão até o último ano com dados publicados e ainda vão mudar.' : '', m.nota || '']
      .filter(Boolean).map(t => `<p class="disclaimer">${esc(t)}</p>`).join('');
    $('pctx').innerHTML = (m.contexto || []).map(c => `<li>${esc(c)}</li>`).join('');
    $('pctx').parentElement.hidden = !(m.contexto || []).length;
    const VER = { melhor: ['good', 'Melhor'], pior: ['bad', 'Pior'], igual: ['nd', 'Igual'] };
    $('ptroca').innerHTML = `<div><h3 class="lt">Como recebeu × como entregou</h3>
      <p class="meta">Cada linha compara o último ano antes da posse com o último ano no cargo.</p></div>
      ${placarTxt(m)}
      ${D.areas.map(a => {
        const linhas = D.indicadores.filter(x => x.area === a && m.indicadores[x.id] && m.indicadores[x.id].recebeu);
        if (!linhas.length) return '';
        return `<div class="troca"><div class="label">${esc(a)}</div>${linhas.map(ind => {
          const r = m.indicadores[ind.id], [vc, vt] = VER[r.veredito] || ['nd', 'Sem selo'];
          return `<div class="trow"><span class="tn">${esc(ind.nome.replace(/ médi[oa]s?$/, ''))}<small>${esc(ind.unidade)}</small></span>
            <span class="tv num"><small>${r.recebeu.ano}</small>${fmt(r.recebeu.valor, ind.casas)}</span>
            <span class="ta" aria-hidden="true">→</span>
            <span class="tv num"><small>${r.entregou.ano}</small>${fmt(r.entregou.valor, ind.casas)}</span>
            <span class="tag v-${vc}">${vt}</span></div>`;
        }).join('')}</div>`;
      }).join('')}`;
    $('pareas').innerHTML =`<div class="label">Resultado por área, comparado aos outros mandatos</div>` + D.areas.map(a => areaBar(a, m.areas[a])).join('');
    $('pinds').innerHTML = D.areas.map(a => {
      const inds = D.indicadores.filter(x => x.area === a);
      return `<section class="card"><div class="ah"><h3>${esc(a)}</h3><span class="score s-${faixa(m.areas[a])} num">${m.areas[a] ?? '–'}</span></div>${inds.map(ind => cartaoIndicador(ind, m.indicadores[ind.id], m)).join('')}</section>`;
    }).join('');
    const ant = D.mandatos[i - 1], prox = D.mandatos[i + 1];
    $('pnav').innerHTML = `${ant ? `<a class="chip" href="presidente.html?id=${ant.id}">← ${esc(ant.curto)} · ${periodo(ant)}</a>` : '<span></span>'}${prox ? `<a class="chip" href="presidente.html?id=${prox.id}">${esc(prox.curto)} · ${periodo(prox)} →</a>` : ''}`;
    $('loading').hidden = true; $('perfil').hidden = false;
  }

  async function iniciar() {
    try {
      const r = await fetch('data/presidentes.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(r.status);
      D = await r.json();
    } catch (e) {
      const alvo = $('mlist') || $('loading');
      alvo.innerHTML = '<li class="empty">Os dados ainda estão sendo gerados pelo robô de atualização. Volte em alguns minutos.</li>';
      return;
    }
    const [a, h] = (D.atualizado || '').split(' ');
    const up = a ? `Dados atualizados em ${a.split('-').reverse().join('/')} às ${h}` : '';
    if ($('upd')) $('upd').textContent = up;
    if ($('upd2')) $('upd2').textContent = up + '.';
    if ($('mlist')) iniciarLista(); else detalhe();
  }

  iniciar();
})();
