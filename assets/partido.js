(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const brl = v => (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: (Math.abs(v) < 1000 ? 2 : 0) });
  const curto = v => {
    const a = Math.abs(v || 0);
    if (a >= 1e9) return 'R$ ' + (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' bi';
    if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
    if (a >= 1e3) return 'R$ ' + Math.round(v / 1e3).toLocaleString('pt-BR') + ' mil';
    return brl(v);
  };
  const pc = (a, b) => b ? Math.round(a / b * 100) + '%' : '–';
  const RISCO = { baixo: ['good', 'Atenção baixa', 1], moderado: ['warn', 'Atenção moderada', 2], alto: ['bad', 'Atenção alta', 3] };
  const TX = { good: 'Nada encontrado', warn: 'Atenção', bad: 'Ponto de atenção', nd: 'Sem dados' };

  let IDX = null, P = null, ANO = null;

  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(r.status);
    return r.json();
  }

  function barras(itens, total, cor = 'var(--accent)') {
    const max = Math.max(1, ...itens.map(i => i.valor));
    return itens.map(i => `<div class="vitem"><div class="row"><span>${esc(i.nome)}</span><span class="num">${brl(i.valor)}</span></div><div class="bar"><i style="width:${i.valor / max * 100}%;background:${i.cor || cor}"></i></div>${total ? `<em>${pc(i.valor, total)} do total</em>` : ''}${i.extra || ''}</div>`).join('');
  }

  function registro(r) {
    const sub = [r.data, r.doc ? (r.doc.includes('*') ? 'CPF ' : 'CNPJ ') + r.doc : '', r.numero ? 'doc. nº ' + r.numero : '', r.fonte].filter(Boolean).join(' · ');
    return `<div class="reg"><div class="rh"><b>${esc(r.fornecedor)}</b><span class="num">${brl(r.valor)}</span></div>${r.descricao ? `<small>${esc(r.descricao)}</small>` : ''}${sub ? `<small>${esc(sub)}</small>` : ''}${r.comparacao ? `<span class="cmp">${esc(r.comparacao)}</span>` : ''}${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noopener">Ver comprovante no TSE ↗</a>` : ''}</div>`;
  }

  function alertas(a) {
    if (!a.alertas.length) return `<p class="meta">${a.sem_movimento ? 'O diretório nacional declarou não ter tido movimento financeiro neste ano.' : 'Movimento pequeno demais para aplicar as regras.'}</p>`;
    const ordem = { bad: 0, warn: 1, nd: 2, good: 3 };
    return [...a.alertas].sort((x, y) => ordem[x.status] - ordem[y.status]).map(al => {
      const dados = (al.dados || []).map(g => `<div class="grp"><span class="label">${esc(g.grupo)}</span>${g.registros ? `<div class="regs">${g.registros.map(registro).join('')}</div>` : ''}${g.linhas ? `<ul>${g.linhas.map(l => `<li>${esc(l)}</li>`).join('')}</ul>` : ''}</div>`).join('');
      return `<details class="al ${al.status}"${al.status === 'bad' ? ' open' : ''}><summary><div class="alh"><b>${esc(al.titulo)}</b><span class="tag v-${al.status}">${TX[al.status]}</span></div><p>${esc(al.encontrado)}</p></summary>
        <div class="albody">
          <div><h4>Regra aplicada</h4><p>${esc(al.regra)}</p></div>
          ${dados ? `<div><h4>Dados que sustentam a observação</h4><div class="stack" style="gap:10px">${dados}</div></div>` : ''}
          ${al.verificar ? `<div><h4>O que precisa ser verificado</h4><p>${esc(al.verificar)}</p></div>` : ''}
          <div><h4>Conclusão atual</h4><p class="concl">${esc(al.conclusao)}</p></div>
        </div></details>`;
    }).join('');
  }

  function chartMensal(m, ano) {
    const W = 360, H = 190, L = 44, Rt = 8, T = 10, B = 24, iw = W - L - Rt, ih = H - T - B;
    const top = Math.max(...m, 1);
    const pot = Math.pow(10, Math.floor(Math.log10(top)));
    const passo = top / pot > 5 ? pot * 2 : top / pot > 2 ? pot : pot / 2;
    const max = Math.ceil(top / passo) * passo;
    const y = v => T + ih - (v / max) * ih, bw = iw / 12;
    const rot = v => v >= 1e6 ? (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + 'mi' : v >= 1e3 ? Math.round(v / 1e3) + 'k' : Math.round(v);
    const nomes = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez'];
    let s = '';
    for (let v = 0; v <= max + 1e-6; v += passo) s += `<line x1="${L}" x2="${W - Rt}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + 3.5}" text-anchor="end" font-size="9.5" font-family="var(--mono)" fill="var(--muted)">${rot(v)}</text>`;
    m.forEach((v, i) => {
      const x = L + i * bw + bw * .18;
      s += `<rect x="${x}" y="${y(v)}" width="${bw * .64}" height="${T + ih - y(v)}" rx="2" fill="var(--accent)" opacity=".85"><title>${nomes[i]}/${ano}: ${brl(v)}</title></rect><text x="${x + bw * .32}" y="${H - 8}" text-anchor="middle" font-size="9" font-family="var(--mono)" fill="var(--muted)">${nomes[i]}</text>`;
    });
    return s;
  }

  function chartHist() {
    const anos = Object.keys(P.anos).sort();
    const f = a => (IDX.ipca && IDX.ipca.fatores && IDX.ipca.fatores[a]) || 1;
    const ser = anos.map(a => { const x = P.anos[a]; return [x.receitas.total * f(a), x.transferencias.total * f(a), x.gastos.total * f(a)]; });
    const W = 360, H = 200, L = 44, Rt = 8, T = 10, B = 26, iw = W - L - Rt, ih = H - T - B;
    const top = Math.max(1, ...ser.flat());
    const pot = Math.pow(10, Math.floor(Math.log10(top)));
    const passo = top / pot > 5 ? pot * 2 : top / pot > 2 ? pot : pot / 2;
    const max = Math.ceil(top / passo) * passo;
    const y = v => T + ih - (v / max) * ih, gw = iw / anos.length;
    const rot = v => v >= 1e9 ? (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + 'bi' : v >= 1e6 ? Math.round(v / 1e6) + 'mi' : v >= 1e3 ? Math.round(v / 1e3) + 'k' : Math.round(v);
    const cores = ['var(--accent)', 'var(--warn)', 'var(--muted)'], nomes = ['Recebeu', 'Repassou', 'Gastou'];
    let s = '';
    for (let v = 0; v <= max + 1e-6; v += passo) s += `<line x1="${L}" x2="${W - Rt}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/><text x="${L - 6}" y="${y(v) + 3.5}" text-anchor="end" font-size="9.5" font-family="var(--mono)" fill="var(--muted)">${rot(v)}</text>`;
    anos.forEach((a, i) => {
      const bw = gw * .7 / 3;
      ser[i].forEach((v, j) => {
        const x = L + i * gw + gw * .15 + j * bw;
        s += `<rect x="${x}" y="${y(v)}" width="${bw - 1.5}" height="${T + ih - y(v)}" rx="2" fill="${cores[j]}" opacity="${a === String(ANO) ? 1 : .55}"><title>${a} · ${nomes[j]}: ${brl(v)}</title></rect>`;
      });
      s += `<text x="${L + i * gw + gw / 2}" y="${H - 8}" text-anchor="middle" font-size="10" font-family="var(--mono)" fill="${a === String(ANO) ? 'var(--ink)' : 'var(--muted)'}" font-weight="${a === String(ANO) ? 600 : 400}">${a}${IDX.eleitorais.includes(+a) ? '*' : ''}</text>`;
    });
    return s;
  }

  function render() {
    const a = P.anos[ANO];
    const anos = Object.keys(P.anos).sort();
    document.title = `${P.sg} · Partidos · Radar Político`;
    $('av').textContent = P.sg;
    $('nome').textContent = P.nome;
    $('meta').textContent = `Diretório nacional · ${P.sg}${P.cnpj ? ' · CNPJ ' + P.cnpj : ''}`;
    $('facts').innerHTML = `${a.eleitoral ? '<span class="chip">Ano de eleição</span>' : ''}<a class="chip" href="https://divulgaspca.tse.jus.br/" target="_blank" rel="noopener">Consultar no DivulgaSPCA ↗</a><a class="chip" href="https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-partidarias-${ANO}" target="_blank" rel="noopener">Arquivo do TSE de ${ANO} ↗</a>`;
    $('anos').innerHTML = anos.map(x => `<button type="button" data-a="${x}" aria-pressed="${x === String(ANO)}">${x}</button>`).join('');
    $('voltar').href = `partidos.html?ano=${ANO}`;

    const [rc, rl, rn] = a.sem_movimento ? ['nd', 'Sem movimento', 0] : (RISCO[a.risco.nivel] || RISCO.baixo);
    $('anoR').textContent = ANO;
    $('riskLvl').textContent = rl; $('riskLvl').style.color = `var(--${rc})`;
    document.querySelectorAll('#riskMeter i').forEach((el, j) => el.style.background = j < rn ? `var(--${rc})` : 'var(--line)');
    const nAl = a.alertas.filter(x => x.status === 'warn' || x.status === 'bad').length;
    $('riskTxt').textContent = a.sem_movimento ? 'Sem contas para analisar.' : `${a.risco.pontos} ${a.risco.pontos === 1 ? 'ponto' : 'pontos'} · ${nAl} de ${a.alertas.length} regras com algo a verificar`;

    const R = a.receitas, Gs = a.gastos, Tr = a.transferencias;
    $('nums').innerHTML = [
      ['Recebeu', curto(R.total), 'em dinheiro'],
      ['Dinheiro público', curto(R.publico), `${pc(R.publico, R.total)} do que entrou`],
      ['Repassou', curto(Tr.total), `${curto(Tr.candidatos)} a candidatos`],
      ['Gastou', curto(Gs.total), `${Gs.n.toLocaleString('pt-BR')} lançamentos`],
    ].map(([l, v, s]) => `<div class="tot"><span class="label">${l}</span><span class="v num">${v}</span><small>${s}</small></div>`).join('');
    $('numsNote').textContent = 'Recebido e gasto no mesmo ano não precisam fechar: o partido pode usar saldo de anos anteriores ou guardar parte do dinheiro.';

    $('alerts').innerHTML = alertas(a);

    $('origem').innerHTML = R.por_origem.length ? barras(R.por_origem.map(o => ({ ...o, cor: o.id === 'fp' || o.id === 'fefc' ? 'var(--accent)' : o.id === 'irreg' ? 'var(--bad)' : 'var(--muted)' })), R.total) : '<p class="meta">Nenhuma receita declarada.</p>';
    const doad = R.maiores_doadores.length ? `<div class="label" style="margin-top:6px">Maiores doadores e contribuintes</div><div class="flist">${R.maiores_doadores.slice(0, 5).map(d => `<div class="fitem"><div class="fhead"><span class="fname">${esc(d.nome)}</span><span class="num fval">${brl(d.valor)}</span></div><div class="fsub"><span>${d.tipo === 'PJ' ? 'Pessoa jurídica' : 'Pessoa física'}</span></div></div>`).join('')}</div>` : '';
    $('origem').insertAdjacentHTML('beforeend', doad);
    $('estim').textContent = R.estimavel > 0 ? `Além disso, ${brl(R.estimavel)} em recursos estimáveis (bens e serviços doados, sem dinheiro).` : '';

    $('cats').innerHTML = Gs.categorias.length ? barras(Gs.categorias.slice(0, 9).map(c => ({ ...c, extra: c.itens.length > 1 ? `<details><summary>Detalhar</summary><ul>${c.itens.map(i => `<li><span>${esc(i.nome)}</span><span class="num">${curto(i.valor)}</span></li>`).join('')}</ul></details>` : '' })), Gs.total) : '<p class="meta">Nenhum gasto declarado.</p>';

    $('chart').innerHTML = chartMensal(Gs.mensal, ANO);

    const maxf = Math.max(1, ...a.fornecedores.map(f => f.pct));
    $('forn').innerHTML = a.fornecedores.length ? a.fornecedores.slice(0, 10).map(f => {
      const sub = [f.categoria, f.doc ? (f.doc.includes('*') ? 'CPF ' : 'CNPJ ') + f.doc : ''].filter(Boolean).join(' · ');
      return `<div class="fitem"><div class="fhead"><span class="fname">${esc(f.nome)}</span><span class="num fval">${brl(f.valor)}</span></div><div class="bar"><i style="width:${f.pct / maxf * 100}%;background:${f.flags.length ? 'var(--bad)' : 'var(--accent)'}"></i></div><div class="fsub"><span>${esc(sub)}</span><span class="num">${f.pct.toLocaleString('pt-BR')}% das compras</span></div>${f.flags.length ? `<div class="flags">${f.flags.map(s => `<span>${esc(s)}</span>`).join('')}</div>` : ''}</div>`;
    }).join('') : '<p class="meta">Nenhuma compra de bens ou serviços no ano.</p>';

    $('repasses').innerHTML = Tr.total ? barras(Tr.por_destino, Tr.total, 'var(--warn)') + `<p class="note">Fontes: ${Object.entries(Tr.por_fonte).map(([k, v]) => `${esc(k)} ${curto(v)}`).join(' · ')}</p>` : '<p class="meta">Nenhum repasse no ano.</p>';
    $('maioresL').hidden = !Tr.maiores.length;
    $('maiores').innerHTML = Tr.maiores.slice(0, 6).map(m => `<div class="fitem"><div class="fhead"><span class="fname">${esc(m.nome)}</span><span class="num fval">${brl(m.valor)}</span></div>${m.doc ? `<div class="fsub"><span>CNPJ ${esc(m.doc)}</span></div>` : ''}</div>`).join('');

    const F = a.fundo_partidario;
    const ob = (nome, v, min) => {
      const p = F.recebido ? v / F.recebido : 0, ok = p >= min;
      return `<div class="ob"><div class="nh"><span>${nome}</span><span class="num"><b style="color:var(--${F.recebido ? (ok ? 'good' : 'warn') : 'nd'})">${F.recebido ? Math.round(p * 1000) / 10 + '%' : '–'}</b> <small class="meta">mínimo ${min * 100}%</small></span></div><div class="nbar"><i style="width:${Math.min(100, p / (min * 2) * 100)}%;background:var(--${ok ? 'good' : 'warn'})"></i><b style="left:50%"></b></div><p>${brl(v)} de ${brl(F.recebido)} recebidos do Fundo Partidário</p></div>`;
    };
    $('obrig').innerHTML = F.recebido ? ob('Fundação do partido', F.fundacao, .2) + ob('Participação das mulheres', F.mulheres, .05) : '<p class="meta">O diretório nacional não declarou cotas do Fundo Partidário neste ano.</p>';

    $('devolCard').hidden = !a.devolucoes.total;
    $('devol').innerHTML = barras(a.devolucoes.itens, a.devolucoes.total, 'var(--bad)');

    $('hist').innerHTML = chartHist();
    $('histNote').textContent = `Valores corrigidos pelo IPCA${IDX.ipca && IDX.ipca.ate ? ' até ' + IDX.ipca.ate : ''}. * ano de eleição, quando o Fundo Eleitoral entra nas contas e o volume sobe muito.`;
    if (!IDX.ipca || !IDX.ipca.ate) $('histNote').textContent = 'Valores nominais (o IPCA não estava disponível na última atualização). * ano de eleição.';

    $('fonte').textContent = `Fonte: prestação de contas anual do diretório nacional entregue ao TSE${a.referencia ? `, arquivo gerado em ${a.referencia}` : ''}. ${a.comprovantes ? 'Os links de comprovante levam ao documento anexado pelo partido no sistema do TSE.' : 'O TSE ainda não publicou o arquivo de comprovantes deste ano.'} Estar no arquivo não significa que as contas foram aprovadas.`;
  }

  function sugerir() {
    const t = norm($('q').value.trim()), sg = $('sugg');
    if (!t || !IDX) { sg.hidden = true; return; }
    const m = IDX.partidos.filter(p => norm(p.sg).includes(t) || norm(p.nome).includes(t)).slice(0, 12);
    sg.innerHTML = m.length ? m.map(p => `<button type="button" data-p="${p.slug}"><span>${esc(p.sg)} · ${esc(p.nome)}</span><small>${p.anos[ANO] ? 'recebeu ' + curto(p.anos[ANO].receita) + ' em ' + ANO : ''}</small></button>`).join('') : '<button type="button" disabled><span>Nenhum partido encontrado</span><small>Tente a sigla, como PT ou PL</small></button>';
    sg.hidden = false;
  }

  async function abrir(slug, ano, push) {
    try {
      P = await getJSON(`data/partidos/${slug}.json`);
    } catch (e) {
      $('loading').hidden = false; $('perfil').hidden = true; $('loading').textContent = 'Não foi possível carregar a ficha deste partido.';
      return;
    }
    const anos = Object.keys(P.anos).sort();
    ANO = anos.includes(String(ano)) ? String(ano) : anos[anos.length - 1];
    $('perfil').hidden = false; $('loading').hidden = true;
    render();
    const url = `partido.html?p=${slug}&ano=${ANO}`;
    history[push ? 'pushState' : 'replaceState']({ slug, ano: ANO }, '', url);
    if (push) window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  async function iniciar() {
    try {
      IDX = await getJSON('data/partidos/index.json');
    } catch (e) {
      $('loading').innerHTML = 'Os dados ainda estão sendo gerados pelo robô de atualização.<br>Volte em alguns minutos.';
      return;
    }
    const [d, h] = (IDX.atualizado || '').split(' ');
    $('upd').textContent = d ? `Dados atualizados em ${d.split('-').reverse().join('/')} às ${h}` : '';
    const q = new URLSearchParams(location.search);
    const slug = q.get('p');
    if (!IDX.partidos.some(p => p.slug === slug)) { location.replace('partidos.html'); return; }
    await abrir(slug, q.get('ano'), false);
  }

  $('anos').addEventListener('click', e => {
    const b = e.target.closest('button[data-a]'); if (!b) return;
    ANO = b.dataset.a; render();
    history.replaceState({ slug: P.slug, ano: ANO }, '', `partido.html?p=${P.slug}&ano=${ANO}`);
  });
  $('q').addEventListener('input', sugerir);
  $('q').addEventListener('keydown', e => { if (e.key === 'Enter') { const b = $('sugg').querySelector('button[data-p]'); if (b) b.click(); } });
  $('sugg').addEventListener('click', e => {
    const b = e.target.closest('button[data-p]'); if (!b) return;
    $('q').value = ''; $('sugg').hidden = true; $('q').blur(); abrir(b.dataset.p, ANO, true);
  });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) $('sugg').hidden = true; });
  window.addEventListener('popstate', () => { const q = new URLSearchParams(location.search); if (q.get('p')) abrir(q.get('p'), q.get('ano'), false); });

  iniciar();
})();
