/* Pocket Lexicon core: fully offline lookup for English, Hindi, Marathi, Urdu.
   Works in the app WebView and in Node (for tests). The caller supplies load(name) -> Promise<object|null>
   which returns the data shard registered under that name (see tools/build_lexicon.py). */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.LexiconCore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var NAT = ['hi', 'mr', 'ur'];
  var LANG_NAME = { en: 'English', hi: 'Hindi', mr: 'Marathi', ur: 'Urdu' };
  var EN_KEY = /^[a-z][a-z'\-]*$/;

  // Must stay identical to key_for() in tools/build_lexicon.py
  function keyFor(code, w) {
    w = String(w).normalize('NFC').trim();
    if (code === 'ur') {
      w = w.replace(/[ً-ٰٟۖ-ۭـ]/g, '');
      w = w.replace(/[يى]/g, 'ی').replace(/ك/g, 'ک').replace(/ة/g, 'ہ');
    } else if (code === 'hi' || code === 'mr') {
      w = w.replace(/़/g, '');
    }
    return w;
  }
  function scriptOf(w) {
    if (/[ऀ-ॿ]/.test(w)) return 'deva';
    if (/[؀-ۿݐ-ݿ]/.test(w)) return 'arab';
    if (/[A-Za-z]/.test(w)) return 'latn';
    return '';
  }
  function tokenize(text) {
    var parts = String(text).split(/[\s​-‍,.;:!?()\[\]{}"“”‘’«»…—–।۔؟،|\/\\<>=+*~^_@#$%&]+/);
    var out = [];
    parts.forEach(function (p) {
      p = p.replace(/^['\-]+|['\-]+$/g, '');
      if (p) out.push(p);
    });
    return out;
  }
  function shardOf(k) { var c = k.charAt(0); return c >= 'a' && c <= 'z' ? c : '_'; }
  function unique(a) { var s = {}, o = []; a.forEach(function (x) { if (!s[x]) { s[x] = 1; o.push(x); } }); return o; }

  function stems(w) {
    var out = [];
    var rules = [['ies', 'y'], ['ied', 'y'], ['ves', 'f'], ['ves', 'fe'], ['es', ''], ['s', ''], ['ed', ''], ['ed', 'e'],
      ['ing', ''], ['ing', 'e'], ['er', ''], ['er', 'e'], ['est', ''], ['est', 'e'], ['ily', 'y'], ['ly', ''], ['ness', '']];
    rules.forEach(function (r) {
      if (w.length > r[0].length + 2 && w.slice(-r[0].length) === r[0]) {
        var s = w.slice(0, -r[0].length) + r[1];
        out.push(s);
        if (s.length > 3 && s.charAt(s.length - 1) === s.charAt(s.length - 2)) out.push(s.slice(0, -1));
      }
    });
    return unique(out);
  }

  function item(text) { return { text: text || '', roman: '', meaning: '', example: '', alts: [], senses: null, mlang: '' }; }
  function blank() { return { en: item(), hi: item(), mr: item(), ur: item() }; }
  function firstSense(p) {
    if (p && p[0] && p[0][1] && p[0][1][0]) return { def: p[0][1][0][0] || '', ex: p[0][1][0][1] || '' };
    return { def: '', ex: '' };
  }

  function create(opts) {
    var load = opts.load;
    var forms = null;

    async function getForms() {
      if (forms === null) forms = (await load('forms')) || {};
      return forms;
    }
    async function exact(k) {
      if (!EN_KEY.test(k)) return null;
      var sh = await load('en_' + shardOf(k));
      return sh && sh[k] ? { key: k, entry: sh[k] } : null;
    }
    async function findEnglish(w) {
      var f = await getForms();
      var cands = [w];
      if (f[w]) cands.push(f[w]);
      stems(w).forEach(function (s) { cands.push(s); });
      cands = unique(cands);
      for (var i = 0; i < cands.length; i++) {
        var r = await exact(cands[i]);
        if (r) return r;
      }
      return null;
    }

    function fromEnglish(found, typed) {
      var entry = found.entry, items = blank(), it = items.en, fs = firstSense(entry.p);
      it.text = found.key; it.senses = entry.p || null; it.meaning = fs.def; it.example = fs.ex;
      var missing = [];
      NAT.forEach(function (c) {
        var t = entry.t && entry.t[c];
        if (t && t.length) { items[c].text = t[0][0]; items[c].roman = t[0][1] || ''; items[c].alts = t.slice(1); }
        else missing.push(LANG_NAME[c]);
      });
      var note = '';
      if (typed && typed !== found.key) note = 'Showing “' + found.key + '” for “' + typed + '”.';
      if (missing.length === 3) note += (note ? ' ' : '') + 'No Hindi, Marathi or Urdu equivalent is in the offline word list for this word.';
      else if (missing.length) note += (note ? ' ' : '') + 'No ' + missing.join(' or ') + ' equivalent in the offline word list.';
      return { detected: 'en', kind: 'word', pos: entry.p && entry.p[0] ? entry.p[0][0] : '', note: note, items: items };
    }

    async function fromNative(code, nent, typed) {
      var w = nent[0], r = nent[1] || '', eng = nent[2] || [], gloss = nent[3] || '';
      var found = null;
      for (var i = 0; i < Math.min(eng.length, 4); i++) {
        var f = await exact(eng[i]);
        if (f) { if (f.entry.p) { found = f; break; } if (!found) found = f; }
      }
      var data;
      if (found) {
        data = fromEnglish(found, '');
        data.note = 'Meaning is for the English word “' + found.key + '”.';
      } else {
        var items = blank();
        items.en.text = eng[0] || ''; items.en.meaning = gloss; items.en.mlang = 'en';
        data = { detected: code, kind: 'word', pos: '', note: 'No English dictionary entry matched, so only the short Wiktionary meaning is shown.', items: items };
      }
      data.detected = code;
      var src = data.items[code];
      src.text = w; src.roman = r; src.alts = []; src.senses = null; src.example = '';
      src.meaning = gloss; src.mlang = 'en';
      return data;
    }

    async function suggestEnglish(w) {
      var sh = await load('en_' + shardOf(w));
      if (!sh) return [];
      var pre = w.slice(0, 3);
      var keys = Object.keys(sh).filter(function (k) { return k.indexOf(pre) === 0; });
      keys.sort(function (a, b) { return Math.abs(a.length - w.length) - Math.abs(b.length - w.length) || (a < b ? -1 : 1); });
      return keys.slice(0, 8);
    }
    async function suggestNative(code, w) {
      var sh = await load('nat_' + code);
      if (!sh) return [];
      var pre = keyFor(code, w).slice(0, 2), out = [];
      Object.keys(sh).forEach(function (k) { if (k.indexOf(pre) === 0) out.push(sh[k][0]); });
      out.sort(function (a, b) { return Math.abs(a.length - w.length) - Math.abs(b.length - w.length) || (a < b ? -1 : 1); });
      return out.slice(0, 8);
    }

    async function lookup(text, hint) {
      var toks = tokenize(text);
      if (!toks.length) return { kind: 'empty' };
      if (toks.length > 1) return { kind: 'multi', tokens: unique(toks).slice(0, 80) };
      var w = toks[0], sc = scriptOf(w);
      var h = hint && hint !== 'auto' ? hint : '';
      if (sc === 'deva' || sc === 'arab') {
        var order = sc === 'arab' ? ['ur'] : (h === 'mr' ? ['mr', 'hi'] : ['hi', 'mr']);
        for (var i = 0; i < order.length; i++) {
          var sh = await load('nat_' + order[i]);
          var ent = sh && sh[keyFor(order[i], w)];
          if (ent) return { kind: 'word', data: await fromNative(order[i], ent, w) };
        }
        return { kind: 'notfound', query: w, script: sc, suggestions: await suggestNative(order[0], w) };
      }
      var lw = w.toLowerCase();
      var found = await findEnglish(lw);
      if (found) return { kind: 'word', data: fromEnglish(found, lw) };
      return { kind: 'notfound', query: w, script: sc || 'latn', suggestions: sc === 'latn' && EN_KEY.test(lw) ? await suggestEnglish(lw) : [] };
    }

    return { lookup: lookup };
  }

  return { create: create, keyFor: keyFor, scriptOf: scriptOf, tokenize: tokenize };
});
