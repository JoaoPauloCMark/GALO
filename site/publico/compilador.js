// Compilador da GALO dentro do navegador, para o site estático (GitHub Pages).
//
// O site estático não tem servidor, então ninguém responde a .../api/compilar. Este arquivo
// atende esses pedidos no próprio navegador: o compilador de verdade, em Python (o pacote
// galo, em _galo/compilador.zip), roda no Pyodide — o Python oficial compilado para
// WebAssembly. Os programas GALO da página continuam usando buscar() como no servidor.
// Só é incluído na versão estática do site (site/publicar.sh).
(function () {
  'use strict';
  const PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v314.0.8/full/';
  const ZIP = new URL('../_galo/compilador.zip', document.currentScript.src).href;
  let pronto = null;

  function carregarScript(src) {
    return new Promise((ok, falha) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = ok;
      s.onerror = () => falha(new Error('não foi possível carregar ' + src));
      document.head.appendChild(s);
    });
  }

  // Carrega o Pyodide e o compilador uma vez só; as compilações seguintes são imediatas.
  function carregar() {
    if (!pronto) {
      pronto = (async () => {
        if (typeof loadPyodide !== 'function') await carregarScript(PYODIDE + 'pyodide.js');
        const py = await loadPyodide({ indexURL: PYODIDE });
        const zip = await (await fetch(ZIP)).arrayBuffer();
        py.unpackArchive(zip, 'zip', { extractDir: '/galo-src' });
        py.runPython("import sys; sys.path.insert(0, '/galo-src')");
        const compilar = py.runPython('from galo.web.navegador import compilar_json; compilar_json');
        compilar('{"código": ""}').destroy(); // importa o compilador agora, não no primeiro clique
        return compilar;
      })();
      pronto.catch(() => { pronto = null; }); // sem conexão: tenta de novo no próximo clique
    }
    return pronto;
  }

  function avisarCarregamento() {
    document.querySelectorAll('.status.rodando').forEach((el) => {
      el.textContent = 'carregando o compilador (só na primeira vez)…';
    });
  }

  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async function (recurso, opcoes) {
    const url = typeof recurso === 'string' ? recurso : (recurso && recurso.url) || '';
    const metodo = String((opcoes && opcoes.method) || 'GET').toUpperCase();
    if (metodo === 'POST' && /\/api\/compilar$/.test(url.split('?')[0])) {
      try {
        if (!pronto) avisarCarregamento();
        const compilar = await carregar();
        const tupla = compilar(String(opcoes.body || ''));
        const [status, corpo] = tupla.toJs();
        tupla.destroy();
        return new Response(corpo, { status, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
      } catch (e) {
        console.error(e);
        return new Response(JSON.stringify({ erro: 'Não foi possível carregar o compilador da GALO no navegador. Verifique a conexão e tente de novo.' }),
          { status: 503, headers: { 'Content-Type': 'application/json; charset=utf-8' } });
      }
    }
    return fetchOriginal(recurso, opcoes);
  };

  // Adianta o carregamento: no Experimente, assim que a página abre; na página inicial,
  // quando os exemplos aparecem na tela.
  function preparar() { carregar().catch(() => {}); }
  document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('botao-executar')) {
      setTimeout(preparar, 300);
    } else if (document.getElementById('exemplos') && 'IntersectionObserver' in window) {
      const observador = new IntersectionObserver((entradas) => {
        if (entradas.some((e) => e.isIntersecting)) { observador.disconnect(); preparar(); }
      });
      observador.observe(document.getElementById('exemplos'));
    }
  });
})();
