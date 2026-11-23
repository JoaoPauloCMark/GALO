// Testa as funções de página de galo.js com um DOM simulado (sem navegador).
// Uso: gjs dom_falso.js galo.js programa.galoc saida.txt
const GLib = imports.gi.GLib;
const ler = (p) => GLib.file_get_contents(p)[1];
let saida = '';
const registrar = (t) => { saida += t; };

(0, eval)(new TextDecoder().decode(ler(GLib.path_get_dirname(imports.system.programInvocationName) + '/dom.js')));
const { Elemento, Texto } = globalThis.DomFalso;
const body = new Elemento('body');
const criar = (tag, id) => { const e = new Elemento(tag); if (id) e.setAttribute('id', id); body.appendChild(e); return e; };
const form = criar('form', 'form');
const campo = criar('input', 'novo');
const lista = criar('ul', 'lista');
globalThis.document = {
  body, readyState: 'complete', addEventListener() {},
  createElement: (t) => new Elemento(t), createTextNode: (t) => new Texto(t),
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  getElementById: (id) => body.querySelector('#' + id),
};
const armazem = {};
globalThis.localStorage = { getItem: (k) => (k in armazem ? armazem[k] : null), setItem: (k, v) => { armazem[k] = v; }, removeItem: (k) => { delete armazem[k]; } };
globalThis.fetch = (url, init) => Promise.resolve({
  status: url.includes('falha') ? 404 : 200,
  headers: new Map([['content-type', 'application/json']]),
  text: () => Promise.resolve(JSON.stringify({ url, método: init.method, corpo: init.body || null })),
});

(0, eval)(new TextDecoder().decode(ler(ARGV[0])));
const vm = globalThis.Galo.executarModulo(globalThis.Galo.carregar(ler(ARGV[1])), {
  escrever: registrar, aoErro: (e) => registrar(globalThis.Galo.formatarErro(e) + '\n'),
});

// Interações do "usuário"
campo.value = 'segundo';
const envio = form.disparar('submit');
registrar(`envio cancelado: ${envio.prevented}\n`);
lista.children[0].disparar('click');
registrar(`classes do primeiro: ${[...lista.children[0].classList.s].join(' ')}\n`);
registrar(`itens: ${lista.children.map((li) => li.textContent).join(', ')} | campo: "${campo.value}"\n`);
registrar(`armazenado: ${armazem.itens}\n`);

const laco = new GLib.MainLoop(null, false);
setTimeout(() => { GLib.file_set_contents(ARGV[2], saida); laco.quit(); }, 100);
laco.run();
