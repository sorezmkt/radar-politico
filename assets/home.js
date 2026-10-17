(() => {
  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const norm = s => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const faixa = n => n == null ? 'nd' : n >= 70 ? 'good' : n >= 45 ? 'warn' : 'bad';
  const RISCO = { baixo: ['good', 'Baixo'], moderado: ['warn', 'Moderado'], alto: ['bad', 'Alto'] };
  const link = id => `deputado.html?id=${id}`;

  // links antigos no formato radar-politico/#123456 continuam funcionando
  const h = location.hash.slice(1);
  if (/^\d+$/.test(h)) { location.replace(link(h)); return; }
  window.addEventListener('hashchange', () => { const x = location.hash.slice(1); if (/^\d+$/.test(x)) location.replace(link(x)); });

  let IDX = null;

  function sugerir() {
    const t = norm($('q').value.trim()), sg = $('sugg');
    if (!t || !IDX) { sg.hidden = true; return; }
    const m = IDX.deputados.filter(d => norm(d.nome).includes(t) || norm(d.partido) === t || norm(d.uf) === t).slice(0, 12);
    sg.innerHTML = m.length
      ? m.map(d => `<button type="button" data-id="${d.id}"><span>${esc(d.nome)}</span><small>${esc(d.partido)} · ${esc(d.uf)} · nota ${d.nota ?? '–'}</small></button>`).join('')
      : '<button type="button" disabled><span>Nenhum deputado encontrado</span><small>Tente outro nome</small></button>';
    sg.hidden = false;
  }

  async function iniciar() {
    try {
      const r = await fetch('data/index.json', { cache: 'no-cache' });
      if (!r.ok) throw new Error(r.status);
      IDX = await r.json();
    } catch (e) {
      $('l50').innerHTML = '<li class="empty">Os dados ainda estão sendo gerados pelo robô de atualização. Volte em alguns minutos.</li>';
      return;
    }
    const [a, hr] = (IDX.atualizado || '').split(' ');
    $('upd').textContent = a ? `Dados atualizados em ${a.split('-').reverse().join('/')} às ${hr}` : '';
    if (IDX.fontes && IDX.fontes.presenca) $('mPres').textContent = IDX.fontes.presenca;
    if (IDX.referencias && IDX.referencias.prod_p90) $('mProd').textContent = `${IDX.referencias.prod_p90} ou mais no período (nível dos 10% mais produtivos)`;

    const comNota = IDX.deputados.filter(d => d.nota != null);
    // do maior para o menor risco; no empate de pontos, a menor eficiência vem antes
    const piores = [...comNota].sort((x, y) => (y.pontos || 0) - (x.pontos || 0) || x.nota - y.nota).slice(0, 50);
    $('l50sub').textContent = `Entre ${comNota.length} deputados avaliados, os que têm mais sinais de risco nos gastos, do maior para o menor. Risco aqui são pontos de atenção nos dados públicos, não uma acusação. Toque num nome para ver a ficha completa.`;
    $('l50').innerHTML = piores.map((d, i) => {
      const [rc, rl] = RISCO[d.risco] || RISCO.baixo;
      return `<li><a href="${link(d.id)}">
        <span class="pos num">${i + 1}</span>
        <span class="who2"><span class="nm2">${esc(d.nome)}</span><small>${esc(d.partido)} · ${esc(d.uf)}</small></span>
        <span class="score s-${faixa(d.nota)} num" aria-label="Índice de eficiência ${d.nota}">${d.nota}</span>
        <span class="rk v-${rc}" aria-label="Risco ${rl}">${rl}</span>
      </a></li>`;
    }).join('');
  }

  $('q').addEventListener('input', sugerir);
  $('q').addEventListener('keydown', e => {
    if (e.key === 'Enter') { const b = $('sugg').querySelector('button[data-id]'); if (b) b.click(); }
  });
  $('sugg').addEventListener('click', e => {
    const b = e.target.closest('button[data-id]');
    if (b) location.href = link(b.dataset.id);
  });
  document.addEventListener('click', e => { if (!e.target.closest('.search')) $('sugg').hidden = true; });

  iniciar();
})();
