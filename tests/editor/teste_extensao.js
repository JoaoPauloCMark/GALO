// Testes da extensão GALO executados DENTRO de um editor real (VS Code ou Cursor), pela
// API de testes de extensões (--extensionTestsPath). Não depende de pacotes npm.
// O resultado é gravado em JSON no caminho da variável GALO_RESULTADO_EXTENSAO.
'use strict';

const vscode = require('vscode');
const fs = require('fs');
const path = require('path');

const pausa = (ms) => new Promise((r) => setTimeout(r, ms));

async function esperar(condicao, descricao, limite = 30000) {
  const fim = Date.now() + limite;
  let ultimo;
  while (Date.now() < fim) {
    ultimo = await condicao();
    if (ultimo) return ultimo;
    await pausa(100);
  }
  throw new Error(`tempo esgotado esperando ${descricao}`);
}

function igual(atual, esperado, descricao) {
  const a = JSON.stringify(atual);
  const e = JSON.stringify(esperado);
  if (a !== e) throw new Error(`${descricao}: esperado ${e}, obtido ${a}`);
}

function verdade(valor, descricao) {
  if (!valor) throw new Error(descricao);
}

const codigo = (d) => (d.code && typeof d.code === 'object' ? d.code.value : d.code);
const pasta = () => vscode.workspace.workspaceFolders[0].uri.fsPath;
const arquivo = (nome) => vscode.Uri.file(path.join(pasta(), nome));

async function abrir(nome) {
  const doc = await vscode.workspace.openTextDocument(arquivo(nome));
  const editor = await vscode.window.showTextDocument(doc);
  return { doc, editor };
}

const testes = [];
const teste = (nome, fn) => testes.push({ nome, fn });

teste('arquivos .galo são reconhecidos e a extensão é ativada', async () => {
  const { doc } = await abrir('certo.galo');
  igual(doc.languageId, 'galo', 'linguagem do documento');
  const ext = vscode.extensions.getExtension('galo.galo-linguagem');
  verdade(ext, 'extensão galo.galo-linguagem não encontrada');
  await esperar(() => ext.isActive, 'a ativação da extensão');
});

teste('comandos da extensão estão registrados', async () => {
  const todos = await vscode.commands.getCommands(true);
  for (const c of ['galo.executar', 'galo.compilar', 'galo.rodarCompilado', 'galo.verificar', 'galo.abrirRepl', 'galo.reiniciarServidor']) {
    verdade(todos.includes(c), `comando ${c} não registrado`);
  }
});

teste('o servidor de linguagem mostra erros enquanto se digita', async () => {
  const { doc, editor } = await abrir('com_erro.galo');
  const diags = await esperar(() => {
    const d = vscode.languages.getDiagnostics(doc.uri);
    return d.length ? d : null;
  }, 'diagnósticos do LSP');
  igual(diags.map(codigo), ['G201'], 'códigos');
  igual([diags[0].range.start.line, diags[0].range.start.character, diags[0].range.end.character], [1, 7, 16], 'posição do erro');
  igual(diags[0].severity, vscode.DiagnosticSeverity.Error, 'gravidade');
  verdade(diags[0].message.includes('A variável "pontuacao" não foi definida.'), 'mensagem: ' + diags[0].message);
  verdade(diags[0].message.includes('defina pontuacao como 0'), 'sugestão na mensagem');
  // Corrigir o código remove o erro.
  await editor.edit((e) => e.replace(new vscode.Range(1, 7, 1, 16), 'x'));
  await esperar(() => vscode.languages.getDiagnostics(doc.uri).length === 0, 'o erro sumir depois da correção');
  // Um nome que esconde função interna gera aviso (não erro).
  await editor.edit((e) => e.insert(new vscode.Position(0, 0), 'defina texto como "a"\n'));
  const avisos = await esperar(() => {
    const d = vscode.languages.getDiagnostics(doc.uri);
    return d.length ? d : null;
  }, 'o aviso A201');
  igual(avisos.map(codigo), ['A201'], 'aviso');
  igual(avisos[0].severity, vscode.DiagnosticSeverity.Warning, 'gravidade do aviso');
  await vscode.commands.executeCommand('workbench.action.revertAndCloseActiveEditor');
});

teste('erros em módulos importados são mostrados', async () => {
  const { doc } = await abrir('usa_modulo.galo');
  const diags = await esperar(() => {
    const d = vscode.languages.getDiagnostics(doc.uri);
    return d.length ? d : null;
  }, 'diagnóstico de importação');
  igual(diags.map(codigo), ['G221'], 'nome não exportado');
});

teste('autocompletar oferece palavras-chave, funções internas, nomes do arquivo e modelos', async () => {
  const { doc } = await abrir('certo.galo');
  const lista = await vscode.commands.executeCommand('vscode.executeCompletionItemProvider', doc.uri, new vscode.Position(3, 0));
  const rotulos = lista.items.map((i) => (typeof i.label === 'string' ? i.label : i.label.label));
  for (const r of ['enquanto', 'registro', 'importe', 'tamanho', 'criar_servidor', 'abrir_banco', 'elemento', 'quantidade']) {
    verdade(rotulos.includes(r), `autocompletar sem "${r}"`);
  }
  const snippet = lista.items.find((i) => i.kind === vscode.CompletionItemKind.Snippet &&
    (typeof i.label === 'string' ? i.label : i.label.label) === 'registro');
  verdade(snippet, 'snippet "registro" ausente');
});

teste('passar o mouse mostra a documentação das funções internas', async () => {
  const { doc } = await abrir('certo.galo');
  const linha = doc.lineAt(2).text;
  const hovers = await vscode.commands.executeCommand('vscode.executeHoverProvider', doc.uri,
    new vscode.Position(2, linha.indexOf('tamanho') + 2));
  const texto = hovers.map((h) => h.contents.map((c) => (typeof c === 'string' ? c : c.value)).join('\n')).join('\n');
  verdade(texto.includes('tamanho(valor)'), 'hover sem a assinatura: ' + texto);
});

teste('reindentar segue os blocos da linguagem', async () => {
  const { doc } = await abrir('indentar.galo');
  await vscode.commands.executeCommand('editor.action.reindentlines');
  await pausa(200);
  const esperado = [
    'função f(x)', '    se x então', '        mostre 1', '    senão', '        mostre 2', '    fim', 'fim',
    'registro R', '    a', '    função m()', '        retorne eu.a', '    fim', 'fim',
    'enquanto falso faça', '    repita 2 vezes', '        mostre 3', '    fim', 'fim',
    'tente', '    mostre 4', 'capture erro', '    mostre erro', 'fim', '',
  ];
  igual(doc.getText().split('\n'), esperado, 'texto reindentado');
  await vscode.commands.executeCommand('workbench.action.revertAndCloseActiveEditor');
});

teste('realce de sintaxe identifica as partes do código', async () => {
  const uri = arquivo('realce.galo');
  await abrir('realce.galo');
  let tokens;
  try {
    tokens = await vscode.commands.executeCommand('_workbench.captureSyntaxTokens', uri);
  } catch (e) {
    throw new Error('o editor não oferece _workbench.captureSyntaxTokens: ' + e.message);
  }
  const escopo = (trecho) => {
    const t = tokens.find((x) => x.c === trecho);
    if (!t) throw new Error(`trecho "${trecho}" não encontrado nos tokens: ${JSON.stringify(tokens.map((x) => x.c))}`);
    return t.t;
  };
  const conferir = (trecho, parte) => verdade(escopo(trecho).includes(parte), `"${trecho}" deveria ter ${parte}, tem ${escopo(trecho)}`);
  conferir('se', 'keyword.control.galo');
  conferir('então', 'keyword.control.galo');
  conferir('registro', 'storage.type');
  conferir('Ponto', 'entity.name.type.galo');
  conferir('função', 'storage.type');
  conferir('dobro', 'entity.name.function.galo');
  conferir('verdadeiro', 'constant.language.galo');
  conferir('42', 'constant.numeric.galo');
  conferir('# comentário', 'comment.line');
  conferir("'{literal}'", 'string.quoted.single.galo');
  conferir('eu', 'variable.language');
  conferir('tamanho', 'support.function.builtin.galo');
  verdade(escopo('nome').includes('meta.interpolation.galo'), 'interpolação dentro do texto');
});

teste('tarefas: a extensão oferece executar, compilar e verificar para o arquivo aberto', async () => {
  await abrir('certo.galo');
  const tarefas = await vscode.tasks.fetchTasks({ type: 'galo' });
  const doArquivo = tarefas.filter((t) => !t.definition.arquivo).map((t) => t.definition.comando).sort();
  igual(doArquivo, ['compilar', 'executar', 'verificar'], 'tarefas oferecidas');
});

teste('tarefa do tasks.json roda a GALO e o painel Problemas recebe os erros', async () => {
  // nao_aberto.galo nunca é aberto: os diagnósticos só podem vir do problem matcher da tarefa.
  const uri = arquivo('nao_aberto.galo');
  igual(vscode.languages.getDiagnostics(uri).length, 0, 'diagnósticos antes da tarefa');
  const tarefas = await vscode.tasks.fetchTasks({ type: 'galo' });
  const tarefa = tarefas.find((t) => t.name === 'GALO: verificar arquivo fechado');
  verdade(tarefa, 'a tarefa do tasks.json não foi encontrada: ' + tarefas.map((t) => t.name).join(', '));
  const fim = new Promise((resolve) => {
    const d = vscode.tasks.onDidEndTaskProcess((e) => {
      if (e.execution.task.name === tarefa.name) { d.dispose(); resolve(e.exitCode); }
    });
  });
  await vscode.tasks.executeTask(tarefa);
  igual(await fim, 1, 'código de saída de galo verificar');
  let diags;
  try {
    diags = await esperar(() => {
      const d = vscode.languages.getDiagnostics(uri);
      return d.length >= 2 ? d : null;
    }, 'os problemas da tarefa', 15000);
  } catch (e) {
    const todos = vscode.languages.getDiagnostics().map(([u, d]) => `${u.toString()}: ${d.map(codigo).join(',')}`);
    throw new Error(`${e.message}; escopo=${typeof tarefa.scope === 'object' ? tarefa.scope.name : tarefa.scope}; ` +
      `matchers=${JSON.stringify(tarefa.problemMatchers)}; diagnósticos=${JSON.stringify(todos)}`);
  }
  const porCodigo = diags.map((d) => [codigo(d), d.range.start.line, d.severity]).sort();
  igual(porCodigo, [['A201', 0, vscode.DiagnosticSeverity.Warning], ['G215', 1, vscode.DiagnosticSeverity.Error]], 'problemas');
});

teste('o comando Executar abre o terminal GALO', async () => {
  await abrir('certo.galo');
  await vscode.commands.executeCommand('galo.executar');
  await esperar(() => vscode.window.terminals.some((t) => t.name === 'GALO'), 'o terminal GALO');
});

teste('reiniciar o servidor de linguagem mantém os diagnósticos funcionando', async () => {
  await vscode.commands.executeCommand('galo.reiniciarServidor');
  await pausa(1000);
  const { doc, editor } = await abrir('certo.galo');
  await editor.edit((e) => e.insert(new vscode.Position(0, 0), 'mostre inexistente\n'));
  const diags = await esperar(() => {
    const d = vscode.languages.getDiagnostics(doc.uri);
    return d.length ? d : null;
  }, 'diagnósticos após reiniciar');
  igual(diags.map(codigo), ['G201'], 'erro após reiniciar');
  await vscode.commands.executeCommand('workbench.action.revertAndCloseActiveEditor');
});

exports.run = async function () {
  const resultados = [];
  for (const t of testes) {
    const inicio = Date.now();
    try {
      await t.fn();
      resultados.push({ nome: t.nome, ok: true, ms: Date.now() - inicio });
    } catch (e) {
      resultados.push({ nome: t.nome, ok: false, erro: String((e && e.stack) || e), ms: Date.now() - inicio });
    }
  }
  resultados.push({ nome: '__editor', ok: true, info: `${vscode.env.appName} ${vscode.version}` });
  fs.writeFileSync(process.env.GALO_RESULTADO_EXTENSAO, JSON.stringify(resultados, null, 2));
};
