(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const curto = v => {
    const a = Math.abs(v || 0);
    if (a >= 1e9) return 'R$ ' + (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' bi';
    if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
    if (a >= 1e3) return 'R$ ' + Math.round(v / 1e3).toLocaleString('pt-BR') + ' mil';
    return (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  };
  const brl = v => (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
  const titulo = s => (s || '').toLowerCase().replace(/(^|[\s(/-])(\p{L})/gu, (m, a, b) => a + b.toUpperCase()).replace(/\b(De|Da|Do|Das|Dos|E)\b/g, w => w.toLowerCase()).replace('(Uf)', '(estado)');
  const doc = d => d && d.length === 14 ? `CNPJ ${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}` : '';
  const TIPO = { individual: 'Com finalidade definida', pix: 'Pix (transferência especial)' };
  const TX = { bad: 'Prioridade de verificação', warn: 'Atenção', good: 'Sem sinal', nd: 'Sem dados' };
  const GRUPO = { publico: 'Prefeituras, estados e órgãos públicos', banco: 'Caixa e Banco do Brasil (repassam a obras e convênios)', entidade: 'Entidades privadas sem fins lucrativos', empresa: 'Empresas privadas', pf: 'Pessoas físicas', outro: 'Outros ou sem informação' };
  const PIXSIT = { ok: ['good', 'relatório final entregue'], andamento: ['nd', 'dentro do prazo'], atrasado: ['bad', 'prazo vencido sem relatório final'], sem_plano: ['warn', 'sem plano de trabalho'] };
  const destino = e => {
    const l = (e.local || '').trim();
    if (l && !/^(múltiplo|nacional|sem informação)$/i.test(l)) return titulo(l);
    if (e.fav && e.fav[0]) return titulo(e.fav[0].nome);
    if (e.conv && e.conv[0]) return titulo(e.conv[0].convenente);
    return titulo(e.acao) || 'Destino não informado';
  };
  let F = null, FILTRO = 'todas';

  const barra = (rot, v, max, sub, cor) => `<div class="vitem"><div class="row"><span>${rot}</span><span class="num">${curto(v)}</span></div>
    <div class="bar"><i style="width:${Math.max(1, pct(v, max))}%;background:${cor || 'var(--accent)'}"></i></div>${sub ? `<em>${sub}</em>` : ''}</div>`;

  function registro(r) {
    if (r.beneficiario !== undefined) {
      return `<div class="reg"><div class="rh"><b>${esc(titulo(r.beneficiario))}${r.uf ? ' - ' + esc(r.uf) : ''}</b><span class="num">${brl(r.valor)}</span></div>
        <small>Emenda ${esc(r.emenda)} de ${r.ano} · plano de ação ${esc(r.plano)}</small><span class="cmp">${esc(r.descricao)}</span>
        <a href="${r.link}" target="_blank" rel="noopener">Ver a emenda no Portal da Transparência</a></div>`;
    }
    if (r.nome !== undefined) {
      return `<div class="reg"><div class="rh"><b>${esc(titulo(r.nome))}</b><span class="num">${brl(r.valor)}</span></div>
        <small>${esc(r.natureza)} · ${esc(titulo(r.municipio))}${r.uf ? ' - ' + esc(r.uf) : ''} · ${doc(r.doc)}</small></div>`;
    }
    if (r.local !== undefined) {
      return `<div class="reg"><div class="rh"><b>${esc(titulo(r.local))}</b><span class="num">${brl(r.valor)}</span></div>
        <small>Emenda ${esc(r.emenda)} de ${r.ano}</small><a href="${r.link}" target="_blank" rel="noopener">Ver no Portal da Transparência</a></div>`;
    }
    return `<div class="reg"><div class="rh"><b>Emenda ${esc(r.emenda)} de ${r.ano}</b><span class="num">${brl(r.pago)} pagos</span></div>
      <small>Reservado: ${brl(r.emp)}</small><a href="${r.link}" target="_blank" rel="noopener">Ver no Portal da Transparência</a></div>`;
  }

  function checks() {
    const ord = { bad: 0, warn: 1, good: 2, nd: 3 };
    $('checks').innerHTML = [...F.checks].sort((a, b) => ord[a.status] - ord[b.status]).map(c => `<details class="al ${c.status}"${c.status === 'bad' ? ' open' : ''}>
      <summary><div class="alh"><b>${esc(c.titulo)}</b><span class="tag v-${c.status}">${TX[c.status]}</span></div><p>${esc(c.texto)}</p></summary>
      <div class="albody">${c.registros && c.registros.length ? `<div class="regs">${c.registros.map(registro).join('')}</div>` : '<p class="meta">Nenhum registro para listar.</p>'}</div></details>`).join('');
  }

  function emendas() {
    const ems = F.emendas.filter(e => FILTRO === 'todas' || e.tipo === FILTRO || (FILTRO === 'pendente' && e.pend > 0));
    document.querySelectorAll('#filtro button').forEach(b => b.setAttribute('aria-pressed', b.dataset.f === FILTRO));
    $('emendas').innerHTML = ems.slice(0, 200).map(e => {
      const pp = pct(e.pago, e.emp);
      const pix = (e.pix || []).map(p => { const [c, t] = PIXSIT[p.situacao] || ['nd', p.situacao]; return `<li>${esc(titulo(p.beneficiario))}: <span class="v-${c} mini">${t}</span>${p.fim ? ` · execução até ${p.fim.split('-').reverse().join('/')}` : ''}</li>`; }).join('');
      return `<details class="al em"><summary><div class="alh"><b>${esc(destino(e))}</b><span class="num">${curto(e.emp)}</span></div>
        <p>${e.ano} · ${TIPO[e.tipo] || e.tipo} · ${esc(e.funcao)} · ${pp}% pago</p><div class="bar"><i style="width:${pp}%;background:var(--accent)"></i></div></summary>
        <div class="albody">
          <p>${esc(titulo(e.acao))}</p>
          <ul><li>Reservado: <b class="num">${brl(e.emp)}</b></li><li>Pago até agora: <b class="num">${brl(e.pago)}</b></li>${e.pend ? `<li>Ainda não pago: <b class="num">${brl(e.pend)}</b></li>` : ''}${e.canc ? `<li>Cancelado: <b class="num">${brl(e.canc)}</b></li>` : ''}</ul>
          ${e.fav && e.fav.length ? `<div><h4>Quem recebeu</h4><ul>${e.fav.map(f => `<li>${esc(titulo(f.nome))} · ${brl(f.valor)}</li>`).join('')}</ul></div>` : ''}
          ${e.conv && e.conv.length ? `<div><h4>Convênios</h4><ul>${e.conv.map(c => `<li>${esc(c.objeto)} (${esc(titulo(c.convenente))}, convênio ${esc(c.numero)}, ${brl(c.valor)})</li>`).join('')}</ul></div>` : ''}
          ${pix ? `<div><h4>Prestação de contas no Transferegov</h4><ul>${pix}</ul></div>` : ''}
          <a href="${e.link}" target="_blank" rel="noopener">Emenda ${esc(e.cod)} no Portal da Transparência</a>
        </div></details>`;
    }).join('') || '<p class="meta">Nenhuma emenda neste filtro.</p>';
  }

  function render() {
    document.title = `Emendas de ${F.nome} · Radar Político`;
    $('nome').textContent = F.nome;
    $('meta').textContent = `${F.partido}-${F.uf} · deputado(a) federal em exercício`;
    $('av').innerHTML = F.foto ? `<img src="${esc(F.foto)}" alt="" loading="lazy">` : esc(F.nome.slice(0, 2).toUpperCase());
    $('linkDep').href = `deputado.html?id=${F.id}`;
    $('facts').innerHTML = `<a class="chip" href="deputado.html?id=${F.id}">Gastos da cota e presença</a>`;
    const t = F.total;
    $('totais').innerHTML = [
      ['Reservado', curto(t.emp), `${t.n} ${t.n === 1 ? 'emenda individual' : 'emendas individuais'}`],
      ['Pago até agora', curto(t.pago), `${pct(t.pago, t.emp)}% do reservado`],
      ['Ainda não pago', curto(t.pend), 'pode ser pago nos próximos anos'],
      ['Emendas Pix', curto(F.tipos.pix.emp), `${pct(F.tipos.pix.emp, t.emp)}% do reservado`],
    ].map(([l, v, s]) => `<div class="tot"><span class="label">${l}</span><span class="v num">${v}</span><small>${s}</small></div>`).join('');
    const nb = F.checks.filter(c => c.status === 'bad').length, nw = F.checks.filter(c => c.status === 'warn').length;
    const [rc, rl, rn] = F.pontos >= 3 ? ['bad', 'Alto', 3] : F.pontos >= 2 ? ['warn', 'Moderado', 2] : ['good', 'Baixo', 1];
    $('riskLvl').textContent = `${rl} · ${F.pontos} ${F.pontos === 1 ? 'ponto' : 'pontos'}`;
    $('riskLvl').style.color = `var(--${rc})`;
    document.querySelectorAll('#riskMeter i').forEach((el, j) => { el.style.background = j < rn ? `var(--${rc})` : 'var(--line)'; });
    $('riskTxt').textContent = nb || nw ? `${nb ? `${nb} de prioridade` : ''}${nb && nw ? ' e ' : ''}${nw ? `${nw} de atenção` : ''}. Índice de triagem, não prova de irregularidade.` : 'Nenhum sinal nas regras automáticas.';

    const anos = Object.entries(F.anos).filter(([, v]) => v.n);
    const amax = Math.max(...anos.map(([, v]) => v.emp), 1);
    $('anos').innerHTML = anos.map(([a, v]) => `<div class="vitem"><div class="row"><span><b>${a}</b> · ${v.n} ${v.n === 1 ? 'emenda' : 'emendas'}</span><span class="num">${curto(v.emp)}</span></div>
      <div class="bar duo"><i style="width:${pct(v.emp, amax)}%"><b style="width:${pct(v.pago, v.emp)}%"></b></i></div><em>${curto(v.pago)} pagos (${pct(v.pago, v.emp)}%)</em></div>`).join('') || '<p class="meta">Nenhuma emenda individual encontrada.</p>';
    checks();

    const gt = Object.values(F.grupos).reduce((s, v) => s + v, 0);
    $('grupos').innerHTML = Object.entries(F.grupos).filter(([, v]) => v > 0).map(([k, v]) => barra(GRUPO[k] || k, v, gt, `${pct(v, gt)}%`, k === 'entidade' || k === 'empresa' ? 'var(--warn)' : null)).join('') || '<p class="meta">Sem pagamentos registrados.</p>';
    $('favs').innerHTML = F.favorecidos.slice(0, 12).map(registro).join('') || '<div class="reg"><small>Sem pagamentos registrados.</small></div>';
    $('munis').innerHTML = F.municipios.slice(0, 12).map(([ib, n, uf, emp, pago]) => `<div class="reg"><div class="rh"><b><a href="emendas.html?cidade=${ib}#cidade">${esc(titulo(n))} - ${esc(uf)}</a></b><span class="num">${curto(emp)}</span></div><small>${curto(pago)} pagos até agora</small></div>`).join('') || '<div class="reg"><small>Destino por cidade não informado.</small></div>';
    const armax = F.areas.length ? F.areas[0][1] : 1;
    $('areas').innerHTML = F.areas.slice(0, 8).map(([n, v]) => barra(esc(n), v, armax)).join('');

    const temPix = F.emendas.some(e => e.tipo === 'pix'), temPend = F.emendas.some(e => e.pend > 0);
    $('filtro').innerHTML = [['todas', 'Todas'], ['individual', 'Finalidade definida'], temPix && ['pix', 'Pix'], temPend && ['pendente', 'Com valor a pagar']].filter(Boolean)
      .map(([k, l]) => `<button type="button" data-f="${k}">${l}</button>`).join('');
    emendas();
  }

  async function iniciar() {
    const id = new URLSearchParams(location.search).get('id');
    try {
      const r = await fetch(`data/emendas/dep/${encodeURIComponent(id)}.json`, { cache: 'no-cache' });
      if (!r.ok) throw new Error(r.status);
      F = await r.json();
    } catch (e) {
      $('loading').textContent = 'Deputado não encontrado. Volte à página de emendas e escolha um nome na lista.';
      return;
    }
    try {
      const s = await fetch('data/emendas/resumo.json', { cache: 'no-cache' });
      if (s.ok) { const R = await s.json(); const [d, h] = (R.atualizado || '').split(' '); $('upd').textContent = d ? `Dados atualizados em ${d.split('-').reverse().join('/')} às ${h}` : ''; }
    } catch (e) { /* só a data de atualização fica de fora */ }
    $('loading').hidden = true;
    $('perfil').hidden = false;
    render();
  }

  $('filtro').addEventListener('click', e => { const b = e.target.closest('button[data-f]'); if (b) { FILTRO = b.dataset.f; emendas(); } });
  iniciar();
})();
