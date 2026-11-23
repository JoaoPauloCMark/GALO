// Extensão do VS Code para a linguagem GALO.
//
// Não depende de pacotes npm: inclui um cliente LSP mínimo que conversa com
// `galo lsp` por stdin/stdout (JSON-RPC 2.0 com cabeçalhos Content-Length).
'use strict';

const vscode = require('vscode');
const cp = require('child_process');
const path = require('path');

let servidor = null;
let buffer = Buffer.alloc(0);
let proximoId = 1;
const pendentes = new Map();
const temporizadores = new Map();
let diagnosticos = null;
let saida = null;
let pronto = false;

function config() {
  return vscode.workspace.getConfiguration('galo');
}

function executavel() {
  return config().get('caminhoExecutavel') || 'galo';
}

// ------------------------------------------------------------------ LSP

function enviar(mensagem) {
  if (!servidor || !servidor.stdin.writable) {
    return;
  }
  const dados = Buffer.from(JSON.stringify(mensagem), 'utf8');
  servidor.stdin.write('Content-Length: ' + dados.length + '\r\n\r\n');
  servidor.stdin.write(dados);
}

function pedir(metodo, parametros) {
  const id = proximoId++;
  return new Promise((resolve, reject) => {
    pendentes.set(id, { resolve, reject });
    enviar({ jsonrpc: '2.0', id: id, method: metodo, params: parametros });
  });
}

function rejeitarPendentes() {
  for (const p of pendentes.values()) {
    p.reject(new Error('servidor encerrado'));
  }
  pendentes.clear();
}

function comLimite(promessa, ms) {
  return Promise.race([promessa, new Promise((resolve) => setTimeout(resolve, ms))]);
}

function avisar(metodo, parametros) {
  enviar({ jsonrpc: '2.0', method: metodo, params: parametros });
}

function aoReceberDados(pedaco) {
  buffer = Buffer.concat([buffer, pedaco]);
  for (;;) {
    const separador = buffer.indexOf('\r\n\r\n');
    if (separador < 0) {
      return;
    }
    const cabecalho = buffer.slice(0, separador).toString('ascii');
    const m = /Content-Length:\s*(\d+)/i.exec(cabecalho);
    if (!m) {
      buffer = buffer.slice(separador + 4);
      continue;
    }
    const tamanho = parseInt(m[1], 10);
    const inicio = separador + 4;
    if (buffer.length < inicio + tamanho) {
      return;
    }
    const corpo = buffer.slice(inicio, inicio + tamanho).toString('utf8');
    buffer = buffer.slice(inicio + tamanho);
    let mensagem;
    try {
      mensagem = JSON.parse(corpo);
    } catch (e) {
      continue;
    }
    tratarMensagem(mensagem);
  }
}

function tratarMensagem(msg) {
  if (msg.id !== undefined && pendentes.has(msg.id) && ('result' in msg || 'error' in msg)) {
    const p = pendentes.get(msg.id);
    pendentes.delete(msg.id);
    if (msg.error) {
      p.reject(msg.error);
    } else {
      p.resolve(msg.result);
    }
    return;
  }
  if (msg.method === 'textDocument/publishDiagnostics' && diagnosticos) {
    const uri = vscode.Uri.parse(msg.params.uri);
    diagnosticos.set(uri, (msg.params.diagnostics || []).map(paraDiagnostico));
  }
}

function paraDiagnostico(d) {
  const r = d.range;
  const faixa = new vscode.Range(r.start.line, r.start.character, r.end.line, r.end.character);
  const gravidade = d.severity === 2 ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Error;
  const diag = new vscode.Diagnostic(faixa, d.message, gravidade);
  diag.code = d.code;
  diag.source = 'galo';
  return diag;
}

function abrirDocumento(doc) {
  if (!pronto || doc.languageId !== 'galo') {
    return;
  }
  avisar('textDocument/didOpen', {
    textDocument: { uri: doc.uri.toString(), languageId: 'galo', version: doc.version, text: doc.getText() }
  });
}

function alterarDocumento(evento) {
  const doc = evento.document;
  if (!pronto || doc.languageId !== 'galo') {
    return;
  }
  const chave = doc.uri.toString();
  clearTimeout(temporizadores.get(chave));
  temporizadores.set(chave, setTimeout(() => {
    temporizadores.delete(chave);
    avisar('textDocument/didChange', {
      textDocument: { uri: chave, version: doc.version },
      contentChanges: [{ text: doc.getText() }]
    });
  }, 250));
}

function fecharDocumento(doc) {
  if (doc.languageId !== 'galo') {
    return;
  }
  if (pronto) {
    avisar('textDocument/didClose', { textDocument: { uri: doc.uri.toString() } });
  }
  if (diagnosticos) {
    diagnosticos.delete(doc.uri);
  }
}

function iniciarServidor() {
  if (!config().get('lsp.habilitado', true)) {
    saida.appendLine('Servidor de linguagem desabilitado (galo.lsp.habilitado = false).');
    return;
  }
  const comando = executavel();
  buffer = Buffer.alloc(0);
  pronto = false;
  try {
    servidor = cp.spawn(comando, ['lsp'], { stdio: ['pipe', 'pipe', 'pipe'], shell: process.platform === 'win32' });
  } catch (e) {
    saida.appendLine('Não foi possível iniciar "' + comando + ' lsp": ' + e.message);
    servidor = null;
    return;
  }
  const este = servidor;
  este.on('error', (erro) => {
    saida.appendLine('Não foi possível iniciar "' + comando + ' lsp": ' + erro.message);
    vscode.window.showWarningMessage(
      'GALO: não encontrei o comando "' + comando + '". Instale a GALO ou ajuste a configuração galo.caminhoExecutavel.'
    );
    if (servidor === este) {
      servidor = null;
      pronto = false;
    }
  });
  este.on('exit', (codigo) => {
    saida.appendLine('Servidor de linguagem encerrado (código ' + codigo + ').');
    if (servidor === este) {
      servidor = null;
      pronto = false;
      rejeitarPendentes();
    }
  });
  este.stderr.on('data', (d) => saida.append(d.toString()));
  este.stdout.on('data', aoReceberDados);
  pedir('initialize', { processId: process.pid, rootUri: null, capabilities: {} }).then(() => {
    avisar('initialized', {});
    pronto = true;
    vscode.workspace.textDocuments.forEach(abrirDocumento);
    saida.appendLine('Servidor de linguagem GALO iniciado.');
  }, (erro) => saida.appendLine('Falha ao inicializar o servidor: ' + JSON.stringify(erro)));
}

function pararServidor() {
  if (!servidor) {
    return Promise.resolve();
  }
  const antigo = servidor;
  return comLimite(pedir('shutdown', null), 2000).then(() => {
    avisar('exit', null);
  }, () => undefined).then(() => {
    pronto = false;
    if (servidor === antigo) {
      servidor = null;
    }
    rejeitarPendentes();
    setTimeout(() => {
      if (antigo.exitCode === null && !antigo.killed) {
        antigo.kill();
      }
    }, 1000);
  });
}

// ------------------------------------------------------------------ comandos e tarefas

function arquivoAtual() {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== 'galo') {
    vscode.window.showErrorMessage('GALO: abra um arquivo .galo primeiro.');
    return null;
  }
  return editor.document;
}

function citar(texto) {
  return '"' + texto.replace(/"/g, '\\"') + '"';
}

function linhaDeComando(args) {
  const exe = executavel();
  const partes = [/\s/.test(exe) ? citar(exe) : exe].concat(args.map(citar));
  const linha = partes.join(' ');
  return process.platform === 'win32' && /\s/.test(exe) ? '& ' + linha : linha;
}

function terminal() {
  let t = vscode.window.terminals.find((x) => x.name === 'GALO');
  if (!t) {
    t = vscode.window.createTerminal('GALO');
  }
  t.show(true);
  return t;
}

async function rodarNoTerminal(montar) {
  const doc = arquivoAtual();
  if (!doc) {
    return;
  }
  if (doc.isDirty) {
    await doc.save();
  }
  const caminho = doc.uri.fsPath;
  const t = terminal();
  for (const args of montar(caminho)) {
    t.sendText(linhaDeComando(args));
  }
}

function escopoDe(arquivo, escopo) {
  // Tarefas precisam pertencer a uma pasta do projeto para que ${workspaceFolder} (usado pelo
  // problem matcher) possa ser resolvido.
  if (escopo && typeof escopo === 'object') return escopo;
  const pastaDoArquivo = path.isAbsolute(arquivo) ? vscode.workspace.getWorkspaceFolder(vscode.Uri.file(arquivo)) : undefined;
  const pastas = vscode.workspace.workspaceFolders || [];
  return pastaDoArquivo || pastas[0] || vscode.TaskScope.Workspace;
}

function criarTarefa(definicao, arquivo, escopo) {
  const nome = definicao.comando + ' ' + path.basename(arquivo);
  const exe = executavel();
  const execucao = new vscode.ShellExecution(exe, ['--formato-curto', definicao.comando, arquivo]);
  return new vscode.Task(definicao, escopoDe(arquivo, escopo), nome, 'galo', execucao, ['$galo', '$galo-aviso']);
}

function provedorDeTarefas() {
  return {
    provideTasks() {
      const editor = vscode.window.activeTextEditor;
      if (!editor || editor.document.languageId !== 'galo') {
        return [];
      }
      const arquivo = editor.document.uri.fsPath;
      return ['executar', 'compilar', 'verificar'].map((c) => criarTarefa({ type: 'galo', comando: c }, arquivo));
    },
    resolveTask(tarefa) {
      const def = tarefa.definition;
      let arquivo = def.arquivo;
      if (!arquivo && vscode.window.activeTextEditor) {
        arquivo = vscode.window.activeTextEditor.document.uri.fsPath;
      }
      return arquivo ? criarTarefa(def, arquivo, tarefa.scope) : undefined;
    }
  };
}

// ------------------------------------------------------------------ provedores do editor

function paraItemDeCompletar(i) {
  // Os tipos do LSP começam em 1; os do VS Code, em 0.
  const tipo = typeof i.kind === 'number' ? i.kind - 1 : vscode.CompletionItemKind.Text;
  const item = new vscode.CompletionItem(i.label, tipo);
  if (i.detail) {
    item.detail = i.detail;
  }
  if (i.documentation) {
    item.documentation = new vscode.MarkdownString(
      typeof i.documentation === 'string' ? i.documentation : i.documentation.value
    );
  }
  if (i.insertText) {
    item.insertText = i.insertTextFormat === 2 ? new vscode.SnippetString(i.insertText) : i.insertText;
  }
  return item;
}

function provedorDeCompletar() {
  return {
    provideCompletionItems(doc, posicao) {
      if (!pronto) {
        return [];
      }
      return pedir('textDocument/completion', {
        textDocument: { uri: doc.uri.toString() },
        position: { line: posicao.line, character: posicao.character }
      }).then((r) => {
        const itens = r ? (Array.isArray(r) ? r : r.items || []) : [];
        return itens.map(paraItemDeCompletar);
      }, () => []);
    }
  };
}

function provedorDeHover() {
  return {
    provideHover(doc, posicao) {
      if (!pronto) {
        return null;
      }
      return pedir('textDocument/hover', {
        textDocument: { uri: doc.uri.toString() },
        position: { line: posicao.line, character: posicao.character }
      }).then((r) => {
        if (!r || !r.contents) {
          return null;
        }
        const valor = typeof r.contents === 'string' ? r.contents : r.contents.value;
        return new vscode.Hover(new vscode.MarkdownString(valor));
      }, () => null);
    }
  };
}

// ------------------------------------------------------------------ ativação

function activate(context) {
  saida = vscode.window.createOutputChannel('GALO');
  // Nome diferente do dono dos problem matchers ('galo'): o editor limpa os marcadores de um dono
  // quando uma tarefa começa, e os diagnósticos do servidor de linguagem não podem sumir junto.
  diagnosticos = vscode.languages.createDiagnosticCollection('galo-lsp');
  context.subscriptions.push(saida, diagnosticos);

  context.subscriptions.push(
    vscode.commands.registerCommand('galo.executar', () => rodarNoTerminal((f) => [['executar', f]])),
    vscode.commands.registerCommand('galo.compilar', () => rodarNoTerminal((f) => [['compilar', f]])),
    vscode.commands.registerCommand('galo.rodarCompilado', () => rodarNoTerminal((f) => {
      const compilado = f.replace(/\.galo$/i, '') + '.galoc';
      return [['compilar', f], ['rodar', compilado]];
    })),
    vscode.commands.registerCommand('galo.verificar', () => rodarNoTerminal((f) => [['verificar', f]])),
    vscode.commands.registerCommand('galo.abrirRepl', () => terminal().sendText(linhaDeComando(['repl']))),
    vscode.commands.registerCommand('galo.reiniciarServidor', () => pararServidor().then(iniciarServidor)),
    vscode.tasks.registerTaskProvider('galo', provedorDeTarefas()),
    vscode.languages.registerCompletionItemProvider('galo', provedorDeCompletar(), '.'),
    vscode.languages.registerHoverProvider('galo', provedorDeHover()),
    vscode.workspace.onDidOpenTextDocument(abrirDocumento),
    vscode.workspace.onDidChangeTextDocument(alterarDocumento),
    vscode.workspace.onDidCloseTextDocument(fecharDocumento),
    vscode.workspace.onDidChangeConfiguration((e) => {
      if (e.affectsConfiguration('galo')) {
        pararServidor().then(iniciarServidor);
      }
    })
  );

  iniciarServidor();
}

function deactivate() {
  return pararServidor();
}

module.exports = { activate, deactivate };
