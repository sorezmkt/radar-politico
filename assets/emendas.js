(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const curto = v => {
    const a = Math.abs(v || 0);
    if (a >= 1e9) return 'R$ ' + (v / 1e9).toLocaleString('pt-BR', { maximumFractionDigits: 2 }) + ' bi';
    if (a >= 1e6) return 'R$ ' + (v / 1e6).toLocaleString('pt-BR', { maximumFractionDigits: 1 }) + ' mi';
    if (a >= 1e3) return 'R$ ' + Math.round(v / 1e3).toLocaleString('pt-BR') + ' mil';
    return (v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
  };
  const pct = (a, b) => b ? Math.round(a / b * 100) : 0;
  const titulo = s => (s || '').toLowerCase().replace(/(^|[\s(/-])(\p{L})/gu, (m, a, b) => a + b.toUpperCase()).replace(/\b(De|Da|Do|Das|Dos|E)\b/g, w => w.toLowerCase());
  const TIPOS = {
    individual: ['Individual com finalidade definida', 'O deputado ou senador indica o destino e a área; o dinheiro passa por convênio ou programa federal.'],
    pix: ['Individual Pix (transferência especial)', 'O dinheiro cai direto na conta da prefeitura ou do estado, sem convênio.'],
    bancada: ['De bancada', 'Indicada em conjunto pelos parlamentares de um estado.'],
    comissao: ['De comissão', 'Indicada por uma comissão da Câmara, do Senado ou do Congresso.'],
    relator: ['De relator (RP9)', 'Distribuída pelo relator do orçamento de 2020 a 2022; declarada inconstitucional pelo STF.'],
  };
  const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } };
  const lerg = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
  const linkDep = id => `emendas-deputado.html?id=${id}`;

  let R = null, D = null, M = null, ANO = null, ORD = lerg('re-ordem') || 'emp', TODOS = false;

  const barra = (rot, v, max, sub, cor) => `<div class="vitem"><div class="row"><span>${rot}</span><span class="num">${curto(v)}</span></div>
    <div class="bar"><i style="width:${Math.max(1, pct(v, max))}%;background:${cor || 'var(--accent)'}"></i></div>${sub ? `<em>${sub}</em>` : ''}</div>`;

  function render() {
    const a = R.por_ano[ANO], parc = +ANO === R.parcial;
    $('anoT').textContent = ANO;
    document.querySelectorAll('#anos button').forEach(b => b.setAttribute('aria-pressed', b.dataset.a === String(ANO)));
    $('anoSub').classList.toggle('parcial', parc);
    $('anoSub').textContent = `${parc ? 'Ano em curso: os pagamentos ainda estão acontecendo · ' : ''}${a.total.n.toLocaleString('pt-BR')} emendas com dinheiro reservado no orçamento de ${ANO}`;
    const t = a.total;
    $('totais').innerHTML = [
      ['Reservado', curto(t.emp), 'empenhado no orçamento'],
      ['Pago até agora', curto(t.pago), `${pct(t.pago, t.emp)}% do reservado`],
      ['Ainda não pago', curto(t.pend), 'pode ser pago nos próximos anos'],
      ['Cancelado', curto(t.canc), 'reserva desfeita depois'],
    ].map(([l, v, s]) => `<div class="tot"><span class="label">${l}</span><span class="v num">${v}</span><small>${s}</small></div>`).join('');

    const tmax = Math.max(...Object.values(a.tipos).map(x => x.emp), 1);
    $('tipos').innerHTML = Object.entries(TIPOS).filter(([k]) => a.tipos[k] && a.tipos[k].n).map(([k, [n, d]]) => {
      const x = a.tipos[k];
      return `<div class="vitem"><div class="row"><span><b>${n}</b></span><span class="num">${curto(x.emp)}</span></div>
        <div class="bar duo"><i style="width:${pct(x.emp, tmax)}%"><b style="width:${pct(x.pago, x.emp)}%"></b></i></div>
        <em>${x.n.toLocaleString('pt-BR')} emendas · ${curto(x.pago)} pagos (${pct(x.pago, x.emp)}%) · ${d}</em></div>`;
    }).join('') + '<div class="legend"><span><i style="background:var(--accent)"></i>Pago</span><span><i style="background:var(--accent-soft)"></i>Reservado</span></div>';

    const gtot = Object.values(a.grupos).reduce((s, v) => s + v, 0);
    $('grupos').innerHTML = Object.entries(a.grupos).filter(([, v]) => v > 0).map(([k, v]) =>
      barra(R.grupos_nome[k] || k, v, gtot, `${pct(v, gtot)}% do que foi pago`, k === 'entidade' || k === 'empresa' ? 'var(--warn)' : null)).join('') ||
      '<p class="meta">Sem pagamentos registrados.</p>';
    $('entidades').innerHTML = a.entidades.map(e => `<div class="reg"><div class="rh"><b>${esc(titulo(e.nome))}</b><span class="num">${curto(e.valor)}</span></div>
      <small>${e.grupo === 'empresa' ? 'Empresa' : 'Entidade sem fins lucrativos'} · ${esc(titulo(e.municipio))}${e.uf ? ' - ' + esc(e.uf) : ''} · CNPJ ${esc(e.doc)}</small></div>`).join('') ||
      '<div class="reg"><small>Nenhuma entidade ou empresa recebeu diretamente neste ano.</small></div>';
    const amax = a.areas.length ? a.areas[0][1] : 1;
    $('areas').innerHTML = a.areas.slice(0, 8).map(([n, v]) => barra(esc(n), v, amax)).join('');
    const umax = a.ufs.length ? a.ufs[0][1] : 1;
    $('ufs').innerHTML = a.ufs.slice(0, 10).map(([n, v]) => barra(esc(n), v, umax)).join('');
    $('munis').innerHTML = a.municipios.map(([ib, n, uf, emp, pago]) => `<div class="reg"><div class="rh"><b><a href="?cidade=${ib}#cidade">${esc(titulo(n))} - ${esc(uf)}</a></b><span class="num">${curto(emp)}</span></div><small>${curto(pago)} pagos até agora</small></div>`).join('');
    $('autores').innerHTML = a.autores.map(x => `<div class="reg"><div class="rh"><b>${x.id ? `<a href="${linkDep(x.id)}">${esc(x.nome)}</a>` : esc(x.nome)}</b><span class="num">${curto(x.emp)}</span></div>
      <small>${x.id ? `Deputado · ${esc(x.partido)}-${esc(x.uf)}` : 'Senador ou ex-parlamentar'}</small></div>`).join('');
    renderLista();
    if (!parc) guardar('re-ano', ANO);
  }

  function renderLista() {
    document.querySelectorAll('#ordem button').forEach(b => b.setAttribute('aria-pressed', b.dataset.o === ORD));
    const ord = [...D.deputados].sort((x, y) => ORD === 'nome' ? x.nome.localeCompare(y.nome, 'pt-BR') : ORD === 'pontos' ? (y.pontos - x.pontos) || (y.emp - x.emp) : y.emp - x.emp);
    const vis = TODOS ? ord : ord.slice(0, 50);
    $('lista').innerHTML = vis.map(d => {
      const [c, l] = d.bad ? ['bad', `${d.bad + d.warn} ${d.bad + d.warn === 1 ? 'sinal' : 'sinais'}`] : d.warn ? ['warn', `${d.warn} ${d.warn === 1 ? 'sinal' : 'sinais'}`] : d.n ? ['good', 'Nenhum'] : ['nd', 'Sem emendas'];
      return `<li class="${d.n ? '' : 'off'}"><a href="${linkDep(d.id)}">
        <span class="pnm"><span class="sigla">${esc(d.partido)}</span><span><b>${esc(d.nome)}</b><small>${esc(d.uf)} · ${d.n} ${d.n === 1 ? 'emenda' : 'emendas'}</small></span></span>
        <span class="pval"><span class="num">${curto(d.emp)}</span><span class="pubbar" title="${pct(d.pago, d.emp)}% pago"><i style="width:${pct(d.pago, d.emp)}%"></i></span><small>${pct(d.pago, d.emp)}% pago</small></span>
        <span class="rk v-${c}">${l}</span></a></li>`;
    }).join('');
    $('mais').hidden = TODOS || ord.length <= 50;
  }

  async function cidades() {
    if (M) return M;
    const r = await fetch('data/emendas/municipios.json', { cache: 'no-cache' });
    M = r.ok ? await r.json() : [];
    return M;
  }

  async function mostrarCidade(ib) {
    const lista = await cidades();
    const c = lista.find(x => x[0] === ib);
    const el = $('cidade');
    if (!c) { el.hidden = true; return; }
    const [, nome, uf, emp, pago, n, aut] = c;
    const deps = Object.fromEntries(D.deputados.map(d => [d.id, d]));
    el.innerHTML = `<div class="listhead"><div><span class="label">Cidade</span><h2 class="lt">${esc(titulo(nome))} - ${esc(uf)}</h2>
      <p class="meta">Todas as emendas com destino nesta cidade, de 2020 até hoje</p></div><button type="button" class="fechar" id="fechaCidade" aria-label="Fechar">×</button></div>
      <div class="totais"><div class="tot"><span class="label">Reservado</span><span class="v num">${curto(emp)}</span><small>${n} ${n === 1 ? 'emenda' : 'emendas'}</small></div>
      <div class="tot"><span class="label">Pago até agora</span><span class="v num">${curto(pago)}</span><small>${pct(pago, emp)}% do reservado</small></div></div>
      ${aut.length ? `<div class="label">Deputados em exercício que mais destinaram</div><div class="regs">${aut.map(([id, v]) => { const d = deps[id] || {}; return `<div class="reg"><div class="rh"><b><a href="${linkDep(id)}">${esc(d.nome || id)}</a></b><span class="num">${curto(v)}</span></div><small>${esc(d.partido || '')}-${esc(d.uf || '')}</small></div>`; }).join('')}</div>` : ''}
      <p class="note">Emendas de bancada, comissão e relator também entram no total da cidade. Para ver cada pagamento, consulte o <a href="https://portaldatransparencia.gov.br/emendas" target="_blank" rel="noopener">Portal da Transparência</a>.</p>`;
    el.hidden = false;
    $('fechaCidade').onclick = () => { el.hidden = true; history.replaceState(null, '', location.pathname); };
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function sugerir() {
    const t = norm($('q').value.trim()), sg = $('sugg');
    if (!t || !D) { sg.hidden = true; return; }
    const ds = D.deputados.filter(d => norm(d.nome).includes(t) || norm(d.partido) === t || norm(d.uf) === t).slice(0, 8);
    const cs = t.length >= 3 ? (await cidades()).filter(c => norm(c[1]).includes(t)).slice(0, 6) : [];
    if (norm($('q').value.trim()) !== t) return;
    const itens = ds.map(d => `<button type="button" data-href="${linkDep(d.id)}"><span>${esc(d.nome)} · ${esc(d.partido)}-${esc(d.uf)}</span><small>${curto(d.emp)} reservados</small></button>`)
      .concat(cs.map(c => `<button type="button" data-cidade="${c[0]}"><span>${esc(titulo(c[1]))} - ${esc(c[2])}</span><small>cidade · ${curto(c[3])}</small></button>`));
    sg.innerHTML = itens.join('') || '<button type="button" disabled><span>Nada encontrado</span><small>Tente o nome do deputado ou da cidade</small></button>';
    sg.hidden = false;
  }

  async function iniciar() {
    try {
      const [r, d] = await Promise.all([fetch('data/emendas/resumo.json', { cache: 'no-cache' }), fetch('data/emendas/deputados.json', { cache: 'no-cache' })]);
      if (!r.ok || !d.ok) throw new Error('sem dados');
      R = await r.json();
      D = await d.json();
    } catch (e) {
      $('anoSub').textContent = 'Os dados ainda estão sendo gerados pelo robô de atualização. Volte em alguns minutos.';
      $('lista').innerHTML = '<li class="empty">Sem dados ainda.</li>';
      return;
    }
    const [dia, h] = (R.atualizado || '').split(' ');
    $('upd').textContent = dia ? `Dados atualizados em ${dia.split('-').reverse().join('/')} às ${h}` : '';
    const anos = Object.keys(R.por_ano);
    const qs = new URLSearchParams(location.search);
    const salvo = lerg('re-ano');
    const fechados = anos.filter(a => +a !== R.parcial);
    const pedido = qs.get('ano') || salvo;
    ANO = anos.includes(pedido) ? pedido : (fechados[fechados.length - 1] || anos[anos.length - 1]);
    $('anos').innerHTML = anos.map(a => `<button type="button" data-a="${a}">${a}${+a === R.parcial ? ' (em curso)' : ''}</button>`).join('');
    if (R.pix) {
      const p = R.pix, tot = Object.values(p).reduce((s, x) => s + x.n, 0);
      $('pix').innerHTML = [
        ['Com relatório final', p.ok, 'prestação de contas entregue', ''],
        ['Dentro do prazo', p.andamento, 'execução ainda não terminou', ''],
        ['Prazo vencido sem relatório', p.atrasado, `mais de 6 meses depois do fim · ${curto(p.atrasado.valor)}`, 'bad'],
        ['Sem plano de trabalho', p.sem_plano, `planos de 2024 em diante · ${curto(p.sem_plano.valor)}`, 'warn'],
      ].map(([l, x, s, c]) => `<div class="tot ${c}"><span class="label">${l}</span><span class="v num">${x.n.toLocaleString('pt-BR')}</span><small>${pct(x.n, tot)}% · ${s}</small></div>`).join('');
      $('pixCard').hidden = false;
    }
    render();
    if (qs.get('cidade')) mostrarCidade(qs.get('cidade'));
  }

  $('anos').addEventListener('click', e => { const b = e.target.closest('button[data-a]'); if (b) { ANO = b.dataset.a; render(); } });
  $('ordem').addEventListener('click', e => { const b = e.target.closest('button[data-o]'); if (b) { ORD = b.dataset.o; guardar('re-ordem', ORD); renderLista(); } });
  $('mais').addEventListener('click', () => { TODOS = true; renderLista(); });
  $('munis').addEventListener('click', e => { const a = e.target.closest('a[href^="?cidade="]'); if (a) { e.preventDefault(); const ib = a.getAttribute('href').split('=')[1].split('#')[0]; history.replaceState(null, '', '?cidade=' + ib); mostrarCidade(ib); } });
  $('q').addEventListener('input', sugerir);
  $('q').addEventListener('keydown', e => { if (e.key === 'Enter') { const b = $('sugg').querySelector('button[data-href],button[data-cidade]'); if (b) b.click(); } });
  $('sugg').addEventListener('click', e => {
    const b = e.target.closest('button[data-href],button[data-cidade]');
    if (!b) return;
    if (b.dataset.href) { location.href = b.dataset.href; return; }
    $('sugg').hidden = true; $('q').value = '';
    history.replaceState(null, '', '?cidade=' + b.dataset.cidade);
    mostrarCidade(b.dataset.cidade);
  });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) $('sugg').hidden = true; });

  iniciar();
})();
