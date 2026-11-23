/*
 * galo.js — máquina virtual da GALO para o navegador.
 *
 * Executa programas compilados (.galoc, formato v2) produzidos por `galo compilar`
 * ou entregues por `app.cliente(...)` no servidor GALO. Implementa a mesma semântica
 * da VM em Python: inteiros de precisão arbitrária (BigInt), decimais IEEE 754,
 * posições a partir de 1, booleanos que não são números, closures, registros,
 * módulos, tratamento de erros com códigos G3xx e a biblioteca padrão (exceto
 * funções de servidor), mais funções para a página: elemento(), buscar(), depois()...
 *
 * Uso:
 *   <script src="/_galo/galo.js"></script>
 *   <script type="application/galo" src="/app.galoc"></script>
 * ou, em JavaScript:  Galo.executar("/app.galoc")
 */
(function (global) {
  'use strict';

  const VERSAO = '0.2.0';
  const VERSAO_BYTECODE = 2;
  const MAX_POW_BITS = 1 << 26;

  // ------------------------------------------------------------------ instruções
  // Mesma numeração de galo/compiler/bytecode.py (conferida por tests/test_navegador.py).
  const OP = {
    NOP: 0, CONST: 1, POP: 2, DUP: 3, LOAD_LOCAL: 4, STORE_LOCAL: 5, LOAD_CELL: 6, STORE_CELL: 7,
    MAKE_CELL: 8, BOX_LOCAL: 9, LOAD_FREE: 10, STORE_FREE: 11, LOAD_GLOBAL: 12, STORE_GLOBAL: 13,
    DEFINE_GLOBAL: 14, ADD: 15, SUB: 16, MUL: 17, DIV: 18, IDIV: 19, MOD: 20, POW: 21, NEG: 22, POS: 23,
    NOT: 24, EQ: 25, NE: 26, LT: 27, LE: 28, GT: 29, GE: 30, IN: 31, JUMP: 32, JUMP_IF_FALSE: 33,
    JUMP_IF_FALSE_KEEP: 34, JUMP_IF_TRUE_KEEP: 35, CHECK_BOOL: 36, BUILD_LIST: 37, BUILD_MAP: 38,
    BUILD_STRING: 39, INDEX: 40, STORE_INDEX: 41, GET_FIELD: 42, SET_FIELD: 43, CALL: 44, RETURN: 45,
    MAKE_FUNCTION: 46, PRINT: 47, PRINT_REPL: 48, ITER_PREPARE: 49, RANGE_PREPARE: 50, REPEAT_PREPARE: 51,
    FOR_ITER: 52, FOR_ITER2: 53, SETUP_TRY: 54, POP_TRY: 55, RAISE: 56, CHECK_TYPE: 57, IMPORT_MODULE: 58,
    MAKE_RECORD_TYPE: 59, NEW_RECORD: 60, CALL_KW: 61, ARG_MISSING: 62,
  };

  // ------------------------------------------------------------------ erros

  class GaloErro extends Error {
    constructor(codigo, mensagem, sugestao) {
      super(mensagem);
      this.codigo = codigo;
      this.mensagem = mensagem;
      this.sugestao = sugestao || null;
      this.linha = null;
      this.coluna = null;
      this.arquivo = null;
      this.rastro = null;
      this.valor = undefined;
    }
  }

  class GaloSaida extends Error {
    constructor(codigo) { super('sair'); this.codigo = codigo; }
  }

  function erro(codigo, mensagem, sugestao) { return new GaloErro(codigo, mensagem, sugestao); }

  function formatarErro(e) {
    const linhas = [`Erro GALO [${e.codigo}] — erro de execução`];
    if (e.arquivo) linhas.push(`Arquivo: ${e.arquivo}`);
    if (e.linha != null) linhas.push(`Linha: ${e.linha}, coluna: ${e.coluna || 1}`);
    linhas.push('', e.mensagem);
    if (e.sugestao) linhas.push('', 'Sugestão:', e.sugestao);
    if (e.rastro && e.rastro.length > 1) {
      linhas.push('', 'Rastro de chamadas (a mais recente por último):');
      const mostrar = e.rastro.length > 16 ? e.rastro.slice(0, 6).concat([null], e.rastro.slice(-10)) : e.rastro;
      for (const r of mostrar) {
        if (r === null) { linhas.push(`  ... ${e.rastro.length - 16} chamadas omitidas ...`); continue; }
        const onde = r[0] === '<programa>' ? 'programa principal' : (r[0].startsWith('<módulo') ? r[0].slice(1, -1) : `função ${r[0]}`);
        linhas.push(r[1] ? `  ${onde}, linha ${r[1]}` : `  ${onde}`);
      }
    }
    return linhas.join('\n');
  }

  // ------------------------------------------------------------------ valores

  const UNSET = { toString() { return '<sem valor>'; } };
  const MISSING = { toString() { return '<ausente>'; } };

  function canonical(s) { return s.normalize('NFD').replace(/\p{Mn}/gu, '').normalize('NFC'); }

  class Cell { constructor(v) { this.value = v === undefined ? UNSET : v; } }

  class Closure {
    constructor(code, cells, globals) { this.code = code; this.cells = cells; this.globals = globals; this.name = code.name; }
  }

  class Native {
    constructor(name, fn, min, max, doc) {
      this.name = name; this.key = canonical(name); this.fn = fn; this.min = min; this.max = max; this.doc = doc || '';
    }
  }

  class MetodoLigado { constructor(receptor, funcao) { this.receptor = receptor; this.funcao = funcao; } }

  class TipoRegistro {
    constructor(name, fields, specs, ctor, methods) {
      this.name = name; this.fields = fields; this.specs = specs; this.ctor = ctor; this.methods = methods;
      this.index = new Map(fields.map((f, i) => [canonical(f), i]));
    }
  }

  class Registro { constructor(tipo, valores) { this.tipo = tipo; this.valores = valores; } }

  class Modulo {
    constructor(name, exports) {
      this.name = name; this.globals = new Map(); this.exports = new Map(exports.map((e) => [canonical(e), e]));
    }
  }

  class ObjetoNativo {
    constructor(tipo, dados) {
      this.tipo = tipo; this.dados = dados; this.metodos = new Map(); this.props = new Map(); this.setters = new Map();
    }
    metodo(nome, fn, min, max) {
      const alvo = this;
      this.metodos.set(canonical(nome), new Native(`${this.tipo}.${nome}`, (vm, args) => fn(vm, alvo, args), min, max));
    }
    propriedade(nome, get, set) {
      this.props.set(canonical(nome), get);
      if (set) this.setters.set(canonical(nome), set);
    }
  }

  class Mapa {
    constructor() { this.d = new Map(); }
    static norm(k) {
      switch (typeof k) {
        case 'string': return 's' + k;
        case 'bigint': return 'i' + k.toString();
        case 'number': return Number.isInteger(k) ? 'i' + BigInt(k).toString() : 'f' + fmtDecimal(k);
        case 'boolean': return 'b' + k;
      }
      if (k === null) return 'n';
      throw erro('G321', `${capitalizar(artigo(typeName(k)))} não pode ser usado como chave de mapa.`,
        'Use textos, números, booleanos ou nulo como chaves.');
    }
    get(k, padrao = MISSING) { const e = this.d.get(Mapa.norm(k)); return e === undefined ? padrao : e[1]; }
    set(k, v) { const n = Mapa.norm(k); const e = this.d.get(n); if (e) e[1] = v; else this.d.set(n, [k, v]); }
    has(k) { try { return this.d.has(Mapa.norm(k)); } catch (e) { return false; } }
    delete(k) { const n = Mapa.norm(k); const e = this.d.get(n); if (!e) return MISSING; this.d.delete(n); return e[1]; }
    keys() { return Array.from(this.d.values(), (e) => e[0]); }
    values() { return Array.from(this.d.values(), (e) => e[1]); }
    items() { return Array.from(this.d.values(), (e) => [e[0], e[1]]); }
    get size() { return this.d.size; }
    clear() { this.d.clear(); }
    copy() { const m = new Mapa(); for (const [n, e] of this.d) m.d.set(n, [e[0], e[1]]); return m; }
    findField(name) {
      if (this.d.has('s' + name)) return name;
      const c = canonical(name);
      for (const e of this.d.values()) if (typeof e[0] === 'string' && canonical(e[0]) === c) return e[0];
      return MISSING;
    }
    static de(pares) { const m = new Mapa(); for (const [k, v] of pares) m.set(k, v); return m; }
  }

  function typeName(v) {
    switch (typeof v) {
      case 'bigint': return 'inteiro';
      case 'number': return 'decimal';
      case 'string': return 'texto';
      case 'boolean': return 'booleano';
    }
    if (v === null) return 'nulo';
    if (Array.isArray(v)) return 'lista';
    if (v instanceof Mapa) return 'mapa';
    if (v instanceof Closure || v instanceof Native || v instanceof MetodoLigado) return 'função';
    if (v instanceof Registro) return v.tipo.name;
    if (v instanceof TipoRegistro) return 'tipo';
    if (v instanceof Modulo) return 'módulo';
    if (v instanceof ObjetoNativo) return v.tipo;
    return 'interno';
  }

  const ARTIGOS = {
    inteiro: 'um inteiro', decimal: 'um decimal', texto: 'um texto', booleano: 'um booleano', lista: 'uma lista',
    mapa: 'um mapa', nulo: 'nulo', 'função': 'uma função', 'número': 'um número', tipo: 'um tipo de registro',
    'módulo': 'um módulo',
  };
  function artigo(t) { return ARTIGOS[t] || `um valor do tipo ${t}`; }
  function capitalizar(s) { return s.charAt(0).toUpperCase() + s.slice(1); }
  function agruparNumero(nomes) {
    nomes = Array.from(nomes);
    if (nomes.includes('inteiro') && nomes.includes('decimal')) {
      nomes = ['número'].concat(nomes.filter((n) => n !== 'inteiro' && n !== 'decimal'));
    }
    return nomes;
  }
  function descreverTipos(nomes) {
    const partes = agruparNumero(nomes).map(artigo);
    if (partes.length <= 1) return partes[0] || 'nada';
    return partes.slice(0, -1).join(', ') + ' ou ' + partes[partes.length - 1];
  }
  function descreverSpec(nomes) { return agruparNumero(nomes).join(' ou '); }

  function coerce(v, spec) {
    const tn = typeName(v);
    if (spec.includes(tn)) return v;
    if (tn === 'inteiro' && spec.includes('decimal')) return Number(v);
    return MISSING;
  }

  function isNum(v) { const t = typeof v; return t === 'bigint' || t === 'number'; }

  // ------------------------------------------------------------------ exibição

  function fmtDecimal(x) {
    if (Number.isNaN(x)) return 'NaN';
    if (x === Infinity) return 'infinito';
    if (x === -Infinity) return '-infinito';
    if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
    const [mant, expTxt] = x.toExponential().split('e');
    const exp = parseInt(expTxt, 10);
    const neg = x < 0;
    const digits = mant.replace('-', '').replace('.', '');
    let s;
    if (exp >= -4 && exp < 16) {
      if (exp >= 0) {
        if (digits.length <= exp + 1) s = digits + '0'.repeat(exp + 1 - digits.length) + '.0';
        else s = digits.slice(0, exp + 1) + '.' + digits.slice(exp + 1);
      } else {
        s = '0.' + '0'.repeat(-exp - 1) + digits;
      }
    } else {
      const m = digits[0] + (digits.length > 1 ? '.' + digits.slice(1) : '');
      s = m + 'e' + (exp < 0 ? '-' : '+') + String(Math.abs(exp)).padStart(2, '0');
    }
    return (neg ? '-' : '') + s;
  }

  function quote(s) {
    return '"' + s.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, '\\n').replace(/\t/g, '\\t')
      .replace(/\{/g, '\\{') + '"';
  }

  function display(v) { return typeof v === 'string' ? v : repr(v); }

  function repr(v, vistos) {
    switch (typeof v) {
      case 'boolean': return v ? 'verdadeiro' : 'falso';
      case 'bigint': return v.toString();
      case 'string': return quote(v);
      case 'number': return fmtDecimal(v);
    }
    if (v === null) return 'nulo';
    if (Array.isArray(v) || v instanceof Mapa || v instanceof Registro) {
      vistos = vistos || new Set();
      if (vistos.has(v)) return Array.isArray(v) ? '[...]' : (v instanceof Mapa ? '{...}' : v.tipo.name + '(...)');
      vistos.add(v);
      try {
        if (Array.isArray(v)) return '[' + v.map((x) => repr(x, vistos)).join(', ') + ']';
        if (v instanceof Mapa) return '{' + v.items().map(([k, x]) => repr(k, vistos) + ': ' + repr(x, vistos)).join(', ') + '}';
        return v.tipo.name + '(' + v.tipo.fields.map((f, i) => f + ': ' + repr(v.valores[i], vistos)).join(', ') + ')';
      } finally { vistos.delete(v); }
    }
    if (v instanceof Closure) return `<função ${v.name}>`;
    if (v instanceof Native) return `<função interna ${v.name}>`;
    if (v instanceof MetodoLigado) return `<método ${v.funcao.name}>`;
    if (v instanceof TipoRegistro) return `<registro ${v.name}>`;
    if (v instanceof Modulo) return `<módulo ${v.name}>`;
    if (v instanceof ObjetoNativo) return `<${v.tipo}>`;
    return '<valor interno>';
  }

  // ------------------------------------------------------------------ igualdade e operações

  function equals(a, b, vistos) {
    const ta = typeof a, tb = typeof b;
    if ((ta === 'bigint' || ta === 'number') && (tb === 'bigint' || tb === 'number')) return a == b; // eslint-disable-line eqeqeq
    if (ta !== tb) return false;
    if (ta !== 'object' || a === null || b === null) return a === b;
    if (a === b) return true;
    if (Array.isArray(a)) {
      if (!Array.isArray(b) || a.length !== b.length) return false;
      vistos = vistos || new Set();
      const par = a; if (vistos.has(par)) return true; vistos.add(par);
      for (let i = 0; i < a.length; i++) if (!equals(a[i], b[i], vistos)) return false;
      return true;
    }
    if (a instanceof Mapa) {
      if (!(b instanceof Mapa) || a.size !== b.size) return false;
      vistos = vistos || new Set();
      if (vistos.has(a)) return true; vistos.add(a);
      for (const [k, v] of a.items()) { const o = b.get(k); if (o === MISSING || !equals(v, o, vistos)) return false; }
      return true;
    }
    if (a instanceof Registro) {
      if (!(b instanceof Registro) || a.tipo !== b.tipo) return false;
      for (let i = 0; i < a.valores.length; i++) if (!equals(a.valores[i], b.valores[i], vistos)) return false;
      return true;
    }
    if (a instanceof MetodoLigado) return b instanceof MetodoLigado && a.receptor === b.receptor && a.funcao === b.funcao;
    return false;
  }

  const VERBOS = { '+': 'somar', '-': 'subtrair', '*': 'multiplicar', '/': 'dividir', '//': 'fazer a divisão inteira entre',
    '%': 'calcular o resto entre', '^': 'calcular a potência entre' };

  function erroBinario(op, a, b) {
    const ta = typeName(a), tb = typeName(b);
    let sug = null;
    const nums = ['inteiro', 'decimal'];
    if (op === '+' && ((ta === 'texto' && nums.includes(tb)) || (tb === 'texto' && nums.includes(ta)))) {
      sug = 'Para juntar texto e número, use interpolação: "Total: {valor}" ou converta com texto(valor).';
    } else if ((ta === 'texto' || tb === 'texto') && (nums.includes(ta) || nums.includes(tb))) {
      sug = 'Se o texto contém um número, converta-o antes: número(texto).';
    } else if (ta === 'nulo' || tb === 'nulo') {
      sug = 'Um dos valores é nulo. Verifique se a variável recebeu um valor antes desta operação.';
    } else if (ta === 'booleano' || tb === 'booleano') {
      sug = 'Booleanos (verdadeiro/falso) não são números em GALO.';
    }
    return erro('G302', `Não é possível ${VERBOS[op]} ${artigo(ta)} e ${artigo(tb)} (operador '${op}').`, sug);
  }
  function divisaoPorZero() {
    return erro('G303', 'Divisão por zero.', 'Verifique se o divisor é diferente de zero antes de dividir.');
  }
  function finito(r) {
    if (!Number.isFinite(r) && !Number.isNaN(r)) throw erro('G317', 'Número grande demais para ser representado.',
      'Decimais (ponto flutuante) têm limite de aproximadamente 1.8e308.');
    return r;
  }
  // Resultado infinito a partir de operandos finitos é estouro (G317); com operandos já
  // infinitos, vale o IEEE 754 (como na VM Python).
  const ehInfinito = (v) => typeof v === 'number' && (v === Infinity || v === -Infinity);
  function semEstouro(r, a, b) { return ehInfinito(a) || ehInfinito(b) ? r : finito(r); }

  // Divisão inteira e resto de decimais exatamente como o Python (float_divmod do CPython):
  // o piso é aplicado ao quociente exato, não ao quociente já arredondado.
  function divmodDecimal(vx, wx) {
    let mod = vx % wx;
    let div = (vx - mod) / wx;
    if (mod) {
      if ((wx < 0) !== (mod < 0)) { mod += wx; div -= 1.0; }
    } else {
      mod = wx < 0 ? -0 : 0;
    }
    let piso;
    if (div) {
      piso = Math.floor(div);
      if (div - piso > 0.5) piso += 1.0;
    } else {
      piso = (vx / wx) < 0 || Object.is(vx / wx, -0) ? -0 : 0;
    }
    return [piso, mod];
  }

  function opAdd(a, b) {
    const ta = typeof a, tb = typeof b;
    if (ta === 'bigint' && tb === 'bigint') return a + b;
    if (isNum(a) && isNum(b)) return semEstouro(Number(a) + Number(b), a, b);
    if (ta === 'string' && tb === 'string') return a + b;
    if (Array.isArray(a) && Array.isArray(b)) return a.concat(b);
    throw erroBinario('+', a, b);
  }
  function opSub(a, b) {
    if (typeof a === 'bigint' && typeof b === 'bigint') return a - b;
    if (isNum(a) && isNum(b)) return semEstouro(Number(a) - Number(b), a, b);
    throw erroBinario('-', a, b);
  }
  function opMul(a, b) {
    const ta = typeof a, tb = typeof b;
    if (ta === 'bigint' && tb === 'bigint') return a * b;
    if (isNum(a) && isNum(b)) return semEstouro(Number(a) * Number(b), a, b);
    if (ta === 'string' && tb === 'bigint') return b > 0n ? a.repeat(Number(b)) : '';
    if (ta === 'bigint' && tb === 'string') return a > 0n ? b.repeat(Number(a)) : '';
    throw erroBinario('*', a, b);
  }
  // ---- aritmética exata: divisões de inteiros e potências com expoente inteiro são calculadas
  // com racionais exatos (BigInt) e arredondadas UMA vez, exatamente como na VM Python.

  const LIMITE_EXATO = 2n ** 53n;

  // p / q (p, q > 0) arredondado para o decimal (IEEE 754) mais próximo, empates para o par.
  function racionalParaNumero(p, q) {
    let e = bitLength(p) - bitLength(q); // 2^e <= p/q < 2^(e+1), após o ajuste abaixo
    if (e >= 0 ? p < (q << BigInt(e)) : (p << BigInt(-e)) < q) e -= 1;
    if (e > 1023) return Infinity;
    if (e < -1075) return 0;
    if (e === -1075) return (p << 1075n) === q ? 0 : Number.MIN_VALUE;
    const bits = e < -1022 ? 53 - (-1022 - e) : 53;
    const s = bits - 1 - e;
    let num = p, den = q;
    if (s >= 0) num = p << BigInt(s); else den = q << BigInt(-s);
    let m = num / den;
    const dobro = 2n * (num % den);
    if (dobro > den || (dobro === den && (m & 1n))) m += 1n;
    let x = Number(m);
    let falta = s;
    while (falta > 1000) { x /= 2 ** 1000; falta -= 1000; }
    while (falta < -1000) { x *= 2 ** 1000; falta += 1000; }
    return x / 2 ** falta;
  }

  function dividirInteiros(a, b) {
    if (a >= -LIMITE_EXATO && a <= LIMITE_EXATO && b >= -LIMITE_EXATO && b <= LIMITE_EXATO) return Number(a) / Number(b);
    const negativo = (a < 0n) !== (b < 0n);
    if (a === 0n) return negativo ? -0 : 0;
    const x = racionalParaNumero(a < 0n ? -a : a, b < 0n ? -b : b);
    return negativo ? -x : x;
  }

  // |x| = m * 2^e (x decimal finito, diferente de zero)
  function decompor(x) {
    const dv = new DataView(new ArrayBuffer(8));
    dv.setFloat64(0, Math.abs(x));
    const alto = dv.getUint32(0), baixo = dv.getUint32(4);
    const expoente = (alto >>> 20) & 0x7ff;
    let m = (BigInt(alto & 0xfffff) << 32n) | BigInt(baixo);
    if (expoente === 0) return [m, -1074];
    return [m | (1n << 52n), expoente - 1075];
  }

  function potenciaInteiraExata(a, n) {
    if (n === 0) return 1;
    let m, e2, e;
    if (typeof a === 'number') {
      if (!Number.isFinite(a) || a === 0) return Math.pow(a, n);
      if (n === 1) return a;
      if (n === 2) return semEstouro(a * a, a, a);
      if (n === -1) return 1 / a;
      [m, e2] = decompor(a);
      e = frexpExpoente(a);
    } else {
      if (n === -1) return dividirInteiros(1n, a);
      m = a < 0n ? -a : a; e2 = 0; e = bitLength(a);
    }
    const menor = Math.min((e - 1) * n, e * n), maior = Math.max((e - 1) * n, e * n);
    if (menor > 1025) throw erro('G317', 'Número grande demais para ser representado.',
      'Decimais (ponto flutuante) têm limite de aproximadamente 1.8e308.');
    const negativo = (typeof a === 'number' ? a < 0 : a < 0n) && Math.abs(n) % 2 === 1;
    if (maior < -1076) return negativo ? -0 : 0;
    const k = Math.abs(n);
    const mk = m ** BigInt(k);
    const ek = e2 * k; // expoente de 2 de |a|^k
    let p, q;
    if (n > 0) { p = mk; q = 1n; if (ek >= 0) p <<= BigInt(ek); else q <<= BigInt(-ek); }
    else { p = 1n; q = mk; if (ek >= 0) q <<= BigInt(ek); else p <<= BigInt(-ek); }
    const x = finito(racionalParaNumero(p, q));
    return negativo ? -x : x;
  }

  // Expoente e de frexp: |x| = f * 2^e com 0.5 <= f < 1
  function frexpExpoente(x) {
    const [m, e2] = decompor(x);
    return e2 + bitLength(m);
  }

  // ---- funções matemáticas com arredondamento correto: os mesmos passos de
  // galo/runtime/matematica_exata.py, com BigInt. Cada cálculo dá um intervalo que contém o
  // valor exato; se as duas pontas arredondam para o mesmo decimal, ele é o resultado. Senão,
  // refaz com o dobro da precisão. Toda divisão usa operandos não negativos (BigInt trunca e
  // o Python arredonda para baixo: com operandos não negativos as duas coisas coincidem).

  const PRECISOES = [96, 192, 384, 768, 1536, 3072, 6144];
  const cachePi = new Map(), cacheLn2 = new Map();
  const absBig = (v) => (v < 0n ? -v : v);

  function atanInverso(n, p) {
    let x = (1n << BigInt(p)) / n, total = 0n, k = 1n, positivo = true;
    const n2 = n * n;
    while (x) { total = positivo ? total + x / k : total - x / k; x /= n2; k += 2n; positivo = !positivo; }
    return total;
  }
  function atanhInverso(n, p) {
    let x = (1n << BigInt(p)) / n, total = 0n, k = 1n;
    const n2 = n * n;
    while (x) { total += x / k; x /= n2; k += 2n; }
    return total;
  }
  function piFixo(p) {
    let v = cachePi.get(p);
    if (v === undefined) {
      const g = p + 24;
      v = (16n * atanInverso(5n, g) - 4n * atanInverso(239n, g)) >> 24n;
      cachePi.set(p, v);
    }
    return v;
  }
  function ln2Fixo(p) {
    let v = cacheLn2.get(p);
    if (v === undefined) {
      v = (2n * atanhInverso(3n, p + 24)) >> 24n;
      cacheLn2.set(p, v);
    }
    return v;
  }
  function racional(num, den) {
    if (num === 0n) return 0;
    return num < 0n ? -racionalParaNumero(-num, den) : racionalParaNumero(num, den);
  }
  function unico(candidatos) {
    let v = null;
    for (const [n, d] of candidatos) {
      const r = racional(n, d);
      if (v === null) v = r; else if (r !== v) return null;
    }
    return v;
  }
  function valoresOrdenados(candidatos) {
    const vals = [];
    for (const [n, d] of candidatos) { const r = racional(n, d); if (!vals.some((v) => v === r)) vals.push(r); }
    return vals.sort((a, b) => a - b);
  }
  // |x| = m / 2^d, com d >= 0
  function decomporRacional(x) {
    const [m, e] = decompor(x);
    return e >= 0 ? [m << BigInt(e), 0] : [m, -e];
  }
  // |x| = m · 2^e com m ímpar (x diferente de zero)
  function decomporImpar(x) {
    let [m, e] = decompor(x);
    while (!(m & 1n)) { m >>= 1n; e += 1; }
    return [m, e];
  }
  // v = n / 2^q com q <= 8 e |n| < 4096? Devolve [n, q] ou null.
  function diadico(v) {
    if (v === 0) return [0, 0];
    const [m, e] = decomporImpar(v);
    if (e < -8) return null;
    if (e >= 0 && bitLength(m) + e > 13) return null;
    const n = e >= 0 ? Number(m << BigInt(e)) : Number(m);
    if (n >= 4096) return null;
    return [v < 0 ? -n : n, e >= 0 ? 0 : -e];
  }
  // a^ka === b^kb, exatamente (a, b > 0 finitos; ka, kb inteiros)
  function potenciasIguais(a, ka, b, kb) {
    const potencia = (x, k) => {
      const [m, e] = decomporImpar(x);
      const mk = m ** BigInt(Math.abs(k));
      return k >= 0 ? [mk, 1n, e * k] : [1n, mk, e * k];
    };
    const [n1, d1, e1] = potencia(a, ka), [n2, d2, e2] = potencia(b, kb);
    return e1 === e2 && n1 * d2 === n2 * d1;
  }

  function senoCossenoReduzidos(r, p) {
    const P = BigInt(p);
    const r2 = (r * r) >> P;
    let termos = 0n;
    let s = 0n, termo = r, n = 1n, positivo = true;
    while (termo) {
      s = positivo ? s + termo : s - termo;
      termo = ((termo * r2) >> P) / ((n + 1n) * (n + 2n)); n += 2n; positivo = !positivo; termos += 1n;
    }
    let c = 0n; termo = 1n << P; n = 0n; positivo = true;
    while (termo) {
      c = positivo ? c + termo : c - termo;
      termo = ((termo * r2) >> P) / ((n + 1n) * (n + 2n)); n += 2n; positivo = !positivo; termos += 1n;
    }
    return [s, c, termos];
  }
  function trigonometricas(x, p) {
    const [m, d] = decomporRacional(x);
    const q = p + Math.max(0, bitLength(m) - d) + 16;
    const xq = q >= d ? (m << BigInt(q)) >> BigInt(d) : m >> BigInt(d - q);
    const meioPi = piFixo(q) >> 1n;
    const k = (2n * xq + meioPi) / (2n * meioPi);
    const resto = xq - k * meioPi;
    const desloc = BigInt(q - p);
    const r = absBig(resto) >> desloc;
    const erroR = ((3n * k + 4n) >> desloc) + 2n;
    let [s, c, termos] = senoCossenoReduzidos(r, p);
    if (resto < 0n) s = -s;
    const quadrante = Number(k % 4n);
    return [[s, c, -s, -c][quadrante], [c, -s, -c, s][quadrante], erroR + 3n * termos + 8n];
  }
  function senoExato(x) {
    if (x === 0) return x;
    let s, um;
    for (const p of PRECISOES) {
      let e;
      [s, , e] = trigonometricas(x, p);
      if (x < 0) s = -s;
      um = 1n << BigInt(p);
      const v = unico([[s - e, um], [s + e, um]]);
      if (v !== null) return v;
    }
    return racional(s, um);
  }
  function cossenoExato(x) {
    if (x === 0) return 1;
    let c, um;
    for (const p of PRECISOES) {
      let e;
      [, c, e] = trigonometricas(x, p);
      um = 1n << BigInt(p);
      const v = unico([[c - e, um], [c + e, um]]);
      if (v !== null) return v;
    }
    return racional(c, um);
  }
  function tangenteExata(x) {
    if (x === 0) return x;
    let s, c;
    for (const p of PRECISOES) {
      let e;
      [s, c, e] = trigonometricas(x, p);
      if (x < 0) s = -s;
      if (absBig(c) <= e) continue;
      const cand = [];
      for (const sn of [s - e, s + e]) for (const cd of [c - e, c + e]) cand.push(cd < 0n ? [-sn, -cd] : [sn, cd]);
      const v = unico(cand);
      if (v !== null) return v;
    }
    return c > 0n ? racional(s, c) : racional(-s, -c);
  }

  function lnFixo(x, p) {
    const P = BigInt(p);
    const [m, d] = decomporRacional(x);
    let k = bitLength(m) - 1 - d; // x = 2^k · f, com f em [1, 2)
    let num = m, den = 1n << BigInt(d);
    if (k >= 0) den <<= BigInt(k); else num <<= BigInt(-k);
    if (num * num >= 2n * den * den) { k += 1; den <<= 1n; } // f >= √2: usa f/2
    const negativo = num < den;
    const t = (absBig(num - den) << P) / (num + den);
    const t2 = (t * t) >> P;
    let soma = 0n, termo = t, j = 1n, termos = 0;
    while (termo) { soma += termo / j; termo = (termo * t2) >> P; j += 2n; termos += 1; }
    const lnF = negativo ? -2n * soma : 2n * soma;
    const ln2 = ln2Fixo(p);
    const valor = k >= 0 ? BigInt(k) * ln2 + lnF : lnF - BigInt(-k) * ln2;
    return [valor, BigInt(2 * termos + 2 * Math.abs(k) + 8)];
  }
  function logaritmoExato(x) {
    if (x === 1) return 0;
    let v, um;
    for (const p of PRECISOES) {
      let e;
      [v, e] = lnFixo(x, p);
      um = 1n << BigInt(p);
      const r = unico([[v - e, um], [v + e, um]]);
      if (r !== null) return r;
    }
    return racional(v, um);
  }
  function logaritmoBaseExato(x, b) {
    if (x === 1) return 0;
    let vx, ex, vb, eb;
    for (const p of PRECISOES) {
      [vx, ex] = lnFixo(x, p);
      [vb, eb] = lnFixo(b, p);
      if (absBig(vb) <= eb) continue;
      const cand = [];
      for (const a of [vx - ex, vx + ex]) for (const c of [vb - eb, vb + eb]) cand.push(c < 0n ? [-a, -c] : [a, c]);
      const r = unico(cand);
      if (r !== null) return r;
      if (p >= 192) {
        for (const v of valoresOrdenados(cand)) {
          const dd = diadico(v);
          if (dd !== null && potenciasIguais(b, dd[0], x, 2 ** dd[1])) return v; // b^(n/2^q) == x
        }
      }
    }
    return vb > 0n ? racional(vx, vb) : racional(-vx, -vb);
  }

  function expFixo(z, ez, p) {
    const P = BigInt(p);
    const ln2 = ln2Fixo(p);
    const n = z >= 0n ? (2n * z + ln2) / (2n * ln2) : -((2n * (-z) + ln2) / (2n * ln2));
    const r = n >= 0n ? z - n * ln2 : z + (-n) * ln2;
    const er = ez + 2n * absBig(n) + 2n;
    const negativo = r < 0n, ra = absBig(r);
    let s = 0n, termo = 1n << P, i = 0n, termos = 0n, positivo = true;
    while (termo) {
      s = positivo || !negativo ? s + termo : s - termo;
      i += 1n;
      termo = ((termo * ra) >> P) / i;
      if (negativo) positivo = !positivo;
      termos += 1n;
    }
    return [s, 2n * er + 2n * termos + 4n, n];
  }
  // x ^ y para x > 0 finito e y finito, arredondado corretamente
  function potenciaExata(x, y) {
    if (x === 1 || y === 0) return 1;
    const [my, ey] = decomporImpar(y);
    const py = ey >= 0 ? my << BigInt(ey) : my, qy = ey >= 0 ? 1n : 1n << BigInt(-ey);
    let cand;
    for (const p of PRECISOES) {
      const P = BigInt(p);
      const [lx, ex] = lnFixo(x, p);
      let z = (absBig(lx) * py) / qy;
      if ((lx < 0n) !== (y < 0)) z = -z;
      const ez = (ex * py) / qy + 2n;
      if (z > (1100n << P)) throw erro('G317', 'Número grande demais para ser representado.',
        'Decimais (ponto flutuante) têm limite de aproximadamente 1.8e308.');
      if (z < -(1200n << P)) return 0;
      const [s, es, n] = expFixo(z, ez, p);
      cand = n >= 0n ? [[(s - es) << n, 1n << P], [(s + es) << n, 1n << P]]
        : [[s - es, 1n << (P - n)], [s + es, 1n << (P - n)]];
      const r = unico(cand);
      if (r !== null) return r;
      if (p >= 192) {
        const dd = diadico(y);
        if (dd !== null) { // candidato v é exato se v^(2^q) == x^n
          for (const v of valoresOrdenados(cand)) {
            if (v > 0 && Number.isFinite(v) && potenciasIguais(v, 2 ** dd[1], x, dd[0])) return v;
          }
        }
      }
    }
    return racional(cand[0][0], cand[0][1]);
  }
  function raizInteira(n) { // maior r com r*r <= n (n >= 0)
    if (n < 2n) return n;
    let x = 1n << BigInt((bitLength(n) + 1) >> 1);
    for (;;) { const y = (x + n / x) >> 1n; if (y >= x) return x; x = y; }
  }

  // ---- números aleatórios: xoshiro128** com semente via splitmix32 (igual à VM Python)
  function rotl32(x, k) { return ((x << k) | (x >>> (32 - k))) >>> 0; }
  class Aleatorio {
    constructor(semente) { this.semear(semente); }
    semear(semente) {
      const v = BigInt.asUintN(64, semente);
      const alto = Number(v >> 32n);
      let z = Number(v & 0xFFFFFFFFn);
      const estado = [];
      for (let i = 0; i < 4; i++) {
        z = (z + 0x9E3779B9) >>> 0;
        let r = z;
        r = Math.imul(r ^ (r >>> 16), 0x85EBCA6B) >>> 0;
        r = Math.imul(r ^ (r >>> 13), 0xC2B2AE35) >>> 0;
        r = (r ^ (r >>> 16)) >>> 0;
        estado.push(i % 2 ? (r ^ alto) >>> 0 : r);
      }
      if (!estado.some((w) => w !== 0)) estado[0] = 1;
      this.s = estado;
    }
    proximo() {
      const s = this.s;
      const resultado = Math.imul(rotl32(Math.imul(s[1], 5) >>> 0, 7), 9) >>> 0;
      const t = (s[1] << 9) >>> 0;
      s[2] = (s[2] ^ s[0]) >>> 0;
      s[3] = (s[3] ^ s[1]) >>> 0;
      s[1] = (s[1] ^ s[2]) >>> 0;
      s[0] = (s[0] ^ s[3]) >>> 0;
      s[2] = (s[2] ^ t) >>> 0;
      s[3] = rotl32(s[3], 11);
      return resultado;
    }
    decimal() {
      const a = this.proximo() >>> 5, b = this.proximo() >>> 6;
      return (a * 67108864 + b) / 9007199254740992;
    }
    inteiroEntre(a, b) {
      const n = b - a + 1n;
      const bits = bitLength(n - 1n);
      if (bits === 0) return a;
      const palavras = Math.ceil(bits / 32);
      for (;;) {
        let r = 0n;
        for (let i = 0; i < palavras; i++) r = (r << 32n) | BigInt(this.proximo());
        r >>= BigInt(32 * palavras - bits);
        if (r < n) return a + r;
      }
    }
  }
  function sementeInicial() {
    const c = typeof crypto !== 'undefined' && crypto.getRandomValues ? crypto.getRandomValues(new Uint32Array(2)) : null;
    const w = c ? [c[0], c[1]] : [Math.floor(Math.random() * 2 ** 32), Math.floor(Math.random() * 2 ** 32)];
    return (BigInt(w[0]) << 32n) | BigInt(w[1]);
  }

  function opDiv(a, b) {
    if (isNum(a) && isNum(b)) {
      if (b == 0) throw divisaoPorZero(); // eslint-disable-line eqeqeq
      if (typeof a === 'bigint' && typeof b === 'bigint') return finito(dividirInteiros(a, b));
      return semEstouro(Number(a) / Number(b), a, b);
    }
    throw erroBinario('/', a, b);
  }
  function floorDiv(a, b) { let q = a / b; if ((a % b !== 0n) && ((a < 0n) !== (b < 0n))) q -= 1n; return q; }
  function floorMod(a, b) { let r = a % b; if (r !== 0n && ((r < 0n) !== (b < 0n))) r += b; return r; }
  function opIdiv(a, b) {
    if (isNum(a) && isNum(b)) {
      if (b == 0) throw divisaoPorZero(); // eslint-disable-line eqeqeq
      if (typeof a === 'bigint' && typeof b === 'bigint') return floorDiv(a, b);
      return semEstouro(divmodDecimal(Number(a), Number(b))[0], a, b);
    }
    throw erroBinario('//', a, b);
  }
  function opMod(a, b) {
    if (isNum(a) && isNum(b)) {
      if (b == 0) throw divisaoPorZero(); // eslint-disable-line eqeqeq
      if (typeof a === 'bigint' && typeof b === 'bigint') return floorMod(a, b);
      return divmodDecimal(Number(a), Number(b))[1];
    }
    throw erroBinario('%', a, b);
  }
  function bitLength(n) { if (n < 0n) n = -n; return n === 0n ? 0 : n.toString(2).length; }
  function opPow(a, b) {
    if (!(isNum(a) && isNum(b))) throw erroBinario('^', a, b);
    if (typeof a === 'bigint' && typeof b === 'bigint') {
      if (b >= 0n) {
        if ((a > 1n || a < -1n) && Number(b) * bitLength(a) > MAX_POW_BITS) {
          throw erro('G317', `O resultado de ${a} ^ ${b} seria grande demais para ser calculado.`);
        }
        return a ** b;
      }
      if (a === 0n) throw erro('G303', 'Zero elevado a um expoente negativo equivale a uma divisão por zero.');
      return potenciaInteiraExata(a, Number(b));
    }
    const x = Number(a), y = Number(b);
    if (x === 0 && y < 0) throw erro('G303', 'Zero elevado a um expoente negativo equivale a uma divisão por zero.');
    if (x < 0 && !Number.isInteger(y)) {
      throw erro('G302', `${fmtDecimal(x)} ^ ${fmtDecimal(y)} não é um número real.`,
        'A potência de um número negativo só existe para expoentes inteiros.');
    }
    if (Number.isInteger(y) && Math.abs(y) <= 1024) return potenciaInteiraExata(x, y);
    if (Number.isNaN(x) || Number.isNaN(y) || !Number.isFinite(x) || !Number.isFinite(y) || x === 0) {
      return x === 1 ? 1 : Math.pow(x, y); // casos especiais do IEEE 754 (como no Python: 1 ^ indefinido é 1)
    }
    const magnitude = finito(potenciaExata(Math.abs(x), y));
    return x < 0 && Math.abs(y) % 2 === 1 ? -magnitude : magnitude; // base negativa: aqui y é inteiro
  }
  function opNeg(a) { if (isNum(a)) return -a; throw erro('G302', `Não é possível aplicar '-' a ${artigo(typeName(a))}.`); }
  function opPos(a) { if (isNum(a)) return a; throw erro('G302', `Não é possível aplicar '+' a ${artigo(typeName(a))}.`); }
  function opNot(a) {
    if (typeof a === 'boolean') return !a;
    throw erro('G310', `O operador 'não' exige um booleano, mas recebeu ${artigo(typeName(a))}.`,
      'Use uma comparação, por exemplo: não (x == 0)');
  }
  function comparaveis(a, b) { return (isNum(a) && isNum(b)) || (typeof a === 'string' && typeof b === 'string'); }
  function erroComparacao(op, a, b) {
    const ta = typeName(a), tb = typeName(b);
    let sug = null;
    if ((ta === 'texto' || tb === 'texto') && ['inteiro', 'decimal'].some((n) => n === ta || n === tb)) {
      sug = 'Converta o texto para número antes de comparar: número(texto).';
    }
    return erro('G302', `Não é possível comparar ${artigo(ta)} com ${artigo(tb)} usando '${op}'.`, sug);
  }
  function opCmp(op, a, b) {
    if (!comparaveis(a, b)) throw erroComparacao(op, a, b);
    switch (op) { case '<': return a < b; case '<=': return a <= b; case '>': return a > b; default: return a >= b; }
  }
  function opIn(a, b) {
    if (Array.isArray(b)) return b.some((x) => equals(a, x));
    if (typeof b === 'string') {
      if (typeof a !== 'string') {
        throw erro('G302', `Para procurar dentro de um texto com 'em', o valor procurado deve ser um texto, mas é ${artigo(typeName(a))}.`);
      }
      return b.includes(a);
    }
    if (b instanceof Mapa) return b.has(a);
    throw erro('G302', `O operador 'em' precisa de uma lista, um texto ou um mapa à direita, mas recebeu ${artigo(typeName(b))}.`);
  }
  function exigeBool(v, contexto) {
    if (typeof v === 'boolean') return v;
    throw erro('G310', `${contexto || 'A condição'} precisa ser um booleano (verdadeiro ou falso), mas é ${artigo(typeName(v))}.`,
      'Use uma comparação, por exemplo: se x > 0 então   ou   se tamanho(lista) > 0 então');
  }

  // ------------------------------------------------------------------ acesso

  const PALAVRAS_POSICAO = { lista: ['em uma lista', 'a lista', 'elemento'], texto: ['em um texto', 'o texto', 'caractere'] };

  function posicao(n, idx, tipo, escrevendo) {
    const [onde, sujeito, nome] = PALAVRAS_POSICAO[tipo];
    if (typeof idx !== 'bigint') throw erro('G302', `A posição ${onde} deve ser um inteiro, mas é ${artigo(typeName(idx))}.`);
    if (idx > 0n) { if (idx <= BigInt(n)) return Number(idx) - 1; }
    else if (idx < 0n) { if (-idx <= BigInt(n)) return n + Number(idx); }
    else {
      throw erro('G304', 'A posição 0 não existe: em GALO, a primeira posição é 1.',
        'Use [1] para o primeiro elemento e [-1] para o último.');
    }
    const tamanho = `${n} ${nome}${n !== 1 ? 's' : ''}`;
    let sug;
    if (n === 0) {
      sug = `${capitalizar(sujeito)} está vazi${sujeito[0]}.` + (escrevendo ? ' Para incluir elementos use adicionar(lista, valor).' : '');
    } else {
      sug = `As posições válidas vão de 1 a ${n} (ou de -1 a -${n}, contando do fim).`;
      if (escrevendo && idx === BigInt(n + 1)) sug += ' Para incluir um novo elemento no final, use adicionar(lista, valor).';
    }
    throw erro('G304', `A posição ${idx} está fora dos limites (${sujeito} tem ${tamanho}).`, sug);
  }

  function indexGet(o, i) {
    if (Array.isArray(o)) return o[posicao(o.length, i, 'lista')];
    if (typeof o === 'string') { const cs = Array.from(o); return cs[posicao(cs.length, i, 'texto')]; }
    if (o instanceof Mapa) {
      const v = o.get(i);
      if (v === MISSING) {
        throw erro('G305', `A chave ${repr(i)} não existe no mapa.`,
          "Verifique antes com 'se chave em mapa então' ou use obter(mapa, chave, valor_padrão).");
      }
      return v;
    }
    throw erro('G302', `Não é possível acessar posições de ${artigo(typeName(o))}.`, 'O acesso com [ ] funciona em listas, textos e mapas.');
  }
  function indexSet(o, i, v) {
    if (Array.isArray(o)) { o[posicao(o.length, i, 'lista', true)] = v; return; }
    if (o instanceof Mapa) { o.set(i, v); return; }
    if (typeof o === 'string') {
      throw erro('G302', 'Textos não podem ser alterados por posição.', 'Crie um novo texto, por exemplo com substituir(...) ou fatia(...).');
    }
    throw erro('G302', `Não é possível alterar posições de ${artigo(typeName(o))}.`);
  }

  function erroCampoRegistro(o, nome) {
    const rt = o.tipo;
    return erro('G305', `O registro ${rt.name} não possui o campo '${nome}'.`, `Campos de ${rt.name}: ${rt.fields.join(', ')}`);
  }

  function fieldGet(o, nome) {
    if (o instanceof Registro) {
      const k = canonical(nome);
      const i = o.tipo.index.get(k);
      if (i !== undefined) return o.valores[i];
      const m = o.tipo.methods.get(k);
      if (m !== undefined) return new MetodoLigado(o, m);
      throw erroCampoRegistro(o, nome);
    }
    if (o instanceof Modulo) {
      const k = canonical(nome);
      if (!o.exports.has(k)) throw erro('G305', `O módulo '${o.name}' não exporta '${nome}'.`);
      const v = o.globals.get(k);
      if (v === undefined) throw erro('G301', `'${nome}' ainda não tem valor no módulo '${o.name}'.`);
      return v;
    }
    if (o instanceof ObjetoNativo) {
      const k = canonical(nome);
      const m = o.metodos.get(k);
      if (m) return m;
      const g = o.props.get(k);
      if (g) return g();
      throw erro('G305', `Um ${o.tipo} não possui '${nome}'.`);
    }
    if (!(o instanceof Mapa)) {
      throw erro('G302', `O acesso com '.' (campo '${nome}') só funciona em mapas e registros, mas o valor é ${artigo(typeName(o))}.`,
        'Para chamar uma função sobre o valor, use a forma função(valor), como tamanho(lista).');
    }
    const k = o.findField(nome);
    if (k === MISSING) {
      const ks = o.keys().slice(0, 8).map((x) => repr(x));
      throw erro('G305', `O mapa não possui o campo '${nome}'.`, ks.length ? 'Campos existentes: ' + ks.join(', ') : 'O mapa está vazio.');
    }
    return o.get(k);
  }
  function fieldSet(o, nome, v) {
    if (o instanceof Registro) {
      const k = canonical(nome);
      const i = o.tipo.index.get(k);
      if (i === undefined) {
        if (o.tipo.methods.has(k)) throw erro('G302', `'${nome}' é um método de ${o.tipo.name} e não pode receber outro valor.`);
        throw erroCampoRegistro(o, nome);
      }
      const spec = o.tipo.specs[i];
      if (spec) {
        const c = coerce(v, spec);
        if (c === MISSING) {
          throw erro('G315', `O campo '${o.tipo.fields[i]}' de ${o.tipo.name} é do tipo ${descreverSpec(spec)}, mas recebeu ${artigo(typeName(v))}.`);
        }
        v = c;
      }
      o.valores[i] = v;
      return;
    }
    if (o instanceof ObjetoNativo) {
      const s = o.setters.get(canonical(nome));
      if (!s) throw erro('G302', `'${nome}' de um ${o.tipo} não pode ser alterado.`);
      s(v);
      return;
    }
    if (o instanceof Modulo) throw erro('G302', `Não é possível alterar '${nome}' do módulo '${o.name}' de fora dele.`);
    if (!(o instanceof Mapa)) {
      throw erro('G302', `O acesso com '.' (campo '${nome}') só funciona em mapas e registros, mas o valor é ${artigo(typeName(o))}.`);
    }
    const k = o.findField(nome);
    o.set(k === MISSING ? nome : k, v);
  }

  // ------------------------------------------------------------------ iteração

  function makeIter(v, dois) {
    if (Array.isArray(v)) {
      const copia = v.slice();
      return dois ? copia.map((x, i) => [BigInt(i + 1), x])[Symbol.iterator]() : copia[Symbol.iterator]();
    }
    if (typeof v === 'string') {
      const cs = Array.from(v);
      return dois ? cs.map((x, i) => [BigInt(i + 1), x])[Symbol.iterator]() : cs[Symbol.iterator]();
    }
    if (v instanceof Mapa) return dois ? v.items()[Symbol.iterator]() : v.keys()[Symbol.iterator]();
    const sug = typeof v === 'bigint' ? "Para repetir um número de vezes, use 'repita n vezes' ou 'para i de 1 até n faça'."
      : "O 'para cada' percorre listas, textos e mapas.";
    throw erro('G314', `Não é possível percorrer ${artigo(typeName(v))} com 'para cada'.`, sug);
  }
  function* rangeInteiro(a, b, passo) {
    if (passo > 0n) { for (let i = a; i <= b; i += passo) yield i; } else { for (let i = a; i >= b; i += passo) yield i; }
  }
  function* rangeDecimal(a, b, passo) {
    const tol = Math.abs(passo) * 1e-9;
    for (let k = 0; ; k++) {
      const x = a + k * passo;
      if ((passo > 0 && x > b + tol) || (passo < 0 && x < b - tol)) return;
      yield x;
    }
  }
  function makeRange(a, b, passo) {
    if (!isNum(a)) throw erro('G302', `O valor inicial do 'para' deve ser um número, mas é ${artigo(typeName(a))}.`);
    if (!isNum(b)) throw erro('G302', `O valor final do 'para' deve ser um número, mas é ${artigo(typeName(b))}.`);
    if (passo === null) passo = a <= b ? 1n : -1n;
    else if (!isNum(passo)) throw erro('G302', `O passo do 'para' deve ser um número, mas é ${artigo(typeName(passo))}.`);
    else if (passo == 0) throw erro('G316', "O passo do 'para' não pode ser zero: o laço nunca terminaria."); // eslint-disable-line eqeqeq
    if (typeof a === 'bigint' && typeof b === 'bigint' && typeof passo === 'bigint') return rangeInteiro(a, b, passo);
    return rangeDecimal(Number(a), Number(b), Number(passo));
  }
  function* repetir(n) { for (let i = 0n; i < n; i++) yield null; }
  function makeRepeat(n) {
    if (typeof n !== 'bigint') throw erro('G302', `A quantidade do 'repita' deve ser um inteiro, mas é ${artigo(typeName(n))}.`);
    return repetir(n);
  }

  // ------------------------------------------------------------------ leitura do .galoc

  const TABELA_CRC = (() => {
    const t = new Uint32Array(256);
    for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; }
    return t;
  })();
  function crc32(bytes) {
    let c = 0xFFFFFFFF;
    for (let i = 0; i < bytes.length; i++) c = TABELA_CRC[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8);
    return (c ^ 0xFFFFFFFF) >>> 0;
  }

  function erroBytecode(msg) {
    return erro('G502', `O arquivo de bytecode está corrompido ou incompleto (${msg}).`,
      'Compile novamente o programa com: galo compilar programa.galo');
  }

  class Leitor {
    constructor(bytes) { this.b = bytes; this.p = 0; this.dec = new TextDecoder('utf-8'); }
    byte() { if (this.p >= this.b.length) throw erroBytecode('fim inesperado'); return this.b[this.p++]; }
    varint() {
      let r = 0, mult = 1;
      for (;;) { const b = this.byte(); r += (b & 0x7F) * mult; if (!(b & 0x80)) return r; mult *= 128; if (mult > 2 ** 56) throw erroBytecode('número inválido'); }
    }
    raw(n) { if (this.p + n > this.b.length) throw erroBytecode('fim inesperado'); const s = this.b.subarray(this.p, this.p + n); this.p += n; return s; }
    str() { return this.dec.decode(this.raw(this.varint())); }
    spec() { const n = this.varint(); if (n === 0) return null; const s = []; for (let i = 0; i < n; i++) s.push(this.str()); return s; }
    value(prof) {
      const t = String.fromCharCode(this.byte());
      switch (t) {
        case 'N': return null;
        case 'T': return true;
        case 'F': return false;
        case 'I': {
          const neg = this.byte(); const n = this.varint(); const bytes = this.raw(n);
          let v = 0n; for (let i = bytes.length - 1; i >= 0; i--) v = (v << 8n) | BigInt(bytes[i]);
          return neg ? -v : v;
        }
        case 'D': { const bytes = this.raw(8); return new DataView(bytes.buffer, bytes.byteOffset, 8).getFloat64(0, true); }
        case 'S': return this.str();
        case 'C': if (prof > 200) throw erroBytecode('aninhamento excessivo'); return this.code(prof + 1);
        case 'Y': { const spec = this.spec() || []; return { tipo: 'checagem', spec, label: this.str() }; }
        case 'R': {
          const name = this.str(); const fields = []; const specs = [];
          const nf = this.varint(); for (let i = 0; i < nf; i++) { fields.push(this.str()); specs.push(this.spec()); }
          const methods = []; const nm = this.varint(); for (let i = 0; i < nm; i++) methods.push(this.str());
          return { tipo: 'registro', name, fields, specs, methods };
        }
        case 'K': { const npos = this.varint(); const names = []; const n = this.varint(); for (let i = 0; i < n; i++) names.push(this.str()); return { tipo: 'chamada', npos, names }; }
        default: throw erroBytecode(`marca de constante desconhecida ${t}`);
      }
    }
    code(prof = 0) {
      const co = { name: this.str(), filename: this.str(), params: [], paramTypes: [], defaults: [] };
      const np = this.varint();
      for (let i = 0; i < np; i++) { co.params.push(this.str()); co.paramTypes.push(this.spec()); co.defaults.push(!!this.byte()); }
      co.nlocals = this.varint();
      co.localNames = []; const nl = this.varint(); for (let i = 0; i < nl; i++) co.localNames.push(this.str());
      co.freeSources = []; co.freeNames = [];
      const nfree = this.varint();
      for (let i = 0; i < nfree; i++) { const kind = this.byte(); const idx = this.varint(); co.freeSources.push([kind, idx]); co.freeNames.push(this.str()); }
      co.returnType = this.byte() ? this.spec() : null;
      co.names = []; const nn = this.varint(); for (let i = 0; i < nn; i++) co.names.push(this.str());
      co.keys = co.names.map(canonical);
      co.consts = []; const nc = this.varint(); for (let i = 0; i < nc; i++) co.consts.push(this.value(prof));
      const n = this.varint();
      co.code = new Array(n); for (let i = 0; i < n; i++) co.code[i] = this.varint();
      co.positions = new Array(n / 2);
      for (let i = 0; i < n / 2; i++) co.positions[i] = [this.varint(), this.varint()];
      co.typed = co.paramTypes.some((s) => s !== null);
      co.hasDefaults = co.defaults.some((d) => d);
      return co;
    }
  }

  function carregar(dados) {
    const bytes = dados instanceof Uint8Array ? dados : new Uint8Array(dados);
    const magica = [0x47, 0x41, 0x4C, 0x4F, 0x43, 0x00];
    if (bytes.length < 12 || !magica.every((b, i) => bytes[i] === b)) {
      throw erro('G502', 'Este arquivo não é um programa GALO compilado (.galoc).');
    }
    const versao = bytes[6] | (bytes[7] << 8);
    if (versao !== VERSAO_BYTECODE) {
      throw erro('G503', `Este bytecode usa o formato versão ${versao}, mas esta GALO entende a versão ${VERSAO_BYTECODE}.`,
        'Compile o programa novamente com a versão atual: galo compilar programa.galo');
    }
    const conteudo = bytes.subarray(8, bytes.length - 4);
    const crc = new DataView(bytes.buffer, bytes.byteOffset + bytes.length - 4, 4).getUint32(0, true);
    if (crc32(conteudo) !== crc) throw erro('G502', 'O arquivo de bytecode está corrompido (soma de verificação inválida).');
    const r = new Leitor(conteudo);
    const galoVersion = r.str(); const programa = r.str(); const fonte = r.str();
    const code = r.code();
    const modules = []; const nm = r.varint();
    for (let i = 0; i < nm; i++) {
      const name = r.str(); const mcode = r.code(); const exports = []; const ne = r.varint();
      for (let j = 0; j < ne; j++) exports.push(r.str());
      modules.push({ name, code: mcode, exports });
    }
    if (r.p !== conteudo.length) throw erroBytecode('dados extras no final');
    return { galoVersion, programName: programa || null, sourceName: fonte, code, modules };
  }

  // ------------------------------------------------------------------ máquina virtual

  class Frame {
    constructor(code, locals, cells, globals) {
      this.code = code; this.pc = 0; this.locals = locals; this.stack = []; this.cells = cells;
      this.handlers = null; this.globals = globals;
    }
  }

  class VM {
    constructor(opcoes = {}) {
      this.escrever = opcoes.escrever || saidaPadrao();
      this.ler = opcoes.ler || ((msg) => (typeof prompt === 'function' ? prompt(msg) : null));
      this.aoErro = opcoes.aoErro || mostrarErro;
      this.maxFrames = opcoes.limitePilha || 100000;
      this.globals = new Map();
      this.builtins = new Map(BUILTINS);
      this.frames = [];
      this.moduleTable = [];
      this.loaded = new Map();
      this.random = new Aleatorio(sementeInicial());
    }

    run(module) {
      this.moduleTable = module.modules || [];
      const f = new Frame(module.code, new Array(module.code.nlocals).fill(null), [], this.globals);
      const stop = this.frames.length;
      this.frames.push(f);
      try { return this.execute(stop); } finally { this.frames.length = stop; }
    }

    // Chamada vinda de fora do laço principal (eventos, temporizadores, respostas de rede).
    chamarDeFora(fn, args) {
      try {
        return this.callValue(fn, args);
      } catch (e) {
        if (e instanceof GaloSaida) return null;
        if (e instanceof GaloErro) { this.aoErro(e); return null; }
        throw e;
      }
    }

    callValue(fn, args, kwargs) {
      if (fn instanceof Native) {
        if (kwargs && kwargs.length) throw erro('G307', `A função interna '${fn.name}' não aceita argumentos nomeados.`);
        this.checkNative(fn, args.length);
        return fn.fn(this, args);
      }
      if (fn instanceof MetodoLigado) return this.callValue(fn.funcao, [fn.receptor].concat(args), kwargs);
      if (fn instanceof TipoRegistro) return this.callValue(fn.ctor, args, kwargs);
      if (fn instanceof Closure) {
        args = args.slice();
        const f = this.newFrame(fn, args);
        const stop = this.frames.length;
        this.frames.push(f);
        return this.execute(stop);
      }
      throw erro('G306', `Tentou chamar ${artigo(typeName(fn))} como se fosse uma função.`);
    }

    checkNative(fn, n) {
      if (n < fn.min || (fn.max !== null && n > fn.max)) {
        const esperado = fn.max === null ? `pelo menos ${fn.min}` : (fn.min === fn.max ? `${fn.min}` : `de ${fn.min} a ${fn.max}`);
        throw erro('G307', `A função interna '${fn.name}' espera ${esperado} argumento(s), mas recebeu ${n}.`);
      }
    }

    bindKwargs(fn, args, names, values) {
      const co = fn.code; const params = co.params; const keys = params.map(canonical);
      if (args.length > params.length) {
        throw erro('G307', `A função '${co.name}' espera no máximo ${params.length} argumentos, mas recebeu ${args.length} sem nome.`);
      }
      const bound = args.concat(new Array(params.length - args.length).fill(UNSET));
      names.forEach((nome, j) => {
        const i = keys.indexOf(canonical(nome));
        if (i < 0) throw erro('G307', `A função '${co.name}' não tem o parâmetro '${nome}'.`, `Parâmetros: ${params.join(', ')}`);
        if (bound[i] !== UNSET) throw erro('G307', `O parâmetro '${params[i]}' recebeu valor duas vezes.`);
        bound[i] = values[j];
      });
      bound.forEach((v, i) => {
        if (v === UNSET && !co.defaults[i]) {
          throw erro('G307', `Falta o argumento '${params[i]}' na chamada de '${co.name}'.`, `Forma correta: ${co.name}(${params.join(', ')})`);
        }
      });
      return bound;
    }

    newFrame(fn, args) {
      const co = fn.code; const params = co.params; const np = params.length; const n = args.length;
      if (n !== np) {
        if (n > np) {
          const plural = np === 1 ? 'argumento' : 'argumentos';
          throw erro('G307', `A função '${co.name}' espera ${co.hasDefaults ? 'no máximo ' : ''}${np} ${plural}, mas recebeu ${n}.`,
            `Forma correta: ${co.name}(${params.join(', ')})`);
        }
        for (let i = n; i < np; i++) {
          if (!co.defaults[i]) {
            throw erro('G307', `Falta o argumento '${params[i]}' na chamada de '${co.name}'.`, `Forma correta: ${co.name}(${params.join(', ')})`);
          }
          args.push(UNSET);
        }
      }
      if (co.typed) {
        for (let i = 0; i < np; i++) {
          const spec = co.paramTypes[i];
          if (spec && args[i] !== UNSET) {
            const v = coerce(args[i], spec);
            if (v === MISSING) {
              throw erro('G308', `O parâmetro '${params[i]}' da função '${co.name}' espera ${descreverSpec(spec)}, mas recebeu ${artigo(typeName(args[i]))}.`);
            }
            args[i] = v;
          }
        }
      }
      if (this.frames.length >= this.maxFrames) {
        throw erro('G311', `Estouro de pilha: mais de ${this.maxFrames} chamadas de função aninhadas.`,
          'Isso costuma indicar uma recursão sem caso base (a função chama a si mesma para sempre).');
      }
      while (args.length < co.nlocals) args.push(null);
      return new Frame(co, args, fn.cells, fn.globals);
    }

    resolve(fn, args) {
      if (fn instanceof MetodoLigado) return this.resolve(fn.funcao, [fn.receptor].concat(args));
      if (fn instanceof TipoRegistro) return [fn.ctor, args];
      return [fn, args];
    }

    importModule(i) {
      const entry = this.moduleTable[i];
      let m = this.loaded.get(entry.name);
      if (m) return m;
      m = new Modulo(entry.name, entry.exports);
      this.loaded.set(entry.name, m);
      const f = new Frame(entry.code, new Array(entry.code.nlocals).fill(null), [], m.globals);
      const stop = this.frames.length;
      this.frames.push(f);
      try { this.execute(stop); } catch (e) { this.loaded.delete(entry.name); throw e; }
      return m;
    }

    errorValue(e) {
      if (e.valor instanceof Mapa) return e.valor;
      const m = Mapa.de([['mensagem', e.mensagem], ['código', e.codigo], ['linha', e.linha == null ? null : BigInt(e.linha)]]);
      if (e.valor !== undefined && e.valor !== null) m.set('valor', e.valor);
      return m;
    }

    attach(e) {
      if (!this.frames.length) return;
      if (e.linha == null) {
        const f = this.frames[this.frames.length - 1];
        const p = f.code.positions[(f.pc - 2) / 2];
        if (p) { e.linha = p[0]; e.coluna = p[1]; }
        e.arquivo = e.arquivo || f.code.filename;
      }
      if (!e.rastro) {
        e.rastro = this.frames.map((f) => { const p = f.code.positions[(f.pc - 2) / 2]; return [f.code.name, p ? p[0] : null]; });
      }
    }

    unwind(e, stop) {
      const frames = this.frames;
      while (frames.length > stop) {
        const f = frames[frames.length - 1];
        if (f.handlers && f.handlers.length) {
          const [alvo, altura] = f.handlers.pop();
          f.stack.length = altura;
          f.stack.push(this.errorValue(e));
          f.pc = alvo;
          return true;
        }
        frames.pop();
      }
      return false;
    }

    userError(v) {
      let msg;
      if (v instanceof Mapa) { const m = v.get('mensagem'); msg = m === MISSING ? repr(v) : display(m); } else msg = display(v);
      const e = erro('G400', msg);
      e.valor = v;
      return e;
    }

    execute(stop) {
      const frames = this.frames;
      const builtins = this.builtins;
      outer: for (;;) {
        const frame = frames[frames.length - 1];
        const globals = frame.globals;
        const co = frame.code;
        const code = co.code;
        const consts = co.consts;
        const stack = frame.stack;
        const locs = frame.locals;
        let pc = frame.pc;
        try {
          for (;;) {
            const op = code[pc]; const arg = code[pc + 1]; pc += 2;
            switch (op) {
              case OP.LOAD_LOCAL: stack.push(locs[arg]); break;
              case OP.CONST: stack.push(consts[arg]); break;
              case OP.STORE_LOCAL: locs[arg] = stack.pop(); break;
              case OP.LOAD_GLOBAL: {
                const k = co.keys[arg];
                let v = globals.get(k);
                if (v === undefined) {
                  v = builtins.get(k);
                  if (v === undefined) {
                    if (SOMENTE_SERVIDOR.has(k)) {
                      throw erro('G327', `A função ${co.names[arg]}() só está disponível no servidor, não no navegador.`,
                        'Faça essa parte no servidor GALO e consulte-a com buscar().');
                    }
                    throw erro('G301', `A variável "${co.names[arg]}" ainda não tem valor neste ponto da execução.`);
                  }
                }
                stack.push(v);
                break;
              }
              case OP.JUMP_IF_FALSE: {
                const v = stack.pop();
                if (v === false) pc = arg; else if (v !== true) exigeBool(v);
                break;
              }
              case OP.JUMP: pc = arg; break;
              case OP.FOR_ITER: {
                const r = stack[stack.length - 1].next();
                if (r.done) { stack.pop(); pc = arg; } else stack.push(r.value);
                break;
              }
              case OP.FOR_ITER2: {
                const r = stack[stack.length - 1].next();
                if (r.done) { stack.pop(); pc = arg; } else { stack.push(r.value[0]); stack.push(r.value[1]); }
                break;
              }
              case OP.STORE_GLOBAL: {
                const k = co.keys[arg];
                if (!globals.has(k)) throw erro('G301', `A variável "${co.names[arg]}" ainda não tem valor neste ponto da execução.`);
                globals.set(k, stack.pop());
                break;
              }
              case OP.ADD: { const b = stack.pop(); stack[stack.length - 1] = opAdd(stack[stack.length - 1], b); break; }
              case OP.SUB: { const b = stack.pop(); stack[stack.length - 1] = opSub(stack[stack.length - 1], b); break; }
              case OP.MUL: { const b = stack.pop(); stack[stack.length - 1] = opMul(stack[stack.length - 1], b); break; }
              case OP.DIV: { const b = stack.pop(); stack[stack.length - 1] = opDiv(stack[stack.length - 1], b); break; }
              case OP.IDIV: { const b = stack.pop(); stack[stack.length - 1] = opIdiv(stack[stack.length - 1], b); break; }
              case OP.MOD: { const b = stack.pop(); stack[stack.length - 1] = opMod(stack[stack.length - 1], b); break; }
              case OP.POW: { const b = stack.pop(); stack[stack.length - 1] = opPow(stack[stack.length - 1], b); break; }
              case OP.LT: { const b = stack.pop(); stack[stack.length - 1] = opCmp('<', stack[stack.length - 1], b); break; }
              case OP.LE: { const b = stack.pop(); stack[stack.length - 1] = opCmp('<=', stack[stack.length - 1], b); break; }
              case OP.GT: { const b = stack.pop(); stack[stack.length - 1] = opCmp('>', stack[stack.length - 1], b); break; }
              case OP.GE: { const b = stack.pop(); stack[stack.length - 1] = opCmp('>=', stack[stack.length - 1], b); break; }
              case OP.EQ: { const b = stack.pop(); stack[stack.length - 1] = equals(stack[stack.length - 1], b); break; }
              case OP.NE: { const b = stack.pop(); stack[stack.length - 1] = !equals(stack[stack.length - 1], b); break; }
              case OP.IN: { const b = stack.pop(); stack[stack.length - 1] = opIn(stack[stack.length - 1], b); break; }
              case OP.NEG: stack[stack.length - 1] = opNeg(stack[stack.length - 1]); break;
              case OP.POS: stack[stack.length - 1] = opPos(stack[stack.length - 1]); break;
              case OP.NOT: stack[stack.length - 1] = opNot(stack[stack.length - 1]); break;
              case OP.CALL: {
                let fn = stack[stack.length - arg - 1];
                let args = arg ? stack.splice(stack.length - arg, arg) : [];
                stack.pop();
                [fn, args] = this.resolve(fn, args);
                if (fn instanceof Closure) {
                  const nf = this.newFrame(fn, args);
                  frame.pc = pc;
                  frames.push(nf);
                  continue outer;
                }
                if (fn instanceof Native) {
                  this.checkNative(fn, args.length);
                  frame.pc = pc;
                  stack.push(fn.fn(this, args));
                  break;
                }
                throw erro('G306', `Tentou chamar ${artigo(typeName(fn))} como se fosse uma função.`,
                  'Só funções podem ser chamadas com parênteses: nome(argumentos).');
              }
              case OP.CALL_KW: {
                const info = consts[arg];
                const total = info.npos + info.names.length;
                const valores = total ? stack.splice(stack.length - total, total) : [];
                let fn = stack.pop();
                let pos;
                [fn, pos] = this.resolve(fn, valores.slice(0, info.npos));
                if (!(fn instanceof Closure)) {
                  if (fn instanceof Native) throw erro('G307', `A função interna '${fn.name}' não aceita argumentos nomeados.`);
                  throw erro('G306', `Tentou chamar ${artigo(typeName(fn))} como se fosse uma função.`);
                }
                const args = this.bindKwargs(fn, pos, info.names, valores.slice(info.npos));
                const nf = this.newFrame(fn, args);
                frame.pc = pc;
                frames.push(nf);
                continue outer;
              }
              case OP.RETURN: {
                let v = stack.pop();
                const rt = co.returnType;
                if (rt) {
                  const c = coerce(v, rt);
                  if (c === MISSING) {
                    if (arg === 1) {
                      throw erro('G309', `A função '${co.name}' deveria retornar ${descreverSpec(rt)}, mas terminou sem executar 'retorne'.`,
                        "Garanta que todos os caminhos da função terminem com 'retorne <valor>'.");
                    }
                    throw erro('G309', `A função '${co.name}' deveria retornar ${descreverSpec(rt)}, mas retornou ${artigo(typeName(v))}.`);
                  }
                  v = c;
                }
                frames.pop();
                if (frames.length === stop) return v;
                frames[frames.length - 1].stack.push(v);
                continue outer;
              }
              case OP.INDEX: { const i = stack.pop(); stack[stack.length - 1] = indexGet(stack[stack.length - 1], i); break; }
              case OP.STORE_INDEX: { const v = stack.pop(); const i = stack.pop(); indexSet(stack.pop(), i, v); break; }
              case OP.GET_FIELD: stack[stack.length - 1] = fieldGet(stack[stack.length - 1], co.names[arg]); break;
              case OP.SET_FIELD: { const v = stack.pop(); fieldSet(stack.pop(), co.names[arg], v); break; }
              case OP.LOAD_CELL: {
                const v = locs[arg].value;
                if (v === UNSET) throw erro('G318', `'${co.localNames[arg]}' foi usada antes de receber um valor.`);
                stack.push(v);
                break;
              }
              case OP.LOAD_FREE: {
                const v = frame.cells[arg].value;
                if (v === UNSET) throw erro('G318', `'${co.freeNames[arg]}' foi usada antes de receber um valor.`);
                stack.push(v);
                break;
              }
              case OP.STORE_CELL: locs[arg].value = stack.pop(); break;
              case OP.STORE_FREE: frame.cells[arg].value = stack.pop(); break;
              case OP.MAKE_CELL: locs[arg] = new Cell(); break;
              case OP.BOX_LOCAL: locs[arg] = new Cell(locs[arg]); break;
              case OP.DEFINE_GLOBAL: globals.set(co.keys[arg], stack.pop()); break;
              case OP.POP: stack.pop(); break;
              case OP.DUP: stack.push(stack[stack.length - 1]); break;
              case OP.JUMP_IF_FALSE_KEEP: {
                const v = stack[stack.length - 1];
                if (v === false) pc = arg; else if (v === true) stack.pop(); else exigeBool(v, "Cada lado do operador 'e'");
                break;
              }
              case OP.JUMP_IF_TRUE_KEEP: {
                const v = stack[stack.length - 1];
                if (v === true) pc = arg; else if (v === false) stack.pop(); else exigeBool(v, "Cada lado do operador 'ou'");
                break;
              }
              case OP.CHECK_BOOL: {
                const v = stack[stack.length - 1];
                if (typeof v !== 'boolean') exigeBool(v, `Cada lado do operador '${arg === 2 ? 'ou' : 'e'}'`);
                break;
              }
              case OP.BUILD_LIST: stack.push(arg ? stack.splice(stack.length - arg, arg) : []); break;
              case OP.BUILD_MAP: {
                const m = new Mapa();
                if (arg) { const itens = stack.splice(stack.length - 2 * arg, 2 * arg); for (let i = 0; i < itens.length; i += 2) m.set(itens[i], itens[i + 1]); }
                stack.push(m);
                break;
              }
              case OP.BUILD_STRING: stack.push(stack.splice(stack.length - arg, arg).map(display).join('')); break;
              case OP.MAKE_FUNCTION: {
                const fco = consts[arg];
                const cells = fco.freeSources.map(([kind, i]) => (kind === 0 ? locs[i] : frame.cells[i]));
                stack.push(new Closure(fco, cells, globals));
                break;
              }
              case OP.PRINT: this.escrever((arg ? stack.splice(stack.length - arg, arg).map(display).join(' ') : '') + '\n'); break;
              case OP.PRINT_REPL: { const v = stack.pop(); if (v !== null) this.escrever(repr(v) + '\n'); break; }
              case OP.ITER_PREPARE: stack[stack.length - 1] = makeIter(stack[stack.length - 1], arg === 1); break;
              case OP.RANGE_PREPARE: {
                const passo = arg ? stack.pop() : null; const fim = stack.pop();
                stack[stack.length - 1] = makeRange(stack[stack.length - 1], fim, passo);
                break;
              }
              case OP.REPEAT_PREPARE: stack[stack.length - 1] = makeRepeat(stack[stack.length - 1]); break;
              case OP.SETUP_TRY: (frame.handlers || (frame.handlers = [])).push([arg, stack.length]); break;
              case OP.POP_TRY: frame.handlers.pop(); break;
              case OP.RAISE: throw this.userError(stack.pop());
              case OP.CHECK_TYPE: {
                const tc = consts[arg];
                const v = coerce(stack[stack.length - 1], tc.spec);
                if (v === MISSING) {
                  throw erro('G315', `${capitalizar(tc.label)} é do tipo ${descreverSpec(tc.spec)}, mas recebeu ${artigo(typeName(stack[stack.length - 1]))}.`);
                }
                stack[stack.length - 1] = v;
                break;
              }
              case OP.ARG_MISSING: { const v = locs[arg]; stack.push(v === UNSET || (v instanceof Cell && v.value === UNSET)); break; }
              case OP.NEW_RECORD: {
                const valores = arg ? stack.splice(stack.length - arg, arg) : [];
                stack[stack.length - 1] = new Registro(stack[stack.length - 1], valores);
                break;
              }
              case OP.MAKE_RECORD_TYPE: {
                const info = consts[arg];
                const k = info.methods.length;
                const metodos = k ? stack.splice(stack.length - k, k) : [];
                const mapa = new Map(info.methods.map((n, i) => [canonical(n), metodos[i]]));
                stack[stack.length - 1] = new TipoRegistro(info.name, info.fields, info.specs, stack[stack.length - 1], mapa);
                break;
              }
              case OP.IMPORT_MODULE: frame.pc = pc; stack.push(this.importModule(arg)); break;
              case OP.NOP: break;
              default: throw new Error(`instrução desconhecida: ${op}`);
            }
          }
        } catch (e) {
          let err = e;
          if (e instanceof GaloSaida) throw e;
          if (!(e instanceof GaloErro)) {
            if (e instanceof RangeError && /call stack|recursion/i.test(e.message)) {
              err = erro('G311', 'Estouro de pilha: há estruturas ou chamadas aninhadas demais.');
            } else {
              throw e;
            }
          }
          frame.pc = pc;
          this.attach(err);
          if (!this.unwind(err, stop)) throw err;
        }
      }
    }
  }

  // ------------------------------------------------------------------ biblioteca padrão

  const BUILTINS = new Map();
  function nativa(nome, min, max, fn) { const n = new Native(nome, fn, min, max); BUILTINS.set(n.key, n); }
  function constante(nome, valor) { BUILTINS.set(canonical(nome), valor); }

  // Funções da biblioteca padrão que dependem do servidor (arquivos, banco, rede síncrona...).
  const SOMENTE_SERVIDOR = new Set([
    'ler_arquivo', 'ler_linhas', 'escrever_arquivo', 'anexar_arquivo', 'arquivo_existe', 'apagar_arquivo',
    'listar_arquivos', 'abrir_banco', 'criar_servidor', 'resposta', 'resposta_json', 'resposta_html', 'redirecionar',
    'requisitar', 'hash_senha', 'verificar_senha', 'sha256', 'modelo', 'renderizar', 'variavel_ambiente', 'espere',
    'compilar_programa',
  ].map(canonical));

  function exige(fname, pos, v, ...tipos) {
    const tn = typeName(v);
    if (tipos.includes(tn)) return v;
    if (tn === 'inteiro' && tipos.includes('decimal')) return Number(v);
    throw erro('G322', `A função ${fname}() espera ${descreverTipos(tipos)} no argumento ${pos}, mas recebeu ${artigo(tn)}.`);
  }
  const exigeTexto = (f, p, v) => exige(f, p, v, 'texto');
  const exigeInteiro = (f, p, v) => exige(f, p, v, 'inteiro');
  const exigeLista = (f, p, v) => exige(f, p, v, 'lista');
  const exigeMapa = (f, p, v) => exige(f, p, v, 'mapa');
  const exigeFuncao = (f, p, v) => exige(f, p, v, 'função');
  function exigeNumero(f, p, v) {
    if (isNum(v)) return v;
    throw erro('G322', `A função ${f}() espera um número no argumento ${p}, mas recebeu ${artigo(typeName(v))}.`);
  }
  const opcional = (args, i, padrao) => (args.length > i ? args[i] : padrao);

  const RE_INT = /^[+-]?[0-9]+(?:_[0-9]+)*$/;
  const RE_DEC = /^[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?$/;
  function lerNumero(s) {
    s = s.trim();
    if (!s) return null;
    if (RE_INT.test(s)) return BigInt(s.replace(/_/g, ''));
    if (s.includes(',') && !s.includes('.') && s.split(',').length === 2) s = s.replace(',', '.');
    if (RE_DEC.test(s)) return Number(s);
    return null;
  }

  // Arredondamento comercial (metade para longe do zero) sobre a forma decimal exata do valor.
  function arredondarTexto(v, casas) {
    let txt = typeof v === 'bigint' ? v.toString() : fmtDecimal(v);
    const neg = txt.startsWith('-');
    if (neg) txt = txt.slice(1);
    let [mant, exp] = txt.split('e');
    exp = exp ? parseInt(exp, 10) : 0;
    const [ip, fp = ''] = mant.split('.');
    let digitos = BigInt(ip + fp);
    let escala = exp - fp.length; // valor = digitos * 10^escala
    if (escala >= -casas) {
      digitos *= 10n ** BigInt(escala + casas);
    } else {
      const d = 10n ** BigInt(-casas - escala);
      const q = digitos / d; const r = digitos % d;
      digitos = 2n * r >= d ? q + 1n : q;
    }
    let s = digitos.toString();
    if (casas > 0) { s = s.padStart(casas + 1, '0'); s = s.slice(0, -casas) + '.' + s.slice(-casas); }
    return (neg && /[1-9]/.test(s) ? '-' : '') + s;
  }

  function ordenaveis(fname, chaves) {
    const tipos = new Set(chaves.map(typeName));
    const ok = [...tipos].every((t) => t === 'inteiro' || t === 'decimal') || (tipos.size === 1 && tipos.has('texto')) || tipos.size === 0;
    if (!ok) throw erro('G322', `A função ${fname}() só ordena listas só de números ou só de textos, mas encontrou: ${[...tipos].sort().join(' e ')}.`);
  }
  const comparar = (a, b) => (a < b ? -1 : a > b ? 1 : 0);

  // -- entrada e saída
  nativa('leia', 0, 1, (vm, a) => { const r = vm.ler(a.length ? display(a[0]) : ''); return r === undefined ? null : r; });
  nativa('escreva', 0, null, (vm, a) => { vm.escrever(a.map(display).join(' ')); return null; });

  // -- texto
  nativa('tamanho', 1, 1, (vm, [v]) => {
    if (Array.isArray(v)) return BigInt(v.length);
    if (typeof v === 'string') return BigInt(Array.from(v).length);
    if (v instanceof Mapa) return BigInt(v.size);
    throw erro('G322', `A função tamanho() espera uma lista, um texto ou um mapa, mas recebeu ${artigo(typeName(v))}.`);
  });
  nativa('maiúsculas', 1, 1, (vm, [t]) => exigeTexto('maiúsculas', 1, t).toUpperCase());
  nativa('minúsculas', 1, 1, (vm, [t]) => exigeTexto('minúsculas', 1, t).toLowerCase());
  nativa('aparar', 1, 1, (vm, [t]) => exigeTexto('aparar', 1, t).trim());
  nativa('dividir', 1, 2, (vm, a) => {
    const t = exigeTexto('dividir', 1, a[0]);
    if (a.length < 2 || a[1] === null) { const s = t.trim(); return s ? s.split(/\s+/) : []; }
    const sep = exigeTexto('dividir', 2, a[1]);
    return sep === '' ? Array.from(t) : t.split(sep);
  });
  nativa('juntar', 1, 2, (vm, a) => exigeLista('juntar', 1, a[0]).map(display).join(exigeTexto('juntar', 2, opcional(a, 1, ''))));
  nativa('substituir', 3, 3, (vm, [t, x, y]) => {
    exigeTexto('substituir', 1, t); exigeTexto('substituir', 2, x); exigeTexto('substituir', 3, y);
    if (x === '') throw erro('G322', 'A função substituir() não aceita um texto vazio como valor a ser trocado.');
    return t.split(x).join(y);
  });
  nativa('contém', 2, 2, (vm, [c, v]) => opIn(v, c));
  nativa('começa_com', 2, 2, (vm, [t, p]) => exigeTexto('começa_com', 1, t).startsWith(exigeTexto('começa_com', 2, p)));
  nativa('termina_com', 2, 2, (vm, [t, s]) => exigeTexto('termina_com', 1, t).endsWith(exigeTexto('termina_com', 2, s)));
  nativa('posição', 2, 2, (vm, [c, v]) => {
    if (typeof c === 'string') {
      exigeTexto('posição', 2, v);
      const i = c.indexOf(v);
      return i < 0 ? null : BigInt(Array.from(c.slice(0, i)).length + 1);
    }
    if (Array.isArray(c)) { const i = c.findIndex((x) => equals(x, v)); return i < 0 ? null : BigInt(i + 1); }
    throw erro('G322', `A função posição() espera um texto ou uma lista, mas recebeu ${artigo(typeName(c))}.`);
  });
  nativa('fatia', 2, 3, (vm, a) => {
    const c = a[0];
    if (typeof c !== 'string' && !Array.isArray(c)) throw erro('G322', `A função fatia() espera um texto ou uma lista, mas recebeu ${artigo(typeName(c))}.`);
    const ini = exigeInteiro('fatia', 2, a[1]);
    const fim = a.length > 2 && a[2] !== null ? exigeInteiro('fatia', 3, a[2]) : null;
    const seq = typeof c === 'string' ? Array.from(c) : c;
    const n = seq.length;
    const norm = (p) => { let x = Number(p); if (x < 0) x = n + x + 1; return Math.min(Math.max(x, 1), n + 1); };
    const i0 = ini !== 0n ? norm(ini) : 1;
    let f = fim === null ? n : (fim !== 0n ? norm(fim) : 0);
    f = Math.min(f, n);
    const r = i0 - 1 < f ? seq.slice(i0 - 1, f) : [];
    return typeof c === 'string' ? r.join('') : r;
  });
  nativa('caracteres', 1, 1, (vm, [t]) => Array.from(exigeTexto('caracteres', 1, t)));
  nativa('código', 1, 1, (vm, [c]) => {
    exigeTexto('código', 1, c);
    const cs = Array.from(c);
    if (cs.length !== 1) throw erro('G322', `A função código() espera um texto com exatamente 1 caractere, mas recebeu ${cs.length}.`);
    return BigInt(c.codePointAt(0));
  });
  nativa('caractere', 1, 1, (vm, [n]) => {
    exigeInteiro('caractere', 1, n);
    if (n < 0n || n > 0x10FFFFn) throw erro('G322', `O código ${n} não corresponde a nenhum caractere Unicode.`);
    return String.fromCodePoint(Number(n));
  });
  nativa('repetir', 2, 2, (vm, [t, n]) => { exigeTexto('repetir', 1, t); exigeInteiro('repetir', 2, n); return n > 0n ? t.repeat(Number(n)) : ''; });
  nativa('inverter', 1, 1, (vm, [v]) => {
    if (typeof v === 'string') return Array.from(v).reverse().join('');
    if (Array.isArray(v)) return v.slice().reverse();
    throw erro('G322', `A função inverter() espera um texto ou uma lista, mas recebeu ${artigo(typeName(v))}.`);
  });
  nativa('formatar', 2, 2, (vm, [n, casas]) => {
    exigeNumero('formatar', 1, n); exigeInteiro('formatar', 2, casas);
    if (casas < 0n || casas > 100n) throw erro('G322', 'A quantidade de casas decimais deve estar entre 0 e 100.');
    if (typeof n === 'number' && !Number.isFinite(n)) throw erro('G322', 'Não é possível formatar um valor infinito ou indefinido.');
    return arredondarTexto(n, Number(casas));
  });
  nativa('é_número', 1, 1, (vm, [t]) => (isNum(t) ? true : typeof t === 'string' ? lerNumero(t) !== null : false));
  function regex(fname, p, flags) {
    exigeTexto(fname, 2, p);
    try { return new RegExp(p, flags); } catch (e) { throw erro('G322', `Expressão regular inválida em ${fname}(): ${e.message}.`); }
  }
  nativa('corresponde', 2, 2, (vm, [t, p]) => regex('corresponde', p, 'u').test(exigeTexto('corresponde', 1, t)));
  nativa('procurar_todos', 2, 2, (vm, [t, p]) => Array.from(exigeTexto('procurar_todos', 1, t).matchAll(regex('procurar_todos', p, 'gu')), (m) => m[0]));
  nativa('substituir_padrão', 3, 3, (vm, [t, p, novo]) => {
    exigeTexto('substituir_padrão', 3, novo);
    return exigeTexto('substituir_padrão', 1, t).replace(regex('substituir_padrão', p, 'gu'),
      (...m) => novo.replace(/\\(\d+)/g, (_, g) => (m[Number(g)] === undefined ? '' : m[Number(g)])));
  });

  // -- matemática
  constante('pi', Math.PI);
  nativa('absoluto', 1, 1, (vm, [x]) => { exigeNumero('absoluto', 1, x); return typeof x === 'bigint' ? (x < 0n ? -x : x) : Math.abs(x); });
  nativa('raiz', 1, 1, (vm, [x]) => {
    exigeNumero('raiz', 1, x);
    if (x < 0) throw erro('G322', `Não existe raiz quadrada real de um número negativo (${display(x)}).`);
    if (typeof x === 'bigint' && x > LIMITE_EXATO) { // como no Python: quadrado perfeito dá a raiz exata
      const r = raizInteira(x);
      if (r * r === x) return Number(r);
    }
    return Math.sqrt(finito(Number(x)));
  });
  nativa('potência', 2, 2, (vm, [a, b]) => opPow(exigeNumero('potência', 1, a), exigeNumero('potência', 2, b)));
  nativa('arredondar', 1, 2, (vm, a) => {
    const x = exigeNumero('arredondar', 1, a[0]);
    const casas = Number(exigeInteiro('arredondar', 2, opcional(a, 1, 0n)));
    if (typeof x === 'bigint') return x;
    if (!Number.isFinite(x)) throw erro('G322', 'Não é possível arredondar um valor infinito ou indefinido.');
    return casas <= 0 ? BigInt(arredondarTexto(x, 0)) : Number(arredondarTexto(x, casas));
  });
  nativa('piso', 1, 1, (vm, [x]) => {
    exigeNumero('piso', 1, x);
    if (typeof x === 'bigint') return x;
    if (!Number.isFinite(x)) throw erro('G322', 'Não é possível calcular o piso de um valor infinito ou indefinido.');
    return BigInt(Math.floor(x));
  });
  nativa('teto', 1, 1, (vm, [x]) => {
    exigeNumero('teto', 1, x);
    if (typeof x === 'bigint') return x;
    if (!Number.isFinite(x)) throw erro('G322', 'Não é possível calcular o teto de um valor infinito ou indefinido.');
    return BigInt(Math.ceil(x));
  });
  function valoresDe(fname, a) {
    const v = a.length === 1 && Array.isArray(a[0]) ? a[0] : a;
    if (!v.length) throw erro('G322', `A função ${fname}() precisa de pelo menos um valor.`);
    return v;
  }
  nativa('mínimo', 0, null, (vm, a) => valoresDe('mínimo', a).reduce((m, v) => (opCmp('<', v, m) ? v : m)));
  nativa('máximo', 0, null, (vm, a) => valoresDe('máximo', a).reduce((m, v) => (opCmp('<', m, v) ? v : m)));
  function somar(lista) {
    let total = 0n;
    lista.forEach((v, i) => {
      if (!isNum(v)) throw erro('G322', `A função soma() só soma números, mas o elemento ${i + 1} é ${artigo(typeName(v))}.`);
      total = opAdd(total, v);
    });
    return total;
  }
  nativa('soma', 1, 1, (vm, [l]) => somar(exigeLista('soma', 1, l)));
  nativa('média', 1, 1, (vm, [l]) => {
    exigeLista('média', 1, l);
    if (!l.length) throw erro('G322', 'Não é possível calcular a média de uma lista vazia.');
    return Number(somar(l)) / l.length;
  });
  nativa('aleatório', 0, 0, (vm) => vm.random.decimal());
  nativa('aleatório_entre', 2, 2, (vm, [a, b]) => {
    exigeInteiro('aleatório_entre', 1, a); exigeInteiro('aleatório_entre', 2, b);
    if (a > b) throw erro('G322', `Em aleatório_entre(${a}, ${b}), o primeiro valor não pode ser maior que o segundo.`);
    return vm.random.inteiroEntre(a, b);
  });
  nativa('semente_aleatória', 1, 1, (vm, [s]) => { vm.random.semear(exigeInteiro('semente_aleatória', 1, s)); return null; });
  function decimalFinito(fname, pos, x) {
    exigeNumero(fname, pos, x);
    const v = Number(x);
    if (typeof x === 'bigint' && !Number.isFinite(v)) {
      throw erro('G317', `O número passado para ${fname}() é grande demais para ser um decimal.`);
    }
    if (!Number.isFinite(v)) throw erro('G322', `A função ${fname}() não aceita valores infinitos ou indefinidos.`);
    return v;
  }
  nativa('seno', 1, 1, (vm, [x]) => senoExato(decimalFinito('seno', 1, x)));
  nativa('cosseno', 1, 1, (vm, [x]) => cossenoExato(decimalFinito('cosseno', 1, x)));
  nativa('tangente', 1, 1, (vm, [x]) => tangenteExata(decimalFinito('tangente', 1, x)));
  nativa('logaritmo', 1, 2, (vm, a) => {
    const x = decimalFinito('logaritmo', 1, a[0]);
    if (x <= 0) throw erro('G322', 'O logaritmo só existe para números maiores que zero.');
    if (a.length < 2 || a[1] === null) return logaritmoExato(x);
    const b = decimalFinito('logaritmo', 2, a[1]);
    if (b <= 0 || b === 1) throw erro('G322', 'A base do logaritmo deve ser maior que zero e diferente de 1.');
    return logaritmoBaseExato(x, b);
  });

  // -- coleções
  nativa('adicionar', 2, 2, (vm, [l, v]) => { exigeLista('adicionar', 1, l).push(v); return null; });
  nativa('inserir', 3, 3, (vm, [l, p, v]) => {
    exigeLista('inserir', 1, l); exigeInteiro('inserir', 2, p);
    if (p < 1n || p > BigInt(l.length + 1)) throw erro('G304', `Não é possível inserir na posição ${p}: as posições válidas vão de 1 a ${l.length + 1}.`);
    l.splice(Number(p) - 1, 0, v);
    return null;
  });
  nativa('remover', 2, 2, (vm, [l, p]) => { exigeLista('remover', 1, l); exigeInteiro('remover', 2, p); return l.splice(posicao(l.length, p, 'lista'), 1)[0]; });
  nativa('remover_valor', 2, 2, (vm, [l, v]) => {
    exigeLista('remover_valor', 1, l);
    const i = l.findIndex((x) => equals(x, v));
    if (i < 0) return false;
    l.splice(i, 1);
    return true;
  });
  nativa('ordenar', 1, 1, (vm, [l]) => { exigeLista('ordenar', 1, l); ordenaveis('ordenar', l); return l.slice().sort(comparar); });
  nativa('ordenar_por', 2, 2, (vm, [l, f]) => {
    exigeLista('ordenar_por', 1, l); exigeFuncao('ordenar_por', 2, f);
    const chaves = l.map((x) => vm.callValue(f, [x]));
    ordenaveis('ordenar_por', chaves);
    return l.map((x, i) => i).sort((i, j) => comparar(chaves[i], chaves[j]) || i - j).map((i) => l[i]);
  });
  nativa('copiar', 1, 1, (vm, [v]) => (Array.isArray(v) ? v.slice() : v instanceof Mapa ? v.copy() : v));
  nativa('intervalo', 2, 3, (vm, a) => Array.from(makeRange(a[0], a[1], opcional(a, 2, null))));
  nativa('nova_lista', 1, 2, (vm, a) => {
    const n = exigeInteiro('nova_lista', 1, a[0]);
    if (n < 0n) throw erro('G322', 'O tamanho de uma lista não pode ser negativo.');
    const v = opcional(a, 1, null);
    return Array.from({ length: Number(n) }, () => (Array.isArray(v) ? v.slice() : v instanceof Mapa ? v.copy() : v));
  });
  nativa('mapear', 2, 2, (vm, [l, f]) => { exigeLista('mapear', 1, l); exigeFuncao('mapear', 2, f); return l.slice().map((x) => vm.callValue(f, [x])); });
  nativa('filtrar', 2, 2, (vm, [l, f]) => {
    exigeLista('filtrar', 1, l); exigeFuncao('filtrar', 2, f);
    return l.slice().filter((x) => exigeBool(vm.callValue(f, [x]), 'O resultado da função passada para filtrar()'));
  });
  nativa('reduzir', 3, 3, (vm, [l, f, ini]) => { exigeLista('reduzir', 1, l); exigeFuncao('reduzir', 2, f); return l.slice().reduce((acc, x) => vm.callValue(f, [acc, x]), ini); });
  nativa('algum', 2, 2, (vm, [l, f]) => exigeLista('algum', 1, l).slice().some((x) => exigeBool(vm.callValue(exigeFuncao('algum', 2, f), [x]), 'O resultado da função passada para algum()')));
  nativa('todos', 2, 2, (vm, [l, f]) => exigeLista('todos', 1, l).slice().every((x) => exigeBool(vm.callValue(exigeFuncao('todos', 2, f), [x]), 'O resultado da função passada para todos()')));
  nativa('primeiro', 1, 1, (vm, [l]) => { exigeLista('primeiro', 1, l); if (!l.length) throw erro('G304', 'A lista está vazia: não há primeiro elemento.'); return l[0]; });
  nativa('último', 1, 1, (vm, [l]) => { exigeLista('último', 1, l); if (!l.length) throw erro('G304', 'A lista está vazia: não há último elemento.'); return l[l.length - 1]; });
  nativa('contar', 2, 2, (vm, [c, v]) => {
    if (Array.isArray(c)) return BigInt(c.filter((x) => equals(x, v)).length);
    if (typeof c === 'string') {
      exige('contar', 2, v, 'texto');
      if (v === '') throw erro('G322', 'A função contar() não aceita um texto vazio como trecho procurado.');
      return BigInt(c.split(v).length - 1);
    }
    throw erro('G322', `A função contar() espera uma lista ou um texto, mas recebeu ${artigo(typeName(c))}.`);
  });
  nativa('limpar', 1, 1, (vm, [c]) => { exige('limpar', 1, c, 'lista', 'mapa'); if (Array.isArray(c)) c.length = 0; else c.clear(); return null; });
  nativa('vazio', 1, 1, (vm, [c]) => { exige('vazio', 1, c, 'lista', 'texto', 'mapa'); return (c instanceof Mapa ? c.size : c.length) === 0; });
  nativa('chaves', 1, 1, (vm, [m]) => exigeMapa('chaves', 1, m).keys());
  nativa('valores', 1, 1, (vm, [m]) => exigeMapa('valores', 1, m).values());
  nativa('pares', 1, 1, (vm, [m]) => exigeMapa('pares', 1, m).items().map(([k, v]) => [k, v]));
  nativa('obter', 2, 3, (vm, a) => {
    const [c, k] = a; const padrao = opcional(a, 2, null);
    if (c instanceof Mapa) { const v = c.has(k) ? c.get(k) : MISSING; return v === MISSING ? padrao : v; }
    if (Array.isArray(c)) {
      if (typeof k === 'bigint' && k !== 0n && -BigInt(c.length) <= k && k <= BigInt(c.length)) return c[k > 0n ? Number(k) - 1 : c.length + Number(k)];
      return padrao;
    }
    throw erro('G322', `A função obter() espera um mapa ou uma lista, mas recebeu ${artigo(typeName(c))}.`);
  });
  nativa('remover_chave', 2, 2, (vm, [m, k]) => { exigeMapa('remover_chave', 1, m); const v = m.has(k) ? m.delete(k) : MISSING; return v === MISSING ? null : v; });

  // -- conversão
  nativa('texto', 1, 1, (vm, [v]) => display(v));
  nativa('inteiro', 1, 1, (vm, [v]) => {
    if (typeof v === 'bigint') return v;
    if (typeof v === 'number') { if (!Number.isFinite(v)) throw erro('G312', 'Não é possível converter um valor infinito ou indefinido em inteiro.'); return BigInt(Math.trunc(v)); }
    if (typeof v === 'boolean') return v ? 1n : 0n;
    if (typeof v === 'string') {
      const n = lerNumero(v);
      if (typeof n === 'bigint') return n;
      if (typeof n === 'number') throw erro('G312', `O texto ${repr(v)} representa um número decimal, não um inteiro.`, 'Use decimal(...) para obter o número decimal, ou arredondar(número(...)).');
      throw erro('G312', `Não foi possível converter o texto ${repr(v)} em inteiro.`, 'Verifique se o texto contém apenas dígitos, como "42". Use é_número(texto) para validar antes.');
    }
    throw erro('G312', `Não é possível converter ${artigo(typeName(v))} em inteiro.`);
  });
  nativa('decimal', 1, 1, (vm, [v]) => {
    if (isNum(v)) return Number(v);
    if (typeof v === 'string') {
      const n = lerNumero(v);
      if (n === null) throw erro('G312', `Não foi possível converter o texto ${repr(v)} em decimal.`, 'Use um texto como "3.5" ou "3,5". Use é_número(texto) para validar antes.');
      return Number(n);
    }
    throw erro('G312', `Não é possível converter ${artigo(typeName(v))} em decimal.`);
  });
  nativa('número', 1, 1, (vm, [v]) => {
    if (isNum(v)) return v;
    if (typeof v === 'string') {
      const n = lerNumero(v);
      if (n === null) throw erro('G312', `Não foi possível converter o texto ${repr(v)} em número.`, 'Use é_número(texto) para verificar antes de converter.');
      return n;
    }
    throw erro('G312', `Não é possível converter ${artigo(typeName(v))} em número.`);
  });
  nativa('booleano', 1, 1, (vm, [v]) => {
    if (typeof v === 'boolean') return v;
    if (typeof v === 'string') {
      const s = v.trim().toLowerCase();
      if (s === 'verdadeiro') return true;
      if (s === 'falso') return false;
      throw erro('G312', `Não foi possível converter o texto ${repr(v)} em booleano.`, 'Apenas os textos "verdadeiro" e "falso" podem ser convertidos.');
    }
    throw erro('G312', `Não é possível converter ${artigo(typeName(v))} em booleano.`, 'Para testar um número, use uma comparação, como x != 0.');
  });
  nativa('tipo', 1, 1, (vm, [v]) => typeName(v));

  // -- JSON (com distinção entre inteiro e decimal, como no servidor)
  function paraJSON(v, indent, nivel, caminho, vistos) {
    switch (typeof v) {
      case 'bigint': return v.toString();
      case 'number':
        if (!Number.isFinite(v)) throw erro('G323', `${caminho} é ${display(v)}, que não pode ser representado em JSON.`);
        return fmtDecimal(v);
      case 'string': return JSON.stringify(v);
      case 'boolean': return v ? 'true' : 'false';
    }
    if (v === null) return 'null';
    let pares;
    if (Array.isArray(v)) pares = v.map((x, i) => [null, x, `${caminho}[${i + 1}]`]);
    else if (v instanceof Mapa) {
      pares = v.items().map(([k, x]) => {
        let chave;
        if (typeof k === 'string') chave = k;
        else if (isNum(k)) chave = display(k);
        else throw erro('G323', `A chave ${display(k)} de ${caminho} não pode ser usada em JSON (use textos como chaves).`);
        return [chave, x, `${caminho}[${JSON.stringify(chave)}]`];
      });
    } else if (v instanceof Registro) pares = v.tipo.fields.map((f, i) => [f, v.valores[i], `${caminho}.${f}`]);
    else throw erro('G323', `${caminho} é ${artigo(typeName(v))}, que não pode ser convertido em JSON.`);
    if (vistos.has(v)) throw erro('G323', `${caminho} contém a si mesmo e não pode ser convertido em JSON.`);
    vistos.add(v);
    try {
      const objeto = !Array.isArray(v);
      const [abre, fecha] = objeto ? ['{', '}'] : ['[', ']'];
      if (!pares.length) return abre + fecha;
      const itens = pares.map(([k, x, c]) => (objeto ? JSON.stringify(k) + (indent ? ': ' : ':') : '') + paraJSON(x, indent, nivel + 1, c, vistos));
      if (!indent) return abre + itens.join(',') + fecha;
      const pad = ' '.repeat(indent * (nivel + 1));
      return abre + '\n' + itens.map((s) => pad + s).join(',\n') + '\n' + ' '.repeat(indent * nivel) + fecha;
    } finally { vistos.delete(v); }
  }
  function codificarJSON(v, indent) { return paraJSON(v, indent || 0, 0, 'valor', new Set()); }

  function decodificarJSON(texto) {
    let p = 0;
    const falha = (msg) => {
      const antes = texto.slice(0, p);
      const linha = antes.split('\n').length;
      const coluna = p - antes.lastIndexOf('\n');
      return erro('G323', `JSON inválido na linha ${linha}, coluna ${coluna}: ${msg}.`, 'Confira aspas, vírgulas e chaves. Textos JSON usam aspas duplas.');
    };
    const espacos = () => { while (p < texto.length && ' \t\n\r'.includes(texto[p])) p++; };
    function valor() {
      espacos();
      const c = texto[p];
      if (c === '{') {
        p++; const m = new Mapa(); espacos();
        if (texto[p] === '}') { p++; return m; }
        for (;;) {
          espacos();
          if (texto[p] !== '"') throw falha('esperava o nome de um campo entre aspas duplas');
          const k = cadeia(); espacos();
          if (texto[p] !== ':') throw falha("esperava ':'");
          p++; m.set(k, valor()); espacos();
          if (texto[p] === ',') { p++; continue; }
          if (texto[p] === '}') { p++; return m; }
          throw falha('esperava uma vírgula');
        }
      }
      if (c === '[') {
        p++; const l = []; espacos();
        if (texto[p] === ']') { p++; return l; }
        for (;;) {
          l.push(valor()); espacos();
          if (texto[p] === ',') { p++; continue; }
          if (texto[p] === ']') { p++; return l; }
          throw falha('esperava uma vírgula');
        }
      }
      if (c === '"') return cadeia();
      if (texto.startsWith('true', p)) { p += 4; return true; }
      if (texto.startsWith('false', p)) { p += 5; return false; }
      if (texto.startsWith('null', p)) { p += 4; return null; }
      const m = /^-?(?:0|[1-9]\d*)(\.\d+)?([eE][+-]?\d+)?/.exec(texto.slice(p));
      if (!m) throw falha('esperava um valor');
      p += m[0].length;
      return m[1] || m[2] ? Number(m[0]) : BigInt(m[0]);
    }
    function cadeia() {
      const m = /^"(?:[^"\\\u0000-\u001f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*"/.exec(texto.slice(p));
      if (!m) throw falha('texto não fechado');
      p += m[0].length;
      return JSON.parse(m[0]);
    }
    const r = valor(); espacos();
    if (p < texto.length) throw falha('há conteúdo depois do fim do JSON');
    return r;
  }
  nativa('para_json', 1, 2, (vm, a) => {
    const ind = opcional(a, 1, null);
    if (ind !== null && typeof ind !== 'bigint') throw erro('G322', 'A indentação de para_json() deve ser um inteiro.');
    return codificarJSON(a[0], ind === null ? 0 : Number(ind));
  });
  nativa('de_json', 1, 1, (vm, [t]) => decodificarJSON(exigeTexto('de_json', 1, t)));

  // -- codificação e identificadores
  nativa('escapar_html', 1, 1, (vm, [t]) => display(t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#x27;'));
  nativa('codificar_url', 1, 1, (vm, [t]) => encodeURIComponent(exigeTexto('codificar_url', 1, t)));
  nativa('decodificar_url', 1, 1, (vm, [t]) => decodeURIComponent(exigeTexto('decodificar_url', 1, t)));
  const B64 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  nativa('codificar_base64', 1, 1, (vm, [t]) => {
    const b = new TextEncoder().encode(exigeTexto('codificar_base64', 1, t));
    let s = '';
    for (let i = 0; i < b.length; i += 3) {
      const n = (b[i] << 16) | ((b[i + 1] || 0) << 8) | (b[i + 2] || 0);
      s += B64[(n >> 18) & 63] + B64[(n >> 12) & 63] + (i + 1 < b.length ? B64[(n >> 6) & 63] : '=') + (i + 2 < b.length ? B64[n & 63] : '=');
    }
    return s;
  });
  nativa('decodificar_base64', 1, 1, (vm, [t]) => {
    exigeTexto('decodificar_base64', 1, t);
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(t) || t.length % 4) throw erro('G312', 'O texto não é um Base64 válido.');
    const bytes = [];
    for (let i = 0; i < t.length; i += 4) {
      const n = (B64.indexOf(t[i]) << 18) | (B64.indexOf(t[i + 1]) << 12) | ((B64.indexOf(t[i + 2]) & 63) << 6) | (B64.indexOf(t[i + 3]) & 63);
      bytes.push((n >> 16) & 255); if (t[i + 2] !== '=') bytes.push((n >> 8) & 255); if (t[i + 3] !== '=') bytes.push(n & 255);
    }
    try { return new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(bytes)); } catch (e) { throw erro('G312', 'O texto não é um Base64 válido.'); }
  });
  function bytesAleatorios(n) {
    const b = new Uint8Array(n);
    if (global.crypto && global.crypto.getRandomValues) global.crypto.getRandomValues(b);
    else for (let i = 0; i < n; i++) b[i] = Math.floor(Math.random() * 256);
    return b;
  }
  nativa('uuid', 0, 0, () => {
    const b = bytesAleatorios(16); b[6] = (b[6] & 0x0f) | 0x40; b[8] = (b[8] & 0x3f) | 0x80;
    const h = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
  });
  nativa('token_aleatório', 0, 1, (vm, a) => {
    const n = Number(exigeInteiro('token_aleatório', 1, opcional(a, 0, 32n)));
    if (n < 8 || n > 1024) throw erro('G322', 'O tamanho do token deve estar entre 8 e 1024 bytes.');
    return Array.from(bytesAleatorios(n), (x) => B64[x & 63].replace('+', '-').replace('/', '_')).join('');
  });

  // -- tempo
  const DIAS = ['domingo', 'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado'];
  const dois = (n) => String(n).padStart(2, '0');
  nativa('agora', 0, 0, () => {
    const d = new Date();
    return Mapa.de([['ano', BigInt(d.getFullYear())], ['mês', BigInt(d.getMonth() + 1)], ['dia', BigInt(d.getDate())],
      ['hora', BigInt(d.getHours())], ['minuto', BigInt(d.getMinutes())], ['segundo', BigInt(d.getSeconds())],
      ['dia_da_semana', DIAS[d.getDay()]]]);
  });
  nativa('data_atual', 0, 0, () => { const d = new Date(); return `${dois(d.getDate())}/${dois(d.getMonth() + 1)}/${d.getFullYear()}`; });
  nativa('hora_atual', 0, 0, () => { const d = new Date(); return `${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`; });
  nativa('tempo', 0, 0, () => Date.now() / 1000);
  nativa('data_hora_iso', 0, 1, (vm, a) => {
    const d = a.length && a[0] !== null ? new Date(Number(exigeNumero('data_hora_iso', 1, a[0])) * 1000) : new Date();
    return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}T${dois(d.getHours())}:${dois(d.getMinutes())}:${dois(d.getSeconds())}`;
  });

  // -- sistema
  nativa('argumentos', 0, 0, () => []);
  nativa('afirmar', 1, 2, (vm, a) => {
    if (!exigeBool(a[0], 'A condição de afirmar()')) throw erro('G329', `Verificação falhou: ${display(opcional(a, 1, 'a condição é falsa'))}.`);
    return null;
  });
  nativa('sair', 0, 1, (vm, a) => { throw new GaloSaida(Number(exigeInteiro('sair', 1, opcional(a, 0, 0n)))); });

  // -- página (somente navegador)
  function semDocumento(nome) {
    if (typeof document === 'undefined') {
      throw erro('G327', `A função ${nome}() só está disponível quando o programa roda no navegador.`);
    }
  }
  const EVENTOS = { clique: 'click', duplo_clique: 'dblclick', envio: 'submit', mudanca: 'change', entrada: 'input',
    tecla: 'keydown', foco: 'focus', carregar: 'load', passar_o_mouse: 'mouseover' };
  const cacheElementos = new WeakMap();
  function envolver(el) {
    if (!el) return null;
    let o = cacheElementos.get(el);
    if (o) return o;
    o = new ObjetoNativo('Elemento', el);
    const elem = (v, f, p) => { if (!(v instanceof ObjetoNativo) || v.tipo !== 'Elemento') throw erro('G322', `${f}() espera um Elemento no argumento ${p}, mas recebeu ${artigo(typeName(v))}.`); return v.dados; };
    o.propriedade('texto', () => el.textContent, (v) => { el.textContent = display(v); });
    o.propriedade('html', () => el.innerHTML, (v) => { el.innerHTML = display(v); });
    o.propriedade('valor', () => (el.value === undefined ? null : el.value), (v) => { el.value = v === null ? '' : display(v); });
    o.propriedade('marcado', () => !!el.checked, (v) => { el.checked = exigeBool(v, 'O valor de marcado'); });
    o.propriedade('etiqueta', () => String(el.tagName || '').toLowerCase());
    o.propriedade('filhos', () => Array.from(el.children || [], envolver));
    o.metodo('ao', (vm, _o, [evento, fn]) => {
      exigeTexto('ao', 1, evento); exigeFuncao('ao', 2, fn);
      const nome = EVENTOS[canonical(evento)] || evento;
      el.addEventListener(nome, (e) => {
        if (nome === 'submit' && e.preventDefault) e.preventDefault();
        const info = Mapa.de([['tipo', e.type || nome], ['alvo', envolver(e.target || el)],
          ['tecla', e.key === undefined ? null : e.key], ['valor', e.target && e.target.value !== undefined ? e.target.value : null],
          ['ctrl', !!e.ctrlKey], ['shift', !!e.shiftKey], ['alt', !!e.altKey], ['meta', !!e.metaKey]]);
        const aridade = fn instanceof Closure ? fn.code.params.length : (fn instanceof MetodoLigado ? fn.funcao.code.params.length - 1 : 1);
        vm.chamarDeFora(fn, aridade === 0 ? [] : [info]);
      });
      return null;
    }, 2, 2);
    o.metodo('adicionar', (vm, _o, [filho]) => {
      el.appendChild(typeof filho === 'string' ? document.createTextNode(filho) : elem(filho, 'adicionar', 1));
      return null;
    }, 1, 1);
    o.metodo('remover', () => { el.remove(); return null; }, 0, 0);
    o.metodo('limpar', () => { el.textContent = ''; return null; }, 0, 0);
    o.metodo('atributo', (vm, _o, [n]) => { const v = el.getAttribute(exigeTexto('atributo', 1, n)); return v === undefined ? null : v; }, 1, 1);
    o.metodo('definir_atributo', (vm, _o, [n, v]) => { el.setAttribute(exigeTexto('definir_atributo', 1, n), display(v)); return null; }, 2, 2);
    o.metodo('remover_atributo', (vm, _o, [n]) => { el.removeAttribute(exigeTexto('remover_atributo', 1, n)); return null; }, 1, 1);
    o.metodo('adicionar_classe', (vm, _o, [c]) => { el.classList.add(exigeTexto('adicionar_classe', 1, c)); return null; }, 1, 1);
    o.metodo('remover_classe', (vm, _o, [c]) => { el.classList.remove(exigeTexto('remover_classe', 1, c)); return null; }, 1, 1);
    o.metodo('alternar_classe', (vm, _o, [c]) => el.classList.toggle(exigeTexto('alternar_classe', 1, c)), 1, 1);
    o.metodo('tem_classe', (vm, _o, [c]) => el.classList.contains(exigeTexto('tem_classe', 1, c)), 1, 1);
    o.metodo('procurar', (vm, _o, [s]) => envolver(el.querySelector(exigeTexto('procurar', 1, s))), 1, 1);
    o.metodo('procurar_todos', (vm, _o, [s]) => Array.from(el.querySelectorAll(exigeTexto('procurar_todos', 1, s)), envolver), 1, 1);
    o.metodo('focar', () => { el.focus(); return null; }, 0, 0);
    o.metodo('estilo', (vm, _o, [p, v]) => { el.style.setProperty(exigeTexto('estilo', 1, p), display(v)); return null; }, 2, 2);
    cacheElementos.set(el, o);
    return o;
  }
  const seletor = (f, s) => exigeTexto(f, 1, s);
  nativa('elemento', 1, 1, (vm, [s]) => { semDocumento('elemento'); try { return envolver(document.querySelector(seletor('elemento', s))); } catch (e) { if (e instanceof GaloErro) throw e; throw erro('G322', `Seletor CSS inválido: "${s}".`); } });
  nativa('elementos', 1, 1, (vm, [s]) => { semDocumento('elementos'); try { return Array.from(document.querySelectorAll(seletor('elementos', s)), envolver); } catch (e) { if (e instanceof GaloErro) throw e; throw erro('G322', `Seletor CSS inválido: "${s}".`); } });
  nativa('criar_elemento', 1, 2, (vm, a) => {
    semDocumento('criar_elemento');
    const el = document.createElement(exigeTexto('criar_elemento', 1, a[0]));
    if (a.length > 1 && a[1] !== null) el.textContent = display(a[1]);
    return envolver(el);
  });
  nativa('depois', 2, 2, (vm, [ms, f]) => BigInt(setTimeout(() => vm.chamarDeFora(exigeFuncao('depois', 2, f), []), Number(exigeNumero('depois', 1, ms)))));
  nativa('a_cada', 2, 2, (vm, [ms, f]) => BigInt(setInterval(() => vm.chamarDeFora(exigeFuncao('a_cada', 2, f), []), Number(exigeNumero('a_cada', 1, ms)))));
  nativa('cancelar_temporizador', 1, 1, (vm, [id]) => { clearTimeout(Number(id)); clearInterval(Number(id)); return null; });
  function armazem(f) { if (typeof localStorage === 'undefined') throw erro('G327', `A função ${f}() só está disponível no navegador.`); return localStorage; }
  nativa('armazenar', 2, 2, (vm, [k, v]) => { armazem('armazenar').setItem(exigeTexto('armazenar', 1, k), codificarJSON(v)); return null; });
  nativa('recuperar', 1, 2, (vm, a) => {
    const t = armazem('recuperar').getItem(exigeTexto('recuperar', 1, a[0]));
    if (t === null) return opcional(a, 1, null);
    try { return decodificarJSON(t); } catch (e) { return opcional(a, 1, null); }
  });
  nativa('esquecer', 1, 1, (vm, [k]) => { armazem('esquecer').removeItem(exigeTexto('esquecer', 1, k)); return null; });
  nativa('alerta', 1, 1, (vm, [m]) => { semDocumento('alerta'); alert(display(m)); return null; });
  nativa('confirmar', 1, 1, (vm, [m]) => { semDocumento('confirmar'); return !!confirm(display(m)); });
  nativa('navegar', 1, 1, (vm, [u]) => { semDocumento('navegar'); global.location.href = exigeTexto('navegar', 1, u); return null; });
  nativa('endereço_atual', 0, 0, () => { semDocumento('endereço_atual'); return String(global.location.href); });

  function respostaHTTP(status, corpo, cabecalhos, erroRede) {
    const cab = new Mapa();
    if (cabecalhos) cabecalhos.forEach((v, k) => cab.set(k.toLowerCase(), v));
    const tipo = cab.has('content-type') ? cab.get('content-type') : '';
    let json = null;
    if (typeof tipo === 'string' && tipo.includes('json') && corpo.trim()) { try { json = decodificarJSON(corpo); } catch (e) { json = null; } }
    const m = Mapa.de([['status', BigInt(status)], ['ok', status >= 200 && status < 300], ['corpo', corpo], ['cabeçalhos', cab], ['json', json]]);
    if (erroRede) m.set('erro', erroRede);
    return m;
  }
  nativa('buscar', 3, 3, (vm, [url, opcoes, f]) => {
    exigeTexto('buscar', 1, url); exigeFuncao('buscar', 3, f);
    if (typeof fetch !== 'function') throw erro('G327', 'A função buscar() precisa de um navegador com fetch.');
    const o = opcoes === null ? new Mapa() : exigeMapa('buscar', 2, opcoes);
    const obterOpcao = (...ns) => { for (const n of ns) { const v = o.get(n); if (v !== MISSING) return v; } return null; };
    const init = { method: String(obterOpcao('método', 'metodo') || 'GET').toUpperCase(), headers: {} };
    const cab = obterOpcao('cabeçalhos', 'cabecalhos');
    if (cab instanceof Mapa) for (const [k, v] of cab.items()) init.headers[String(k)] = display(v);
    if (obterOpcao('json') !== null) { init.body = codificarJSON(obterOpcao('json')); init.headers['Content-Type'] = init.headers['Content-Type'] || 'application/json'; }
    else if (obterOpcao('corpo') !== null) {
      const c = obterOpcao('corpo');
      if (typeof c === 'string') init.body = c; else { init.body = codificarJSON(c); init.headers['Content-Type'] = init.headers['Content-Type'] || 'application/json'; }
    }
    fetch(url, init).then(
      (r) => r.text().then((corpo) => vm.chamarDeFora(f, [respostaHTTP(r.status, corpo, r.headers)])),
      (e) => vm.chamarDeFora(f, [respostaHTTP(0, '', null, `Não foi possível acessar "${url}": ${e.message}`)])
    );
    return null;
  });

  // -- GALO dentro da GALO: executar_programa roda um programa compilado (compilar_programa, no
  // servidor) isolado num Web Worker: a página não trava, e um programa que passa do tempo é
  // interrompido encerrando o worker. Sem Worker (gjs, Node), executa aqui mesmo, sem limite de tempo.
  const URL_GALO_JS = (typeof document !== 'undefined' && document.currentScript && document.currentScript.src) || null;
  const LIMITE_SAIDA = 1 << 20;

  function bytesDeBase64(t) {
    if (!/^[A-Za-z0-9+/]*={0,2}$/.test(t) || t.length % 4) throw erro('G312', 'O bytecode não é um Base64 válido.');
    const n = (t.length / 4) * 3 - (t.endsWith('==') ? 2 : t.endsWith('=') ? 1 : 0);
    const b = new Uint8Array(n);
    let j = 0;
    for (let i = 0; i < t.length; i += 4) {
      const v = (B64.indexOf(t[i]) << 18) | (B64.indexOf(t[i + 1]) << 12) | ((B64.indexOf(t[i + 2]) & 63) << 6) | (B64.indexOf(t[i + 3]) & 63);
      if (j < n) b[j++] = (v >> 16) & 255;
      if (j < n) b[j++] = (v >> 8) & 255;
      if (j < n) b[j++] = v & 255;
    }
    return b;
  }
  function erroParaObjeto(e) {
    return { codigo: e.codigo, mensagem: e.mensagem, linha: e.linha, coluna: e.coluna, sugestao: e.sugestao, texto: formatarErro(e) };
  }
  // Executa o bytecode numa VM nova; envia {tipo: 'saida', texto} em lotes e, no fim, {tipo: 'fim', erro, tempo}.
  function rodarIsolado(bytes, entradas, enviar) {
    // As primeiras escritas vão na hora (se o programa travar depois, nada se perde); quem escreve
    // muito tem a saída enviada em lotes, para não inundar a página de mensagens.
    let total = 0, lote = '', envios = 0, ultimoEnvio = 0;
    const descarregar = () => { if (lote) { enviar({ tipo: 'saida', texto: lote }); lote = ''; envios++; } ultimoEnvio = Date.now(); };
    const escrever = (t) => {
      total += t.length;
      if (total > LIMITE_SAIDA) {
        throw erro('G331', 'O programa escreveu mais de 1 MB e foi interrompido.', 'Mostre menos linhas, ou só um resumo dos resultados.');
      }
      lote += t;
      if (envios < 200 || lote.length > 4096 || Date.now() - ultimoEnvio > 40) descarregar();
    };
    const fila = Array.from(entradas || [], (v) => display(v));
    let erroFinal = null;
    const vm = new VM({
      escrever,
      ler: (pergunta) => {
        const v = fila.length ? fila.shift() : null;
        if (pergunta) escrever(pergunta);
        if (v !== null) escrever(v + '\n'); // eco da entrada, como no terminal
        return v;
      },
      aoErro: (e) => { erroFinal = e; },
    });
    const inicio = Date.now();
    try {
      vm.run(carregar(bytes));
    } catch (e) {
      if (e instanceof GaloErro) erroFinal = e;
      else if (!(e instanceof GaloSaida)) erroFinal = erro('G320', `O programa não pôde continuar: ${e && e.message ? e.message : e}.`);
    }
    descarregar();
    enviar({ tipo: 'fim', erro: erroFinal ? erroParaObjeto(erroFinal) : null, tempo: (Date.now() - inicio) / 1000 });
  }
  function novoTrabalhador() {
    if (typeof Worker === 'undefined' || typeof Blob === 'undefined' || typeof URL === 'undefined' || !URL_GALO_JS) return null;
    const codigo = `importScripts(${JSON.stringify(URL_GALO_JS)});\n` +
      'onmessage = (m) => Galo._internos.rodarIsolado(new Uint8Array(m.data.bytes), m.data.entradas, (d) => postMessage(d));\n';
    try { return new Worker(URL.createObjectURL(new Blob([codigo], { type: 'text/javascript' }))); } catch (e) { return null; }
  }
  nativa('executar_programa', 3, 3, (vm, [bc, opcoes, f]) => {
    exigeTexto('executar_programa', 1, bc); exigeFuncao('executar_programa', 3, f);
    const o = opcoes === null ? new Mapa() : exigeMapa('executar_programa', 2, opcoes);
    const opcao = (n, padrao) => { const v = o.get(n); return v === MISSING || v === null ? padrao : v; };
    const entradas = exigeLista('executar_programa', 2, opcao('entradas', []));
    const limite = Number(exigeNumero('executar_programa', 2, opcao('limite_segundos', 5n)));
    const aoEscrever = opcao('ao_escrever', null);
    if (aoEscrever !== null) exigeFuncao('executar_programa', 2, aoEscrever);
    const bytes = bytesDeBase64(bc);
    carregar(bytes); // bytecode inválido é recusado aqui (G502/G503), antes de criar o worker
    let saida = '';
    const concluir = (e, tempo, interrompido) => vm.chamarDeFora(f, [Mapa.de([
      ['saída', saida], ['tempo', tempo], ['interrompido', interrompido],
      ['erro', e === null ? null : Mapa.de([['código', e.codigo], ['mensagem', e.mensagem],
        ['linha', e.linha == null ? null : BigInt(e.linha)], ['coluna', e.coluna == null ? null : BigInt(e.coluna)],
        ['sugestão', e.sugestao || null], ['texto', e.texto]])],
    ])]);
    const receber = (d) => {
      saida += d.texto;
      if (aoEscrever !== null) vm.chamarDeFora(aoEscrever, [d.texto]);
    };
    const t = novoTrabalhador();
    if (t === null) {
      rodarIsolado(bytes, entradas, (d) => { if (d.tipo === 'fim') concluir(d.erro, d.tempo, false); else receber(d); });
      return null;
    }
    const inicio = Date.now();
    let terminou = false;
    const encerrar = () => { terminou = true; clearTimeout(relogio); t.terminate(); };
    const relogio = setTimeout(() => {
      if (terminou) return;
      encerrar();
      const segundos = Number.isInteger(limite) ? String(limite) : fmtDecimal(limite);
      const e = erro('G330', `O programa passou de ${segundos} segundo${limite === 1 ? '' : 's'} e foi interrompido.`,
        'Confira se algum laço (enquanto, repita, recursão) nunca termina.');
      concluir(erroParaObjeto(e), (Date.now() - inicio) / 1000, true);
    }, limite * 1000);
    t.onmessage = (m) => {
      if (terminou) return;
      if (m.data.tipo === 'fim') { encerrar(); concluir(m.data.erro, m.data.tempo, false); } else receber(m.data);
    };
    t.onerror = (ev) => {
      if (ev && ev.preventDefault) ev.preventDefault();
      if (terminou) return;
      encerrar();
      concluir(erroParaObjeto(erro('G320', `Não foi possível executar o programa: ${(ev && ev.message) || 'falha no worker'}.`)),
        (Date.now() - inicio) / 1000, false);
    };
    t.postMessage({ bytes: bytes.buffer, entradas: Array.from(entradas, (v) => display(v)) }, [bytes.buffer]);
    return null;
  });

  // ------------------------------------------------------------------ saída, erros na página e carregamento

  function saidaPadrao() {
    let pendente = '';
    return function (texto) {
      pendente += texto;
      let i;
      while ((i = pendente.indexOf('\n')) >= 0) {
        const linha = pendente.slice(0, i);
        pendente = pendente.slice(i + 1);
        if (typeof console !== 'undefined') console.log(linha);
        const alvo = typeof document !== 'undefined' && document.getElementById('galo-saida');
        if (alvo) alvo.textContent += linha + '\n';
      }
    };
  }

  function mostrarErro(e) {
    const texto = formatarErro(e);
    if (typeof console !== 'undefined') console.error(texto);
    if (typeof document === 'undefined' || !document.body) return;
    let caixa = document.getElementById('galo-erro');
    if (!caixa) {
      caixa = document.createElement('pre');
      caixa.id = 'galo-erro';
      caixa.style.cssText = 'position:fixed;left:1rem;right:1rem;bottom:1rem;max-height:45vh;overflow:auto;margin:0;' +
        'padding:1rem;background:#fff5f5;color:#7a0000;border:2px solid #c00;border-radius:8px;' +
        'font:13px/1.4 monospace;white-space:pre-wrap;z-index:2147483647;box-shadow:0 4px 18px rgba(0,0,0,.2)';
      caixa.title = 'Clique para fechar';
      caixa.addEventListener('click', () => caixa.remove());
      document.body.appendChild(caixa);
    }
    caixa.textContent = texto;
  }

  function executarModulo(modulo, opcoes = {}) {
    const vm = new VM(opcoes);
    try {
      vm.run(modulo);
    } catch (e) {
      if (e instanceof GaloSaida) return vm;
      if (e instanceof GaloErro) { vm.aoErro(e); return vm; }
      throw e;
    }
    return vm;
  }

  async function executar(fonte, opcoes = {}) {
    let dados = fonte;
    if (typeof fonte === 'string') {
      const r = await fetch(fonte, { cache: 'no-cache' });
      if (!r.ok) {
        const corpo = await r.text();
        const e = erro('G501', `Não foi possível carregar o programa "${fonte}" (status ${r.status}).`);
        if (corpo) e.sugestao = corpo.slice(0, 4000);
        (opcoes.aoErro || mostrarErro)(e);
        return null;
      }
      dados = await r.arrayBuffer();
    }
    let modulo;
    try { modulo = carregar(dados); } catch (e) { (opcoes.aoErro || mostrarErro)(e); return null; }
    return executarModulo(modulo, opcoes);
  }

  function iniciarAutomatico() {
    if (typeof document === 'undefined') return;
    const rodar = () => {
      document.querySelectorAll('script[type="application/galo"][src]').forEach((s) => { executar(s.getAttribute('src')); });
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', rodar); else rodar();
  }

  global.Galo = {
    versao: VERSAO, carregar, executar, executarModulo, VM, formatarErro, OP, canonical,
    _internos: { BUILTINS, SOMENTE_SERVIDOR, fmtDecimal, repr, display, codificarJSON, decodificarJSON, Mapa, envolver, rodarIsolado },
  };
  iniciarAutomatico();
})(typeof window !== 'undefined' ? window : globalThis);
