#!/usr/bin/env python3
"""Builds the offline word data that Pocket Lexicon ships inside the APK.

It runs on GitHub (which has internet) while the APK is being built. The installed app never goes online.

Sources
  * Princeton WordNet (through the nltk package): English meanings, examples, synonyms.
  * Wiktionary (through kaikki.org's Hindi, Marathi and Urdu extracts): native words with English
    glosses and romanization. The glosses are turned around to give English -> Hindi/Marathi/Urdu words.

Output (in --out): small .js files that the app loads on demand.
  en_a.js ... en_z.js, en__.js   English words: meanings plus Hindi/Marathi/Urdu equivalents
  nat_hi.js, nat_mr.js, nat_ur.js  native words -> English meaning
  forms.js                         irregular English forms (went -> go)
"""
import argparse
import collections
import json
import os
import re
import shutil
import sys
import unicodedata
import urllib.request

LANGS = {'hi': 'Hindi', 'mr': 'Marathi', 'ur': 'Urdu'}
UA = {'User-Agent': 'Mozilla/5.0 (PocketLexicon offline build)'}
SKIP_TAGS = {'obsolete', 'archaic', 'dated', 'vulgar', 'offensive', 'nonstandard', 'misspelling'}
SKIP_GLOSS = re.compile(
    r'^(alternative|alternate|obsolete|archaic|dated|misspelling|plural of|inflection|inflected|'
    r'form of|romanization|abbreviation|initialism|acronym|clipping|eye dialect|nonstandard|'
    r'standard spelling|synonym of|short for|contraction|letter|the (name|letter))\b', re.I)
EN_KEY = re.compile(r"^[a-z][a-z'\-]*$")
URDU_MARKS = re.compile('[\u064B-\u065F\u0670\u06D6-\u06ED\u0640]')
MIN_SCORE = 0.2
PER_LANG = 5


# ---------- keys (must match core.js keyFor) ----------
def nfc(s):
    return unicodedata.normalize('NFC', s)


def key_for(code, w):
    w = nfc(w.strip())
    if code == 'ur':
        w = URDU_MARKS.sub('', w)
        w = w.replace('\u064A', '\u06CC').replace('\u0649', '\u06CC')
        w = w.replace('\u0643', '\u06A9').replace('\u0629', '\u06C1')
    elif code in ('hi', 'mr'):
        w = w.replace('\u093C', '')
    return w


# ---------- Wiktionary (kaikki) ----------
def is_latin(s):
    letters = 0
    for ch in s:
        if ch.isalpha():
            if 'LATIN' not in unicodedata.name(ch, ''):
                return False
            letters += 1
        elif not (ch in " '-.\u02BC" or unicodedata.combining(ch)):
            return False
    return letters > 0


def roman_of(o):
    for f in o.get('forms') or []:
        if 'romanization' in (f.get('tags') or []) and f.get('form'):
            return re.split(r'[,/]', f['form'])[0].strip()
    for t in o.get('head_templates') or []:
        m = re.search(r'\(([^()]+)\)', t.get('expansion', '') or '')
        if m:
            cand = re.split(r'[,/]', m.group(1))[0].strip()
            if is_latin(cand):
                return cand
    return ''


def gloss_keys(g):
    g = re.sub(r'\([^)]*\)', ' ', g)
    g = re.sub(r'\[[^\]]*\]', ' ', g)
    out = []
    for part in re.split(r'[;,/]| or ', g):
        p = part.strip().lower().strip('.').strip()
        p = re.sub(r'^(to|a|an|the) ', '', p)
        if EN_KEY.match(p) and p not in out:
            out.append(p)
    return out


def clean_gloss(g):
    g = re.sub(r'\s+', ' ', g).strip().rstrip('.')
    return g[:120]


def process_kaikki(lines, code):
    nat = {}
    rev = collections.defaultdict(lambda: collections.defaultdict(float))
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get('lang_code') != code:
            continue
        word = (o.get('word') or '').strip()
        if not word or ' ' in word:
            continue
        roman = roman_of(o)
        disp = nfc(word)
        key = key_for(code, word)
        if not key:
            continue
        for si, s in enumerate(o.get('senses') or []):
            if set(s.get('tags') or []) & SKIP_TAGS or s.get('form_of') or s.get('alt_of'):
                continue
            gl = s.get('glosses') or s.get('raw_glosses') or []
            if not gl:
                continue
            g = gl[-1]
            if SKIP_GLOSS.match(g.strip()):
                continue
            keys = gloss_keys(g)
            e = nat.setdefault(key, {'w': disp, 'r': roman, 'e': [], 'g': []})
            if not e['r'] and roman:
                e['r'] = roman
            cg = clean_gloss(g)
            if cg and len(e['g']) < 3 and cg not in e['g']:
                e['g'].append(cg)
            for ki, k in enumerate(keys[:4]):
                if k not in e['e'] and len(e['e']) < 6:
                    e['e'].append(k)
                score = (1.0 / (1 + si)) * (1.0 if ki == 0 else 0.5) * (1.0 if len(keys) == 1 else 0.8)
                rev[k][(disp, e['r'])] += score
    return nat, rev


def download(name, cache, log):
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, name + '.jsonl')
    for ext in ('jsonl', 'json'):
        url = 'https://kaikki.org/dictionary/%s/kaikki.org-dictionary-%s.%s' % (name, name, ext)
        try:
            log('Downloading ' + url)
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=300) as r, open(path, 'wb') as f:
                shutil.copyfileobj(r, f)
            if os.path.getsize(path) > 1000:
                return path
        except Exception as e:  # keep going with whatever else is available
            log('  failed: %s' % e)
    return None


# ---------- WordNet ----------
def load_wordnet():
    import nltk
    try:
        nltk.data.find('corpora/wordnet')
    except LookupError:
        nltk.download('wordnet', quiet=True)
    try:
        nltk.data.find('corpora/omw-1.4')
    except LookupError:
        try:
            nltk.download('omw-1.4', quiet=True)
        except Exception:
            pass
    from nltk.corpus import wordnet as wn
    posn = {'n': 'noun', 'v': 'verb', 'a': 'adjective', 'r': 'adverb'}
    entries = {}
    for name in wn.all_lemma_names():
        low = name.lower()
        if '_' in name or not EN_KEY.match(low):
            continue
        by_pos = []
        for p in 'nvar':
            items = []
            for s in wn.synsets(name, pos=p)[:4]:
                ex = s.examples()
                syn = [l.name().replace('_', ' ') for l in s.lemmas() if l.name().lower() != low][:4]
                items.append([s.definition()[:220], (ex[0] if ex else '')[:160], syn])
            if items:
                by_pos.append([posn[p], items])
        if by_pos:
            if low in entries:
                have = {p for p, _ in entries[low]}
                entries[low].extend(x for x in by_pos if x[0] not in have)
            else:
                entries[low] = by_pos
    exc = {}
    try:
        for pos_map in wn._exception_map.values():
            for infl, lemmas in pos_map.items():
                if lemmas and ' ' not in infl and infl not in exc and EN_KEY.match(infl):
                    exc[infl] = lemmas[0]
    except Exception:
        pass
    return entries, exc


# ---------- output ----------
def shard_of(key):
    c = key[0]
    return c if 'a' <= c <= 'z' else '_'


def write_js(path, name, obj):
    s = json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
    s = s.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('__lex(%s,%s);\n' % (json.dumps(name), s))


def build_trans(rev_by_lang):
    trans = collections.defaultdict(dict)
    for code, rev in rev_by_lang.items():
        for k, cands in rev.items():
            ranked = sorted(((c, sc) for c, sc in cands.items() if sc >= MIN_SCORE),
                            key=lambda kv: (-kv[1], len(kv[0][0]), kv[0][0]))[:PER_LANG]
            if ranked:
                trans[k][code] = [[w, r] for (w, r), _ in ranked]
    return trans


def write_all(out, wn, exc, trans, nat_by_lang):
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith('.js'):
            os.remove(os.path.join(out, f))
    shards = collections.defaultdict(dict)
    for key in set(wn) | set(trans):
        if not EN_KEY.match(key):
            continue
        e = {}
        if key in wn:
            e['p'] = wn[key]
        if key in trans:
            e['t'] = trans[key]
        shards[shard_of(key)][key] = e
    for s, d in shards.items():
        write_js(os.path.join(out, 'en_%s.js' % s), 'en_' + s, d)
    for code, nat in nat_by_lang.items():
        d = {k: [v['w'], v['r'], v['e'], '; '.join(v['g'])] for k, v in nat.items()}
        write_js(os.path.join(out, 'nat_%s.js' % code), 'nat_' + code, d)
    write_js(os.path.join(out, 'forms.js'), 'forms', exc)
    return sum(len(d) for d in shards.values())


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--report', default='')
    ap.add_argument('--cache', default='lexicon-cache')
    ap.add_argument('--wordnet-json', help='test only: WordNet data as JSON instead of nltk')
    ap.add_argument('--kaikki-dir', help='test only: folder with Hindi.jsonl, Marathi.jsonl, Urdu.jsonl')
    ap.add_argument('--min-wordnet', type=int, default=20000)
    ap.add_argument('--min-native', type=int, default=500)
    a = ap.parse_args(argv)

    lines_out = []

    def log(m):
        print(m)
        lines_out.append(m)

    if a.wordnet_json:
        with open(a.wordnet_json, encoding='utf-8') as f:
            d = json.load(f)
        wn, exc = d['entries'], d.get('exc', {})
    else:
        wn, exc = load_wordnet()
    log('WordNet words: %d, irregular forms: %d' % (len(wn), len(exc)))

    nat_by_lang, rev_by_lang = {}, {}
    for code, name in LANGS.items():
        path = os.path.join(a.kaikki_dir, name + '.jsonl') if a.kaikki_dir else download(name, a.cache, log)
        if not path or not os.path.exists(path):
            log('WARNING: no %s data' % name)
            nat_by_lang[code], rev_by_lang[code] = {}, {}
            continue
        with open(path, encoding='utf-8') as f:
            nat, rev = process_kaikki(f, code)
        nat_by_lang[code], rev_by_lang[code] = nat, rev
        log('%s words: %d (English keys: %d)' % (name, len(nat), len(rev)))
        if not a.kaikki_dir:
            try:
                os.remove(path)
            except OSError:
                pass

    trans = build_trans(rev_by_lang)
    total_en = write_all(a.out, wn, exc, trans, nat_by_lang)
    total_nat = sum(len(n) for n in nat_by_lang.values())
    size = sum(os.path.getsize(os.path.join(a.out, f)) for f in os.listdir(a.out))
    log('English entries written: %d' % total_en)
    log('Words with a Hindi/Marathi/Urdu equivalent: %d' % len(trans))
    log('Total data size: %.1f MB' % (size / 1e6))

    if a.report:
        with open(a.report, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines_out) + '\n')
    if len(wn) < a.min_wordnet:
        print('ERROR: too little WordNet data (%d).' % len(wn))
        return 2
    if total_nat < a.min_native:
        print('ERROR: too little Hindi/Marathi/Urdu data (%d). Check the download lines above.' % total_nat)
        return 3
    return 0


if __name__ == '__main__':
    sys.exit(main())
