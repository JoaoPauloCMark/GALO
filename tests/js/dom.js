// DOM mínimo simulado para testar galo.js sem navegador.
class Classes {
  constructor() { this.s = new Set(); }
  add(c) { this.s.add(c); } remove(c) { this.s.delete(c); } contains(c) { return this.s.has(c); }
  toggle(c) { if (this.s.has(c)) { this.s.delete(c); return false; } this.s.add(c); return true; }
}
class Texto { constructor(t) { this.textContent = t; this.parent = null; } }
class Elemento {
  constructor(tag) {
    this.tagName = tag.toUpperCase(); this.children = []; this.nodes = []; this._texto = ''; this.attrs = {};
    this.listeners = {}; this.classList = new Classes(); this.style = { setProperty(p, v) { this[p] = v; } };
    this.parent = null; this.value = ''; this.checked = false;
  }
  get textContent() { return this.nodes.length ? this.nodes.map((n) => n.textContent).join('') : this._texto; }
  set textContent(v) { this.nodes = []; this.children = []; this._texto = String(v); }
  get innerHTML() { return this.textContent; }
  set innerHTML(v) { this.textContent = v; }
  appendChild(c) { c.parent = this; this.nodes.push(c); if (c instanceof Elemento) this.children.push(c); return c; }
  remove() { const p = this.parent; if (p) { p.nodes = p.nodes.filter((x) => x !== this); p.children = p.children.filter((x) => x !== this); } }
  addEventListener(n, f) { (this.listeners[n] = this.listeners[n] || []).push(f); }
  disparar(n, extra = {}) {
    const ev = Object.assign({ type: n, target: this, prevented: false, preventDefault() { this.prevented = true; } }, extra);
    (this.listeners[n] || []).forEach((f) => f(ev));
    return ev;
  }
  setAttribute(n, v) { this.attrs[n] = String(v); }
  getAttribute(n) { return n in this.attrs ? this.attrs[n] : null; }
  removeAttribute(n) { delete this.attrs[n]; }
  corresponde(sel) {
    if (sel.startsWith('#')) return this.attrs.id === sel.slice(1);
    if (sel.startsWith('.')) return this.classList.contains(sel.slice(1));
    return this.tagName === sel.toUpperCase();
  }
  querySelectorAll(sel) {
    const out = [];
    const andar = (e) => { for (const c of e.children) { if (c.corresponde(sel)) out.push(c); andar(c); } };
    andar(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  focus() { this.focado = true; }
}
globalThis.DomFalso = { Elemento, Texto, Classes };
