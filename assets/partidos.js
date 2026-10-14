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
  const RISCO = { baixo: ['good', 'Baixo'], moderado: ['warn', 'Moderado'], alto: ['bad', 'Alto'] };
  const link = (p, ano) => `partido.html?p=${p.slug}&ano=${ano}`;
  const guardar = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* sem armazenamento */ } };
  const lerg = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };

  let IDX = null, ANO = null, ORD = lerg('rp-ordem') || 'receita';

  function sugerir() {
    const t = norm($('q').value.trim()), sg = $('sugg');
    if (!t || !IDX) { sg.hidden = true; return; }
    const m = IDX.partidos.filter(p => norm(p.sg).includes(t) || norm(p.nome).includes(t)).slice(0, 12);
    sg.innerHTML = m.length
      ? m.map(p => { const a = p.anos[ANO]; return `<button type="button" data-href="${link(p, a ? ANO : Math.max(...Object.keys(p.anos)))}"><span>${esc(p.sg)} · ${esc(p.nome)}</span><small>${a ? 'recebeu ' + curto(a.receita) + ' em ' + ANO : 'sem contas em ' + ANO}</small></button>`; }).join('')
      : '<button type="button" disabled><span>Nenhum partido encontrado</span><small>Tente a sigla, como PT ou PL</small></button>';
    sg.hidden = false;
  }

  function render() {
    const ano = ANO, el = IDX.eleitorais.includes(+ano);
    $('anoT').textContent = ano;
    document.querySelectorAll('#anos button').forEach(b => b.setAttribute('aria-pressed', b.dataset.a === String(ano)));
    document.querySelectorAll('#ordem button').forEach(b => b.setAttribute('aria-pressed', b.dataset.o === ORD));
    const ps = IDX.partidos.filter(p => p.anos[ano]);
    const ativos = ps.filter(p => !p.anos[ano].sem_movimento);
    const soma = k => ps.reduce((s, p) => s + (p.anos[ano][k] || 0), 0);
    const ref = (IDX.referencias || {})[ano];
    $('anoSub').textContent = `${ativos.length} diretórios nacionais com movimento${el ? ' · ano de eleição' : ''}${ref ? ` · arquivo do TSE gerado em ${ref}` : ''}`;
    const pub = soma('publico'), rec = soma('receita');
    $('totais').innerHTML = [
      ['Receberam', curto(rec), 'em dinheiro no ano'],
      ['Dinheiro público', curto(pub), rec ? `${Math.round(pub / rec * 100)}% do que entrou` : ''],
      ['Repassaram', curto(soma('transferencias')), 'a candidatos e a outras direções'],
      ['Gastaram', curto(soma('gasto')), 'com fornecedores, pessoal e tributos'],
    ].map(([l, v, s]) => `<div class="tot"><span class="label">${l}</span><span class="v num">${v}</span><small>${s}</small></div>`).join('');

    const ord = [...ps].sort((a, b) => {
      const x = a.anos[ano], y = b.anos[ano];
      if (ORD === 'nome') return a.sg.localeCompare(b.sg, 'pt-BR');
      if (ORD === 'pontos') return (y.pontos - x.pontos) || (y.receita - x.receita);
      return y.receita - x.receita;
    });
    $('listSub').textContent = ORD === 'pontos' ? 'Ordenados pelo nível de atenção dos alertas automáticos. Toque num partido para ver a ficha completa.' : 'Toque num partido para ver a ficha completa.';
    $('lista').innerHTML = ord.map(p => {
      const a = p.anos[ano];
      const [rc, rl] = a.sem_movimento ? ['nd', 'Sem movimento'] : (RISCO[a.nivel] || RISCO.baixo);
      const pp = a.receita ? Math.round(a.publico / a.receita * 100) : 0;
      return `<li class="${a.sem_movimento ? 'off' : ''}"><a href="${link(p, ano)}">
        <span class="pnm"><span class="sigla">${esc(p.sg)}</span><span><b>${esc(p.nome)}</b><small>${a.alertas ? `${a.alertas} ${a.alertas === 1 ? 'alerta' : 'alertas'}` : a.sem_movimento ? 'declarou não ter movimento' : 'nenhum alerta'}</small></span></span>
        <span class="pval"><span class="num">${curto(a.receita)}</span><span class="pubbar" title="${pp}% de dinheiro público"><i style="width:${pp}%"></i></span><small>${pp}% público</small></span>
        <span class="rk v-${rc}">${rl}</span>
      </a></li>`;
    }).join('') || '<li class="empty">Nenhum partido com contas neste ano.</li>';
    guardar('rp-ano', ano);
  }

  async function iniciar() {
    try {
      const r = await fetch('data/partidos/index.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(r.status);
      IDX = await r.json();
    } catch (e) {
      $('lista').innerHTML = '<li class="empty">Os dados ainda estão sendo gerados pelo robô de atualização. Volte em alguns minutos.</li>';
      $('anoSub').textContent = '';
      return;
    }
    const [d, h] = (IDX.atualizado || '').split(' ');
    $('upd').textContent = d ? `Dados atualizados em ${d.split('-').reverse().join('/')} às ${h}` : '';
    const anos = IDX.anos.map(String);
    const pedido = new URLSearchParams(location.search).get('ano') || lerg('rp-ano');
    ANO = anos.includes(pedido) ? pedido : anos[anos.length - 1];
    $('anos').innerHTML = anos.map(a => `<button type="button" data-a="${a}">${a}</button>`).join('');
    if (IDX.ipca && IDX.ipca.ate) $('ipcaRef').textContent = `até ${IDX.ipca.ate}`;
    const nomes = { duplicidade: 'Possíveis pagamentos duplicados', fora_padrao: 'Valores fora do padrão', concentracao: 'Concentração de pagamentos', temporal: 'Padrões no tempo', documental: 'Inconsistências documentais', cnpj: 'Situação dos fornecedores na Receita' };
    $('regras').innerHTML = Object.entries(IDX.regras || {}).map(([k, t]) => `<li><b>${nomes[k] || k}.</b> ${esc(t)}</li>`).join('');
    render();
  }

  $('anos').addEventListener('click', e => { const b = e.target.closest('button[data-a]'); if (b) { ANO = b.dataset.a; history.replaceState(null, '', '?ano=' + ANO); render(); } });
  $('ordem').addEventListener('click', e => { const b = e.target.closest('button[data-o]'); if (b) { ORD = b.dataset.o; guardar('rp-ordem', ORD); render(); } });
  $('q').addEventListener('input', sugerir);
  $('q').addEventListener('keydown', e => { if (e.key === 'Enter') { const b = $('sugg').querySelector('button[data-href]'); if (b) b.click(); } });
  $('sugg').addEventListener('click', e => { const b = e.target.closest('button[data-href]'); if (b) location.href = b.dataset.href; });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) $('sugg').hidden = true; });

  iniciar();
})();
