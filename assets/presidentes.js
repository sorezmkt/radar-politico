(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmt = (v, c = 1) => v == null ? '–' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: c, maximumFractionDigits: c });
  const faixa = n => n == null ? 'nd' : n >= 67 ? 'good' : n >= 34 ? 'warn' : 'bad';
  const anoDe = s => s ? s.slice(0, 4) : 'hoje';
  const periodo = m => `${anoDe(m.inicio)}–${m.termino ? anoDe(m.termino) : 'hoje'}`;
  const ordinal = n => `${n}º`;

  let D = null;
  const ehResultado = a => !D.blocos || (D.blocos.find(b => b.nome === a) || {}).tipo === 'resultado';
  const secao = a => ((D.blocos || []).find(b => b.nome === a) || {}).secao || 'principal';
  const SECOES = { principal: 'Indicadores principais', custo: 'Custo de vida e acesso ao consumo', fator: 'Fatores que explicam os resultados' };
  const quando = x => x ? (x.rotulo || x.ano) : '';

  function areaBar(nome, nota) {
    return `<div class="abar"><span class="an">${esc(nome)}</span><span class="bar"><i style="width:${nota ?? 0}%;background:var(--${faixa(nota)})"></i></span><span class="av num">${nota ?? '–'}</span></div>`;
  }

  const faixaNivel = n => n == null ? ['nd', 'Sem dados suficientes'] : n >= 70 ? ['good', 'Próximo do adequado'] : n >= 40 ? ['warn', 'Intermediário'] : ['bad', 'Distante do adequado'];
  function nivelTxt(m, compacto) {
    const n = m.nivel_geral, n0 = m.nivel_geral_inicio, [fc, fl] = faixaNivel(n);
    if (n == null) return `<div class="nivel"><span class="nl">Nível de vida</span><span class="meta">Dados insuficientes neste período</span></div>`;
    return `<div class="nivel"><div class="nh"><span class="nl">Nível de vida ${m.em_andamento ? 'agora' : 'ao sair'}</span><span class="nv num" style="color:var(--${fc})">${n}<small>/100</small></span></div>
      <div class="nbar"><i style="width:${n}%;background:var(--${fc})"></i>${n0 != null ? `<b style="left:${n0}%" title="Ao assumir: ${n0}"></b>` : ''}</div>
      ${compacto ? '' : `<p class="meta" style="margin:0">${fl}${n0 != null ? ` · ao assumir: ${n0}/100` : ''}. Mede o quanto as condições se aproximam de um padrão adequado, não o quanto mudaram.</p>`}</div>`;
  }
  const tagsTxt = m => (m.tags || []).map(id => (D.tags || []).find(t => t.id === id)).filter(Boolean)
    .map(t => `<span class="htag" title="${esc(t.impactos)}">⚠ ${esc(t.nome)}</span>`).join('');

  function placarTxt(m) {
    const p = m.placar; if (!p || !p.total) return '';
    const w = v => `${v / p.total * 100}%`;
    return `<div class="placar">
      <div class="pbar" aria-hidden="true"><i style="width:${w(p.melhor)};background:var(--good)"></i><i style="width:${w(p.igual)};background:var(--nd)"></i><i style="width:${w(p.pior)};background:var(--bad)"></i></div>
      <p><b>Evolução no mandato:</b> entregou o país <b style="color:var(--good)">melhor em ${p.melhor}</b>${p.igual ? `, igual em ${p.igual}` : ''} e <b style="color:var(--bad)">pior em ${p.pior}</b> de ${p.total} indicadores</p>
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
      ${nivelTxt(m, true)}
      ${placarTxt(m)}
      ${(m.tags || []).length ? `<div class="htags">${tagsTxt(m)}</div>` : ''}
      ${area
        ? `<div class="mbig">${areaBar(area, m.areas[area])}</div>`
        : `<div class="label" style="margin-top:2px">Evolução por área</div><div class="mareas">${D.areas.filter(ehResultado).map(a => areaBar(a, m.areas[a])).join('')}</div>`}
    </a></li>`).join('');
  }

  // cor contínua da nota: vermelho (0) → amarelo (50) → verde (100)
  const corNota = n => n == null ? 'var(--line)' : n >= 67 ? 'var(--good)' : n >= 34 ? 'var(--warn)' : 'var(--bad)';
  const opNota = n => n == null ? 1 : n >= 67 ? .45 + (n - 67) / 33 * .55 : n >= 34 ? .75 : .45 + (33 - n) / 33 * .55;

  function mapa() {
    const ms = D.mandatos, inds = D.indicadores.filter(i => i.melhor !== 'neutro');
    let h = `<thead><tr><th></th>${ms.map(m => `<th><a href="presidente.html?id=${m.id}">${esc(m.sigla || m.curto)}${m.em_andamento ? '*' : ''}</a></th>`).join('')}</tr></thead><tbody>`;
    let grupo = null;
    D.areas.forEach(a => {
      const linhas = inds.filter(i => i.area === a); if (!linhas.length) return;
      const g = SECOES[secao(a)];
      if (g !== grupo) { grupo = g; h += `<tr class="hmgrupo"><th colspan="${ms.length + 1}">${g}</th></tr>`; }
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
      if (!neutro && ra && rb && ra.nota != null && rb.nota != null && ra.nota !== rb.nota) { w = ra.nota > rb.nota ? 'a' : 'b'; if (ehResultado(ind.area)) w === 'a' ? va++ : vb++; }
      const cel = (r, lado) => {
        if (!r) return `<div class="dc nd">sem dados</div>`;
        const ini = r.recebeu ? fmt(r.recebeu.valor, ind.casas) : '–', fim = r.entregou ? fmt(r.entregou.valor, ind.casas) : '–';
        const media = r.media != null ? `<small>média ${fmt(r.media, ind.casas)}</small>` : '';
        const vc = { melhor: 'good', pior: 'bad', igual: 'nd' }[r.veredito] || 'nd';
        return `<div class="dc ${w === lado ? 'win' : ''}"><span class="num">${ini} → ${fim}</span>${media}${r.veredito ? `<span class="tag v-${vc}">${r.veredito === 'melhor' ? 'Melhorou' : r.veredito === 'pior' ? 'Piorou' : 'Igual'}</span>` : ''}</div>`;
      };
      return `<div class="drow"><div class="dn">${esc(ind.nome)}<small>${esc(ind.unidade)}${neutro ? ' · sem selo' : ''}</small></div>${cel(ra, 'a')}${cel(rb, 'b')}</div>`;
    };
    let corpo = '', fatores = false;
    D.areas.forEach(a => {
      const rows = D.indicadores.filter(i => i.area === a).map(linha).join('');
      if (!rows) return;
      if (!ehResultado(a) && !fatores) { fatores = true; corpo += `<div class="dgrupo">Fatores que explicam os resultados <small>não contam no placar</small></div>`; }
      else if (secao(a) === 'custo' && !corpo.includes('dgrupo-custo')) corpo += `<div class="dgrupo dgrupo-custo">Custo de vida e acesso ao consumo</div>`;
      corpo += `<div class="label dlab">${esc(a)}</div>${rows}`;
    });
    const nome = m => `${esc(m.sigla)} <small>${periodo(m)}</small>`;
    const tot = va + vb;
    $('dres').innerHTML = `<div class="dplacar">
        <div class="dp ${va > vb ? 'lead' : ''}"><span class="dpn">${nome(A)}</span><span class="dpv num">${va}</span></div>
        <div class="dp ${vb > va ? 'lead' : ''}"><span class="dpn">${nome(B)}</span><span class="dpv num">${vb}</span></div>
      </div>
      <div class="dnivel"><span>Nível de vida ao fim: <b class="num">${A.nivel_geral ?? '–'}</b></span><span>Nível de vida ao fim: <b class="num">${B.nivel_geral ?? '–'}</b></span></div>
      <div class="dbar" aria-hidden="true"><i style="width:${tot ? va / tot * 100 : 50}%"></i><i style="width:${tot ? vb / tot * 100 : 50}%"></i></div>
      <p class="note">Indicadores de vida da população e de custo de vida em que cada governo teve o melhor resultado na comparação entre todos os mandatos. ${A.em_andamento || B.em_andamento ? 'Mandato em andamento ainda tem dados parciais. ' : ''}Cada linha mostra como o governo recebeu → como entregou.</p>
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
      corpo = `<div class="ival"><span class="num big2">${fmt(r.media, ind.casas)}</span><span class="meta">${esc(ind.unidade)}, ${r.media_rotulo ? esc(r.media_rotulo) : 'média de ' + r.anos[0] + (r.anos[1] !== r.anos[0] ? ' a ' + r.anos[1] : '')}</span></div>`;
      if (r.entregou && r.entregou.rotulo) corpo += `<p class="cmp">Dado mais recente: <b class="num">${fmt(r.entregou.valor, ind.casas)}</b> (${esc(r.entregou.rotulo)})</p>`;
      if (r.regiao_media != null) corpo += `<p class="cmp">América Latina e Caribe no mesmo período: <b class="num">${fmt(r.regiao_media, ind.casas)}</b></p>`;
    } else {
      const sub = r.variacao < 0;
      const melhorou = ind.melhor === 'menor' ? sub : !sub;
      const pct = r.variacao_pct != null ? ` (${r.variacao_pct > 0 ? '+' : ''}${fmt(r.variacao_pct, 0)}%)` : '';
      corpo = `<div class="ival"><span class="num big2">${fmt(r.inicio.valor, ind.casas)} → ${fmt(r.fim.valor, ind.casas)}</span><span class="meta">${esc(ind.unidade)}, de ${r.inicio.ano} a ${r.entregou && r.entregou.rotulo ? esc(r.entregou.rotulo) : r.fim.ano}</span></div>
        <p class="delta ${r.variacao === 0 ? '' : melhorou ? 'up' : 'down'}">${r.variacao === 0 ? 'Ficou estável' : (sub ? 'Caiu ' : 'Subiu ') + (ind.pct && r.variacao_pct != null ? fmt(Math.abs(r.variacao_pct), 1) + '%' : fmt(Math.abs(r.variacao), ind.casas) + pct)}</p>`;
      if (r.regiao) {
        const rs = r.regiao.variacao < 0;
        corpo += `<p class="cmp">América Latina e Caribe no mesmo período: ${rs ? 'caiu' : 'subiu'} ${fmt(Math.abs(r.regiao.variacao), ind.casas)}${r.regiao.variacao_pct != null ? ` (${r.regiao.variacao_pct > 0 ? '+' : ''}${fmt(r.regiao.variacao_pct, 0)}%)` : ''}</p>`;
      }
    }
    if (r.nivel_fim != null || r.nivel_inicio != null) {
      const ref = (D.referencias || {})[ind.id] || {};
      const [nc] = faixaNivel(r.nivel_fim);
      corpo += `<div class="inivel"><div class="nh"><span>Nível ${m.em_andamento ? 'agora' : 'ao sair'}</span><span class="num" style="color:var(--${nc})"><b>${r.nivel_fim ?? '–'}</b>/100${r.nivel_inicio != null ? ` <small>(ao assumir: ${r.nivel_inicio})</small>` : ''}</span></div>
        <div class="nbar"><i style="width:${r.nivel_fim ?? 0}%;background:var(--${nc})"></i>${r.nivel_inicio != null ? `<b style="left:${r.nivel_inicio}%"></b>` : ''}</div>
        ${r.smn_entregou != null ? `<p class="note" style="margin:0">O salário mínimo equivale a <b>${fmt(r.smn_entregou, 0)}%</b> do salário mínimo necessário do DIEESE${r.smn_recebeu != null ? ` (era ${fmt(r.smn_recebeu, 0)}% ao assumir)` : ''}.</p>` : ''}
        ${ref.texto ? `<p class="note" style="margin:0">Referência: ${esc(ref.texto)}</p>` : ''}</div>`;
    }
    const imp = impacto(ind, r);
    if (imp) corpo += `<p class="impacto">${imp}</p>`;
    const pos = r.posicao ? `<span class="tag v-${bom}">${r.posicao === 1 ? 'Melhor' : r.posicao === r.total ? 'Pior' : ordinal(r.posicao) + ' melhor'} de ${r.total}</span>` : '';
    return `<div class="ind"><div class="ih"><b>${esc(ind.nome)}</b>${pos}</div>${corpo}${grafico(ind, m)}<p class="note">${esc(ind.explica)}</p><p class="fonteconf"><span>Fonte: ${esc(ind.fonte)}</span>${ind.confianca ? `<span class="conf c-${ind.confianca === 'alta' ? 'good' : ind.confianca === 'média' ? 'warn' : 'bad'}">Confiança ${esc(ind.confianca)}</span>` : ''}${ind.limite ? `<span>Limite: ${esc(ind.limite)}</span>` : ''}</p></div>`;
  }

  // frase de impacto na vida da população, calculada só a partir dos dados
  function impacto(ind, r) {
    if (!r.recebeu || !r.entregou) return '';
    const ini = r.recebeu.valor, fim = r.entregou.valor, desde = r.recebeu.ano, ate = r.entregou.rotulo || r.entregou.ano;
    const pct = ini ? (fim / ini - 1) * 100 : null;
    if (ind.id.startsWith('acess_') && pct != null) {
      if (Math.abs(pct) < 1) return `Para quem ganha o salário mínimo, ${esc(ind.nome.toLowerCase())} ficou praticamente igual de acessível entre ${desde} e ${esc(ate)}.`;
      return `Com um salário mínimo, dava para comprar <b>${fmt(Math.abs(pct), 0)}% ${pct > 0 ? 'mais' : 'menos'}</b> em ${esc(ind.nome.toLowerCase())} em ${esc(ate)} do que em ${desde}. Ficou ${pct > 0 ? 'mais acessível' : 'mais caro'} para quem ganha o mínimo.`;
    }
    if (ind.id === 'cesta_horas') return `Quem ganha o mínimo precisava trabalhar <b>${fmt(ini, 0)} horas</b> para comprar a cesta básica em ${desde} e <b>${fmt(fim, 0)} horas</b> em ${esc(ate)}: ${fim < ini ? fmt(ini - fim, 0) + ' horas a menos' : fmt(fim - ini, 0) + ' horas a mais'} de trabalho.`;
    if (ind.id === 'litros_gasolina') return `Um salário mínimo comprava <b>${fmt(ini, 0)} litros</b> de gasolina em ${desde} e <b>${fmt(fim, 0)} litros</b> em ${esc(ate)}.`;
    if (ind.id === 'salario_minimo') return `O salário mínimo ${fim >= ini ? 'ganhou' : 'perdeu'} <b>R$ ${fmt(Math.abs(fim - ini), 0)}</b> de poder de compra por mês, em valores de hoje.`;
    return '';
  }

  // custo de vida: o que ficou mais fácil ou mais difícil de pagar com um salário mínimo
  function custoVisual(m) {
    const el = $('pcusto'); if (!el) return;
    const itens = D.indicadores.filter(i => secao(i.area) === 'custo').map(i => {
      const r = m.indicadores[i.id];
      if (!r || !r.recebeu || !r.entregou || !r.recebeu.valor) return null;
      let pct = (r.entregou.valor / r.recebeu.valor - 1) * 100;
      if (i.melhor === 'menor') pct = -pct; // horas de trabalho: cair é bom
      return { nome: i.nome.replace(/^Horas de trabalho para comprar a cesta básica$/, 'Cesta básica').replace(/^Litros de gasolina com um salário mínimo$/, 'Gasolina'), pct };
    }).filter(Boolean).sort((a, b) => b.pct - a.pct);
    if (!itens.length) { el.hidden = true; return; }
    const max = Math.max(10, ...itens.map(x => Math.abs(x.pct)));
    el.innerHTML = `<div><h3 class="lt">Ficou mais fácil ou mais difícil de pagar?</h3>
      <p class="meta">Quanto cada despesa ficou mais acessível (verde) ou mais cara (vermelho) para quem ganha o salário mínimo, do início ao fim do mandato. Já considera a alta do salário e a alta do preço.</p></div>
      <div class="div">${itens.map(x => `<div class="drow2"><span class="dn2">${esc(x.nome)}</span>
        <span class="dbarw"><span class="dmid"></span><i style="${x.pct >= 0 ? `left:50%;width:${x.pct / max * 50}%;background:var(--good)` : `right:50%;width:${-x.pct / max * 50}%;background:var(--bad)`}"></i></span>
        <span class="dv num" style="color:var(--${x.pct >= 0 ? 'good' : 'bad'})">${x.pct >= 0 ? '+' : '−'}${fmt(Math.abs(x.pct), 0)}%</span></div>`).join('')}</div>
      <div class="legend"><span><i style="background:var(--bad)"></i>Mais caro</span><span><i style="background:var(--good)"></i>Mais acessível</span></div>`;
    el.hidden = false;
  }

  function detalhe() {
    const id = new URLSearchParams(location.search).get('id');
    const i = D.mandatos.findIndex(m => m.id === id);
    if (i < 0) { location.replace('presidentes.html'); return; }
    const m = D.mandatos[i];
    document.title = `${m.nome} (${periodo(m)}) · Radar Político`;
    $('pnome').textContent = m.nome;
    $('pmeta').textContent = `${m.rotulo} · ${periodo(m)} · ${m.partido}`;
    $('pnota').innerHTML = [m.em_andamento ? 'Mandato em andamento: usamos o dado mais recente de cada indicador (do último mês ou trimestre publicado, quando existe). Os números ainda vão mudar.' : '', m.nota || '']
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
            <span class="tv num"><small>${esc(r.entregou.rotulo ? r.entregou.rotulo.replace(/^12 meses até /, '') : r.entregou.ano)}</small>${fmt(r.entregou.valor, ind.casas)}</span>
            <span class="tag v-${vc}">${vt}</span></div>`;
        }).join('')}</div>`;
      }).join('')}`;
    $('pareas').innerHTML =`<div class="label">Evolução por área, comparada aos outros mandatos</div>` + D.areas.map(a => areaBar(a, m.areas[a])).join('');
    const bloco = a => {
      const inds = D.indicadores.filter(x => x.area === a);
      const desc = ((D.blocos || []).find(b => b.nome === a) || {}).descricao;
      return `<section class="card"><div class="ah"><h3>${esc(a)}</h3><span class="score s-${faixa(m.areas[a])} num">${m.areas[a] ?? '–'}</span></div>${desc ? `<p class="meta" style="margin:0">${esc(desc)}</p>` : ''}${inds.map(ind => cartaoIndicador(ind, m.indicadores[ind.id], m)).join('')}</section>`;
    };
    $('pinds').innerHTML = ['principal', 'custo', 'fator'].map(sec => {
      const as = D.areas.filter(a => secao(a) === sec); if (!as.length) return '';
      const sub = sec === 'fator' ? '<p class="meta" style="margin:0">Ajudam a entender o que aconteceu e o que pode vir depois. Não entram no placar.</p>' : '';
      return `<h3 class="grupo">${SECOES[sec]}</h3>${sub}` + as.map(bloco).join('');
    }).join('');
    custoVisual(m);
    $('presumo').innerHTML = `<div><h3 class="lt">Dois resultados, medidos de forma independente</h3>
      <p class="meta">Uma situação pode melhorar muito e continuar ruim, ou piorar um pouco e continuar boa. Por isso medimos as duas coisas separadas.</p></div>
      ${nivelTxt(m)}
      <div class="nareas">${D.areas.filter(a => m.nivel && a in m.nivel).map(a => { const v = m.nivel[a], [c] = faixaNivel(v); return `<div class="abar"><span class="an">${esc(a)}</span><span class="bar"><i style="width:${v ?? 0}%;background:var(--${c})"></i></span><span class="av num">${v ?? '–'}</span></div>`; }).join('')}</div>
      ${placarTxt(m)}`;
    const tg = (m.tags || []).map(id => (D.tags || []).find(t => t.id === id)).filter(Boolean);
    $('ptags').hidden = !tg.length;
    $('ptags').innerHTML = `<div><h3 class="lt">Atenção: acontecimentos extraordinários no período</h3>
      <p class="meta">Contexto para ler os resultados. Não dá nem tira pontos do presidente.</p></div>
      ${tg.map(t => `<div class="tagcard"><b>⚠ ${esc(t.nome)}</b><span class="meta">${esc(t.inicio.split('-').reverse().join('/'))} a ${esc(t.fim.split('-').reverse().join('/'))}</span><p>${esc(t.impactos)}</p><p class="note">Indicadores afetados: ${esc(t.afeta.map(id => (D.indicadores.find(i => i.id === id) || {}).nome).filter(Boolean).join(', '))}. Fonte: ${esc(t.fonte)}.</p></div>`).join('')}`;
    heranca(m);
    projecao(m);
    const ant = D.mandatos[i - 1], prox = D.mandatos[i + 1];
    $('pnav').innerHTML = `${ant ? `<a class="chip" href="presidente.html?id=${ant.id}">← ${esc(ant.curto)} · ${periodo(ant)}</a>` : '<span></span>'}${prox ? `<a class="chip" href="presidente.html?id=${prox.id}">${esc(prox.curto)} · ${periodo(prox)} →</a>` : ''}`;
    $('loading').hidden = true; $('perfil').hidden = false;
  }

  function heranca(m) {
    const h = m.heranca || {}, ids = D.indicadores.filter(x => h[x.id]);
    if (!ids.length) { $('pheranca').hidden = true; return; }
    const piores = ids.filter(x => h[x.id].situacao === 'pior').length;
    $('pheranca').innerHTML = `<div><h3 class="lt">Herança recebida</h3>
      <p class="meta">Como o país estava quando ${esc(m.curto)} assumiu, comparado à média de 1995 até hoje, e se vinha melhorando ou piorando nos dois anos anteriores. Ajuda a separar problemas herdados dos resultados do próprio governo.</p></div>
      <p class="hsum">Recebeu <b style="color:var(--bad)">${piores}</b> de ${ids.length} indicadores piores que a média histórica.</p>
      ${ids.map(ind => {
        const x = h[ind.id];
        return `<div class="hrow"><span class="tn">${esc(ind.nome)}<small>${esc(ind.unidade)}</small></span>
          <span class="tv num"><small>${x.ano}</small>${fmt(x.valor, ind.casas)}</span>
          <span class="hsit"><span class="tag v-${x.situacao === 'pior' ? 'bad' : 'good'}">${x.situacao === 'pior' ? 'Pior que a média' : 'Melhor que a média'}</span>${x.tendencia ? `<small class="${x.tendencia === 'piorando' ? 'down' : 'up'}">${x.tendencia === 'piorando' ? '↘ vinha piorando' : '↗ vinha melhorando'}</small>` : ''}</span></div>`;
      }).join('')}`;
  }

  function projecao(m) {
    const P = D.projecao, el = $('pproj');
    const C = P && P.cenarios ? P.cenarios : [];
    if (!m.em_andamento || !C.length) { el.hidden = true; return; }
    const NOME = { base: 'Base', pessimista: 'Pessimista', otimista: 'Otimista' };
    el.innerHTML = `<div><span class="tag v-warn">Projeção · estimativa, não é fato</span><h3 class="lt" style="margin-top:8px">Para onde o país pode ir</h3>
      <p class="meta">Só para o governo atual. Trajetórias possíveis a partir dos dados mais recentes, separadas dos resultados medidos. Nenhuma projeção entra no nível de vida ou no placar.</p></div>
      ${C.map(c => {
        const anos = [...new Set(Object.values(c.cenarios).flat().map(p => p[0]))].sort();
        return `<div class="pc"><div class="ih"><b>${esc(c.nome)}</b><span class="tag v-${c.incerteza === 'alta' ? 'bad' : 'warn'}">Incerteza ${esc(c.incerteza)}</span></div>
          <span class="meta">${esc(c.unidade)} · horizonte ${esc(c.horizonte)}${c.atual != null ? ` · hoje: ${fmt(c.atual, c.atual > 100 ? 0 : 1)}${c.atual_ano ? ' (' + c.atual_ano + ')' : ''}` : ''}</span>
          <div class="ptab"><table><thead><tr><th></th>${anos.map(a => `<th>${a}</th>`).join('')}</tr></thead><tbody>
          ${Object.entries(c.cenarios).map(([k, pts]) => `<tr><th>${esc(NOME[k] || k)}</th>${anos.map(a => { const p = pts.find(x => x[0] === a); return `<td class="num">${p ? fmt(p[1], p[1] > 100 ? 0 : 1) : '–'}</td>`; }).join('')}</tr>`).join('')}
          </tbody></table></div>
          <p class="note"><b>Premissas:</b> ${esc(c.premissas)}</p><p class="note"><b>Riscos:</b> ${esc(c.riscos)}</p><p class="note">Fonte: ${esc(c.fonte)}.</p></div>`;
      }).join('')}`;
    el.hidden = false;
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
