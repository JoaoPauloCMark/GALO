// Testa o frontend do exemplo examples/tarefas (cliente.galo compilado) com um DOM
// simulado e um backend falso em memória. Uso: gjs cliente_tarefas.js galo.js cliente.galoc saida.txt
const GLib = imports.gi.GLib;
const ler = (p) => GLib.file_get_contents(p)[1];
(0, eval)(new TextDecoder().decode(ler(GLib.path_get_dirname(imports.system.programInvocationName) + '/dom.js')));
const { Elemento, Texto } = globalThis.DomFalso;
let log = '';
const registrar = (t) => { log += t; };

const body = new Elemento('body');
const criar = (tag, id, pai = body) => { const e = new Elemento(tag); e.setAttribute('id', id); pai.appendChild(e); return e; };
const resumo = criar('p', 'resumo');
const form = criar('form', 'nova-tarefa');
const campo = criar('input', 'titulo', form);
const lista = criar('ul', 'tarefas');
globalThis.document = {
  body, readyState: 'complete', addEventListener() {},
  createElement: (t) => new Elemento(t), createTextNode: (t) => new Texto(t),
  querySelector: (s) => body.querySelector(s), querySelectorAll: (s) => body.querySelectorAll(s),
  getElementById: (id) => body.querySelector('#' + id),
};
globalThis.confirm = (m) => { registrar(`[confirmar] ${m}\n`); return true; };
globalThis.alert = (m) => registrar(`[alerta] ${m}\n`);

// Backend falso com o mesmo contrato da API real.
const tarefas = []; let proximo = 1;
globalThis.fetch = (url, init) => {
  registrar(`[rede] ${init.method} ${url}${init.body ? ' ' + init.body : ''}\n`);
  let status = 200; let corpo = null;
  const m = /^\/api\/tarefas\/(\d+)$/.exec(url);
  if (url === '/api/tarefas' && init.method === 'GET') corpo = tarefas;
  else if (url === '/api/tarefas' && init.method === 'POST') {
    const t = { id: proximo++, 'título': JSON.parse(init.body)['título'], feita: false }; tarefas.push(t); status = 201; corpo = t;
  } else if (m && init.method === 'PATCH') { const t = tarefas.find((x) => x.id === +m[1]); Object.assign(t, JSON.parse(init.body)); corpo = t; }
  else if (m && init.method === 'DELETE') { tarefas.splice(tarefas.findIndex((x) => x.id === +m[1]), 1); status = 204; }
  else { status = 404; corpo = { erro: 'rota inexistente' }; }
  return Promise.resolve({ status, headers: new Map([['content-type', 'application/json']]), text: () => Promise.resolve(corpo === null ? '' : JSON.stringify(corpo)) });
};

(0, eval)(new TextDecoder().decode(ler(ARGV[0])));
globalThis.Galo.executarModulo(globalThis.Galo.carregar(ler(ARGV[1])), {
  escrever: registrar, aoErro: (e) => registrar(globalThis.Galo.formatarErro(e) + '\n'),
});

const estado = (rotulo) => registrar(`== ${rotulo}: resumo="${resumo.textContent}" itens=[${lista.children.map((li) =>
  `${li.children[1].textContent}${li.classList.contains('feita') ? ' (feita)' : ''}`).join(', ')}]\n`);
const esperar = () => new Promise((r) => setTimeout(r, 15));
const laco = new GLib.MainLoop(null, false);
(async () => {
  await esperar(); estado('início');
  campo.value = '  Estudar GALO '; form.disparar('submit'); await esperar(); estado('depois de criar');
  campo.value = 'Publicar o app'; form.disparar('submit'); await esperar(); estado('segunda tarefa');
  const caixa = lista.children[0].children[0]; caixa.checked = true; caixa.disparar('change'); await esperar(); estado('depois de marcar');
  lista.children[1].children[2].disparar('click'); await esperar(); estado('depois de apagar');
  registrar(`campo vazio depois de enviar: ${campo.value === ''}\n`);
})().catch((e) => registrar('FALHA: ' + e + '\n' + e.stack)).finally(() => { GLib.file_set_contents(ARGV[2], log); laco.quit(); });
laco.run();
