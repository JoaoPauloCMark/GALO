// Executa um .galoc na VM JavaScript (galo.js) usando o gjs, sem navegador.
// Uso: gjs rodar_galoc.js galo.js programa.galoc saida.txt [linhas de entrada...]
const GLib = imports.gi.GLib;
const ler = (p) => GLib.file_get_contents(p)[1];
(0, eval)(new TextDecoder().decode(ler(ARGV[0])));
const entradas = ARGV.slice(3);
let saida = '';
const opcoes = {
  escrever: (t) => { saida += t; },
  ler: (msg) => { saida += msg; return entradas.length ? entradas.shift() : null; },
  aoErro: (e) => { saida += globalThis.Galo.formatarErro(e) + '\n'; },
};
try {
  globalThis.Galo.executarModulo(globalThis.Galo.carregar(ler(ARGV[1])), opcoes);
} catch (e) {
  if (e && e.codigo) saida += globalThis.Galo.formatarErro(e) + '\n';  // erro GALO (ex.: bytecode inválido)
  else saida += 'FALHA INTERNA: ' + e + '\n' + e.stack;
}
GLib.file_set_contents(ARGV[2], saida);
