// The save panel.
//
// Only ever runs in the desktop app, so a mistake here does not show up in a
// browser or in CI - it shows up as a panel that will not draw on the one
// machine that can write to a save. That is reason enough to test it where it
// can be tested.
//
// The DOM it needs is small and deliberate (`el()` in save-ui.js touches
// createElement, append and replaceChildren and nothing else), so it is
// stubbed here rather than pulling in a browser.

import assert from 'node:assert/strict';
import { afterEach, describe, it } from 'node:test';

import { attachSaves } from '../save-ui.js';

/** Just enough DOM for `el()`. */
function node(tag = 'div') {
  const self = {
    tag, children: [], style: {}, className: '', textContent: '', title: '',
    hidden: false, onclick: null, parent: null, focused: false,
    append(...kids) {
      for (const kid of kids) { if (kid && kid.tag) kid.parent = self; }
      self.children.push(...kids);
    },
    replaceChildren(...kids) {
      for (const kid of kids) { if (kid && kid.tag) kid.parent = self; }
      self.children = [...kids];
    },
    // The overlay takes itself off the page again, so the stub has to be
    // able to say whether it is still there.
    remove() {
      const owner = self.parent;
      if (!owner) return;
      owner.children = owner.children.filter((k) => k !== self);
      self.parent = null;
    },
    focus() { self.focused = true; },
  };
  return self;
}

/**
 * A document stub that holds a body and remembers key handlers.
 *
 * The overlay listens for Escape and has to stop listening when it closes;
 * a listener left behind would close the *next* overlay the moment it opens.
 */
function fakeDocument() {
  const body = node('body');
  const keys = new Set();
  return {
    body,
    createElement: (tag) => node(tag),
    addEventListener(kind, fn) { if (kind === 'keydown') keys.add(fn); },
    removeEventListener(kind, fn) { if (kind === 'keydown') keys.delete(fn); },
    press(key) { for (const fn of [...keys]) fn({ key }); },
    listening: () => keys.size,
  };
}

/** Every button in the tree, depth first. */
function buttons(root) {
  const out = [];
  const walk = (n) => {
    if (!n || typeof n !== 'object') return;
    if (n.tag === 'button') out.push(n);
    for (const kid of n.children ?? []) walk(kid);
  };
  walk(root);
  return out;
}

const byText = (root, text) =>
  buttons(root).find((b) => b.textContent === text);

const stubs = [];
function global_(name, value) {
  stubs.push([name, globalThis[name]]);
  globalThis[name] = value;
}
afterEach(() => {
  while (stubs.length) {
    const [name, was] = stubs.pop();
    if (was === undefined) delete globalThis[name]; else globalThis[name] = was;
  }
});

const A_MAP = {
  name: 'Daibi', id: 'abc', playable: true,
  derived: { players: 2 },
  document: { size: { cols: 12, rows: 10 }, terrain: [], cells: [], units: [] },
};

/**
 * Attach the panel over a scripted bridge.
 *
 * `api` is what pywebview would inject; only the calls a test cares about
 * need to be present.
 */
function panelOver(api, { confirms = [], prompts = [], pickMap } = {}) {
  const asked = [];
  const alerts = [];
  const doc = fakeDocument();
  global_('document', doc);
  global_('window', { pywebview: { api: {
    find_saves: async () => ({ ok: true, saves: [{ path: 'C:/save/maps' }] }),
    open_save: async () => ({ ok: true, maps: [A_MAP] }),
    ...api,
  } } });
  global_('confirm', (m) => { asked.push(m); return confirms.length ? confirms.shift() : true; });
  global_('prompt', (m) => { asked.push(m); return prompts.length ? prompts.shift() : '1'; });
  global_('alert', (m) => { alerts.push(m); });

  const panel = node();
  const api_ = attachSaves({
    panel,
    poster: (doc_, tile) => ({ tag: 'canvas', style: {}, children: [],
                              tile, width: 1, height: 1 }),
    pickMap: pickMap ?? (() => null),
  });
  return { panel, api: api_, asked, alerts, doc };
}

/** Every node carrying this class, depth first. */
function byClass(root, wanted) {
  const out = [];
  const walk = (n) => {
    if (!n || typeof n !== 'object') return;
    if (String(n.className || '').split(' ').includes(wanted)) out.push(n);
    for (const kid of n.children ?? []) walk(kid);
  };
  walk(root);
  return out;
}

const text = (n) => String(n?.textContent ?? '');

describe('each map as a card', () => {
  const twoMaps = {
    open_save: async () => ({ ok: true, maps: [
      { index: 0, name: 'Daibi', playable: true,
        derived: { players: 2, fog: true },
        document: { size: { cols: 30, rows: 20 }, author: 'debbie' } },
      { index: 1, name: '', playable: false,
        derived: { players: 1 },
        document: { size: { cols: 12, rows: 10 }, author: '' } },
    ] }),
  };

  it('draws one card per map, not a run of rows', async () => {
    const p = panelOver(twoMaps);
    await p.api.refresh();
    assert.equal(byClass(p.panel, 'mapcard').length, 2);
    assert.equal(byClass(p.panel, 'maplist').length, 1);
  });

  it('gives each card a picture, a name and an author', async () => {
    const p = panelOver(twoMaps);
    await p.api.refresh();
    const first = byClass(p.panel, 'mapcard')[0];
    assert.equal(byClass(first, 'thumb').length, 1, 'somewhere for the map');
    assert.equal(text(byClass(first, 'name')[0]), 'Daibi');
    assert.match(text(byClass(first, 'by')[0]), /debbie/);
  });

  it('says Untitled rather than leaving the name blank', async () => {
    // A blank line reads as a rendering fault; "Untitled" reads as a map
    // nobody got round to naming.
    const p = panelOver(twoMaps);
    await p.api.refresh();
    const second = byClass(p.panel, 'mapcard')[1];
    assert.equal(text(byClass(second, 'name')[0]), 'Untitled');
    assert.match(text(byClass(second, 'by')[0]), /no author/);
  });

  it('shows the facts as badges, from what Python derived', async () => {
    const p = panelOver(twoMaps);
    await p.api.refresh();
    const said = byClass(byClass(p.panel, 'mapcard')[0], 'badge').map(text);
    assert.ok(said.includes('2p'), said.join(' | '));
    assert.ok(said.includes('30×20'));
    assert.ok(said.includes('fog'));
  });

  it('marks an unplayable map, and only that one', async () => {
    const p = panelOver(twoMaps);
    await p.api.refresh();
    const cards = byClass(p.panel, 'mapcard');
    const warned = (c) => byClass(c, 'warn').map(text).join(' ');
    assert.equal(warned(cards[0]), '');
    assert.match(warned(cards[1]), /not playable/);
  });

  it('says so plainly when the save holds no maps', async () => {
    const p = panelOver({ open_save: async () => ({ ok: true, maps: [] }) });
    await p.api.refresh();
    assert.equal(byClass(p.panel, 'mapcard').length, 0);
    assert.match(text(byClass(p.panel, 'notice')[0]), /No custom maps/);
  });
});

describe('the panel', () => {
  it('draws the maps and the controls without throwing', async () => {
    const p = panelOver({});
    await p.api.refresh();
    const labels = buttons(p.panel).map((b) => b.textContent);
    assert.ok(labels.includes('Remove'), labels.join(' | '));
    assert.ok(labels.includes('Back up now'));
    assert.ok(labels.includes('Restore…'));
  });

  it('offers nothing that needs a map editor', async () => {
    // The save editor is shipped apart from the map editor, so there is
    // nothing here to open a map into and no "current map" to add. Maps come
    // from a file the person picked.
    const p = panelOver({});
    await p.api.refresh();
    const labels = buttons(p.panel).map((b) => b.textContent);
    assert.ok(!labels.includes('Open'), 'nothing to open a map into');
    assert.ok(!labels.includes('Add the current map'),
              'there is no map being edited here');
  });
});

describe('importing a map from a file', () => {
  it('writes the picked document into the save', async () => {
    let seen = null;
    const doc = { name: 'Daibi', size: { cols: 12, rows: 10 } };
    const p = panelOver({
      import_map: async (path, document) => {
        seen = [path, document];
        return { ok: true, slot: 3, backup: 'b.bak' };
      },
    }, { pickMap: () => doc });

    await p.api.refresh();
    await p.api.addPicked();
    assert.deepEqual(seen, ['C:/save/maps', doc]);
  });

  it('does nothing when no map was picked', async () => {
    let called = false;
    const p = panelOver({
      import_map: async () => { called = true; return { ok: true }; },
    }, { pickMap: () => null });

    await p.api.refresh();
    await p.api.addPicked();
    assert.equal(called, false);
  });

  it('asks before writing, and does not write when declined', async () => {
    let called = false;
    const p = panelOver({
      import_map: async () => { called = true; return { ok: true }; },
    }, { pickMap: () => ({ name: 'Daibi' }), confirms: [false] });

    await p.api.refresh();
    await p.api.addPicked();
    assert.equal(called, false);
  });

  it('shows the findings when the map is refused', async () => {
    const p = panelOver({
      import_map: async () => ({
        ok: false, error: 'that map did not pass validation',
        findings: [{ code: 'play.noHQ', message: 'team 0 has no HQ' }],
      }),
    }, { pickMap: () => ({ name: 'Daibi' }) });

    await p.api.refresh();
    await p.api.addPicked();
    assert.ok(p.alerts.some((m) => m.includes('team 0 has no HQ')),
              p.alerts.join(' | '));
  });
});

describe('backing up on demand', () => {
  it('asks the bridge and says what it got', async () => {
    let seen = null;
    const p = panelOver({
      backup_now: async (path) => { seen = path; return { ok: true, name: 'maps-2026.bak' }; },
    });
    await p.api.refresh();
    await byText(p.panel, 'Back up now').onclick();
    assert.equal(seen, 'C:/save/maps');
    assert.ok(p.alerts.some((m) => m.includes('maps-2026.bak')), p.alerts.join(' | '));
  });

  it('shows the error rather than claiming success', async () => {
    const p = panelOver({
      backup_now: async () => ({ ok: false, error: 'the disk is full' }),
    });
    await p.api.refresh();
    await byText(p.panel, 'Back up now').onclick();
    assert.ok(p.alerts.some((m) => m.includes('the disk is full')));
  });
});

describe('restoring', () => {
  const twoSnapshots = {
    snapshots: async () => ({ ok: true, snapshots: [
      { name: 'older.bak', taken: '2026-09-01', size: 1 },
      { name: 'newer.bak', taken: '2026-09-30', size: 1 },
    ] }),
  };

  it('says so plainly when there are none, rather than offering a prompt',
     async () => {
    const p = panelOver({ snapshots: async () => ({ ok: true, snapshots: [] }) });
    await p.api.refresh();
    await byText(p.panel, 'Restore…').onclick();
    assert.ok(p.alerts.some((m) => /No backups/.test(m)), p.alerts.join(' | '));
  });

  it('restores the one that was chosen', async () => {
    let seen = null;
    const p = panelOver({
      ...twoSnapshots,
      restore: async (path, name) => { seen = [path, name]; return { ok: true, restored: name }; },
    }, { prompts: ['1'] });
    await p.api.refresh();
    await byText(p.panel, 'Restore…').onclick();
    assert.deepEqual(seen, ['C:/save/maps', 'older.bak']);
  });

  it('does nothing at all, and says nothing, when the prompt is cancelled',
     async () => {
    // Silence is the point. Falling through to the "no such backup" branch
    // would also restore nothing, but it scolds somebody for pressing Cancel.
    let called = false;
    const p = panelOver({
      ...twoSnapshots,
      restore: async () => { called = true; return { ok: true }; },
    }, { prompts: [null] });
    await p.api.refresh();
    await byText(p.panel, 'Restore…').onclick();
    assert.equal(called, false);
    assert.deepEqual(p.alerts, [], `cancelling should be quiet: ${p.alerts}`);
  });

  it('restores nothing when the number is not on the list', async () => {
    // An overwrite of the save is on the other side of this, so a typo must
    // not pick a neighbour.
    let called = false;
    const p = panelOver({
      ...twoSnapshots,
      restore: async () => { called = true; return { ok: true }; },
    }, { prompts: ['9'] });
    await p.api.refresh();
    await byText(p.panel, 'Restore…').onclick();
    assert.equal(called, false);
    assert.ok(p.alerts.some((m) => /no backup 9/i.test(m)), p.alerts.join(' | '));
  });

  it('restores nothing when the confirmation is declined', async () => {
    let called = false;
    const p = panelOver({
      ...twoSnapshots,
      restore: async () => { called = true; return { ok: true }; },
    }, { prompts: ['2'], confirms: [false] });
    await p.api.refresh();
    await byText(p.panel, 'Restore…').onclick();
    assert.equal(called, false);
  });
});

describe('looking at a map full size', () => {
  const bigAndSmall = {
    open_save: async () => ({ ok: true, maps: [
      { index: 0, name: 'Daibi', playable: true, derived: { players: 2 },
        document: { size: { cols: 30, rows: 20 }, author: 'debbie' } },
    ] }),
  };

  const open = (where) => byClass(where.doc.body, 'lightbox');

  it('opens when the picture is clicked', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    assert.equal(open(it_).length, 0, 'nothing is open to begin with');

    byClass(it_.panel, 'thumb')[0].onclick();
    assert.equal(open(it_).length, 1);
  });

  it('is a button, so a keyboard can reach it', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    const thumb = byClass(it_.panel, 'thumb')[0];
    assert.equal(thumb.tag, 'button');
    assert.match(thumb.title, /bigger/i);
  });

  it('draws the map larger than the thumbnail does', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    const small = byClass(it_.panel, 'thumb')[0].children[0];

    byClass(it_.panel, 'thumb')[0].onclick();
    const big = byClass(it_.doc.body, 'bigframe')[0].children[0];
    assert.ok(big.tile > small.tile,
              `the big one should use a bigger tile: ${big.tile} vs ${small.tile}`);
  });

  it('never blows the sprites up past twice their size', async () => {
    // A tiny map on a huge screen would otherwise be upscaled into blur.
    const tiny = { open_save: async () => ({ ok: true, maps: [
      { index: 0, name: 'Pocket', playable: true, derived: { players: 2 },
        document: { size: { cols: 2, rows: 2 }, author: 'd' } }] }) };
    const it_ = panelOver(tiny);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    const big = byClass(it_.doc.body, 'bigframe')[0].children[0];
    assert.ok(big.tile <= 32, `tile was ${big.tile}`);
  });

  it('names the map it is showing', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    const caption = byClass(it_.doc.body, 'bigcaption')[0];
    assert.equal(text(caption.children[0]), 'Daibi');
    assert.equal(text(caption.children[1]), 'by debbie');
  });

  it('closes on the button', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    byClass(it_.doc.body, 'bigshut')[0].onclick();
    assert.equal(open(it_).length, 0);
  });

  it('closes on Escape', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    it_.doc.press('Escape');
    assert.equal(open(it_).length, 0);
  });

  it('ignores other keys', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    it_.doc.press('a');
    assert.equal(open(it_).length, 1);
  });

  it('closes when the backdrop is clicked', async () => {
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    const sheet = open(it_)[0];
    sheet.onclick({ target: sheet });
    assert.equal(open(it_).length, 0);
  });

  it('stays open when the picture itself is clicked', async () => {
    // Somebody looking at the map is not somebody reaching for the way out.
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    const sheet = open(it_)[0];
    sheet.onclick({ target: byClass(it_.doc.body, 'bigframe')[0] });
    assert.equal(open(it_).length, 1);
  });

  it('stops listening for Escape once it is closed', async () => {
    // A listener left behind would close the next one as it opened.
    const it_ = panelOver(bigAndSmall);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    it_.doc.press('Escape');
    assert.equal(it_.doc.listening(), 0, 'the key handler is still attached');

    byClass(it_.panel, 'thumb')[0].onclick();
    assert.equal(open(it_).length, 1, 'the second one opens and stays open');
  });

  it('does nothing for an entry with no map in it', async () => {
    const empty = { open_save: async () => ({ ok: true, maps: [
      { index: 0, name: 'Broken', playable: false, derived: {} }] }) };
    const it_ = panelOver(empty);
    await it_.api.refresh();
    byClass(it_.panel, 'thumb')[0].onclick();
    assert.equal(open(it_).length, 0);
  });
});
