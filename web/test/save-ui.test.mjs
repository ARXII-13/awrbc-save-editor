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

describe('queueing maps instead of writing them', () => {
  const doc = (name) => ({ name, size: { cols: 12, rows: 10 } });

  it('writes nothing when a map is queued', async () => {
    // The whole point. Until Save changes, the save on disk is untouched.
    let called = false;
    const p = panelOver({
      apply_changes: async () => { called = true; return { ok: true }; },
    });
    await p.api.refresh();
    p.api.queue([doc('Daibi')]);
    assert.equal(called, false);
  });

  it('shows a queued map as a card, like the ones already there', async () => {
    const p = panelOver({});
    await p.api.refresh();
    p.api.queue([doc('Daibi')]);
    const coming = byClass(p.panel, 'mapcard').filter(
      (c) => String(c.className).includes('coming'));
    assert.equal(coming.length, 1, 'a queued map should be drawn as a card');
    assert.equal(text(byClass(coming[0], 'name')[0]), 'Daibi');
  });

  it('takes several at once', async () => {
    const p = panelOver({});
    await p.api.refresh();
    p.api.queue([doc('One'), doc('Two'), doc('Three')]);
    assert.equal(byClass(p.panel, 'coming').filter(
      (n) => String(n.className).includes('badge')).length, 3);
  });

  it('writes all of them in one call when saved', async () => {
    let seen = null;
    const p = panelOver({
      apply_changes: async (path, removes, adds) => {
        seen = { path, removes, adds };
        return { ok: true, added: ['1', '2'], removed: [], backup: 'b.bak' };
      },
    });
    await p.api.refresh();
    p.api.queue([doc('One'), doc('Two')]);
    await p.api.commit();

    assert.equal(seen.path, 'C:/save/maps');
    assert.deepEqual(seen.removes, []);
    assert.deepEqual(seen.adds.map((a) => a.document.name), ['One', 'Two']);
  });

  it('asks before writing, and writes nothing when declined', async () => {
    let called = false;
    const p = panelOver({
      apply_changes: async () => { called = true; return { ok: true }; },
    }, { confirms: [false] });
    await p.api.refresh();
    p.api.queue([doc('Daibi')]);
    await p.api.commit();
    assert.equal(called, false);
  });

  it('does nothing at all when nothing is staged', async () => {
    let called = false;
    const p = panelOver({
      apply_changes: async () => { called = true; return { ok: true }; },
    });
    await p.api.refresh();
    await p.api.commit();
    assert.equal(called, false);
  });

  it('shows the findings when a queued map is refused', async () => {
    const p = panelOver({
      apply_changes: async () => ({
        ok: false, error: 'Daibi is not playable',
        findings: [{ code: 'play.noHQ', message: 'team 0 has no HQ' }],
      }),
    });
    await p.api.refresh();
    p.api.queue([doc('Daibi')]);
    await p.api.commit();
    assert.ok(p.alerts.some((m) => m.includes('team 0 has no HQ')),
              p.alerts.join(' | '));
  });

  it('keeps the queue when the batch is refused', async () => {
    // It is what somebody would otherwise have to pick all over again, and
    // a refused batch changed nothing.
    const p = panelOver({
      apply_changes: async () => ({ ok: false, error: 'no' }),
    });
    await p.api.refresh();
    p.api.queue([doc('One'), doc('Two')]);
    await p.api.commit();
    assert.equal(byClass(p.panel, 'coming').filter(
      (n) => String(n.className).includes('badge')).length, 2);
  });
});

describe('marking maps for removal', () => {
  const twoMaps = {
    open_save: async () => ({ ok: true, maps: [
      { index: 0, name: 'Daibi', playable: true, derived: { players: 2 },
        document: { size: { cols: 30, rows: 20 }, author: 'debbie' } },
      { index: 1, name: 'Renew', playable: true, derived: { players: 2 },
        document: { size: { cols: 12, rows: 10 }, author: 'yoyo' } },
    ] }),
  };

  const removeButtons = (p) =>
    byClass(p.panel, 'mapcard').map(
      (c) => buttons(c).find((b) => ['Remove', 'Keep'].includes(b.textContent)));

  it('writes nothing when a map is marked', async () => {
    let called = false;
    const p = panelOver({
      ...twoMaps,
      apply_changes: async () => { called = true; return { ok: true }; },
    });
    await p.api.refresh();
    removeButtons(p)[0].onclick();
    assert.equal(called, false);
  });

  it('says on the card that it is going', async () => {
    const p = panelOver(twoMaps);
    await p.api.refresh();
    removeButtons(p)[0].onclick();
    assert.equal(byClass(p.panel, 'going').filter(
      (n) => String(n.className).includes('badge')).length, 1);
  });

  it('turns into its own undo', async () => {
    const p = panelOver(twoMaps);
    await p.api.refresh();
    assert.equal(removeButtons(p)[0].textContent, 'Remove');
    removeButtons(p)[0].onclick();
    assert.equal(removeButtons(p)[0].textContent, 'Keep');
    removeButtons(p)[0].onclick();
    assert.equal(removeButtons(p)[0].textContent, 'Remove');
    assert.equal(byClass(p.panel, 'going').length, 0);
  });

  it('sends every marked index in one call', async () => {
    let seen = null;
    const p = panelOver({
      ...twoMaps,
      apply_changes: async (path, removes, adds) => {
        seen = { removes, adds };
        return { ok: true, added: [], removed: ['Daibi', 'Renew'],
                 backup: 'b.bak' };
      },
    });
    await p.api.refresh();
    removeButtons(p)[0].onclick();
    removeButtons(p)[1].onclick();
    await p.api.commit();
    assert.deepEqual([...seen.removes].sort(), [0, 1]);
  });

  it('carries removals and additions in the same write', async () => {
    let seen = null;
    const p = panelOver({
      ...twoMaps,
      apply_changes: async (path, removes, adds) => {
        seen = { removes, adds };
        return { ok: true, added: ['3'], removed: ['Daibi'], backup: 'b' };
      },
    });
    await p.api.refresh();
    removeButtons(p)[0].onclick();
    p.api.queue([{ name: 'New', size: { cols: 8, rows: 8 } }]);
    await p.api.commit();
    assert.deepEqual(seen.removes, [0]);
    assert.equal(seen.adds.length, 1);
  });
});

describe('the pending-changes bar', () => {
  it('is absent until something is staged', async () => {
    const p = panelOver({});
    await p.api.refresh();
    assert.equal(byClass(p.panel, 'commitbar').length, 0);
  });

  it('appears once something is', async () => {
    const p = panelOver({});
    await p.api.refresh();
    p.api.queue([{ name: 'One', size: { cols: 8, rows: 8 } }]);
    assert.equal(byClass(p.panel, 'commitbar').length, 1);
  });

  it('says what is about to happen', async () => {
    const p = panelOver({});
    await p.api.refresh();
    p.api.queue([{ name: 'One', size: { cols: 8, rows: 8 } },
                 { name: 'Two', size: { cols: 8, rows: 8 } }]);
    assert.match(text(byClass(p.panel, 'what')[0]), /2 to add/);
  });

  it('discards the queue without touching the save', async () => {
    let called = false;
    const p = panelOver({
      apply_changes: async () => { called = true; return { ok: true }; },
    });
    await p.api.refresh();
    p.api.queue([{ name: 'One', size: { cols: 8, rows: 8 } }]);
    byText(p.panel, 'Discard').onclick();
    assert.equal(byClass(p.panel, 'commitbar').length, 0);
    assert.equal(called, false);
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


describe('choosing between saves', () => {
  const two = {
    find_saves: async () => ({ ok: true, saves: [
      { path: 'C:/ryu/maps', label: 'Ryujinx profile 0', source: 'ryujinx' },
      { path: 'C:/yuzu/maps', label: 'Sudachi profile abcdef01',
        source: 'yuzu' },
    ] }),
  };

  const one = {
    find_saves: async () => ({ ok: true, saves: [
      { path: 'C:/ryu/maps', label: 'Ryujinx profile 0' }] }),
  };

  const picker = (p) => byClass(p.panel, 'savepick')[0];

  /** Every option in the picker, through whatever groups they sit in. */
  const options = (list) => {
    const out = [];
    const walk = (n) => {
      if (!n || typeof n !== 'object') return;
      if (n.tag === 'option') out.push(n);
      for (const kid of n.children ?? []) walk(kid);
    };
    walk(list);
    return out;
  };
  const saveOptions = (list) =>
    options(list).filter((o) => o.value && o.value !== '__browse__');

  it('lists every save it found', async () => {
    const p = panelOver(two);
    await p.api.refresh();
    const list = picker(p);
    assert.ok(list, 'there should be a picker');
    assert.deepEqual(saveOptions(list).map(text),
                     ['Ryujinx profile 0', 'Sudachi profile abcdef01']);
  });

  it('offers browsing in the same list, not beside it', async () => {
    // One question - which save - so one control. A list of found saves
    // next to an "Open a save..." button read as two unrelated things.
    const p = panelOver(two);
    await p.api.refresh();
    const browse = options(picker(p)).find((o) => o.value === '__browse__');
    assert.ok(browse, 'browsing should be an entry in the picker');
    assert.match(text(browse), /choose a folder/i);
  });

  it('separates what it found from what you opened by hand', async () => {
    const p = panelOver(two);
    await p.api.refresh();
    const groups = [];
    const walk = (n) => {
      if (!n || typeof n !== 'object') return;
      if (n.tag === 'optgroup') groups.push(n.label);
      for (const kid of n.children ?? []) walk(kid);
    };
    walk(picker(p));
    assert.ok(groups.some((g) => /found on this machine/i.test(g)), groups);
  });

  it('is a list, not a row of buttons', async () => {
    // Four of them wrapped badly, and two profiles plus a folder copy makes
    // exactly four on a real machine.
    const p = panelOver(two);
    await p.api.refresh();
    assert.equal(picker(p).tag, 'select');
  });

  it('offers the picker even with a single save', async () => {
    // Browsing lives in it, so hiding it would hide the only way to reach a
    // save that was not found.
    const p = panelOver(one);
    await p.api.refresh();
    assert.equal(byClass(p.panel, 'savepick').length, 1);
  });

  it('offers it even when nothing at all was found', async () => {
    // This is the state where pointing at a save by hand matters most, and
    // the panel used to replace itself with a message and no control.
    const p = panelOver({ find_saves: async () => ({ ok: true, saves: [] }) });
    await p.api.refresh();
    const list = picker(p);
    assert.ok(list, 'there should still be a picker');
    assert.ok(options(list).some((o) => o.value === '__browse__'));
  });

  const groupOf = (list, value) => {
    let found = null;
    const walk = (n, label) => {
      if (!n || typeof n !== 'object') return;
      const here = n.tag === 'optgroup' ? n.label : label;
      if (n.tag === 'option' && n.value === value) found = here;
      for (const kid of n.children ?? []) walk(kid, here);
    };
    walk(list, null);
    return found;
  };

  it('puts a save you opened by hand in its own group', async () => {
    // Which of these the tool found and which one you went and fetched is
    // worth knowing, especially when a console dump sits beside a detected
    // emulator save.
    const p = panelOver({
      ...two,
      browse_for_save: async () => ({ ok: true, cancelled: false, saves: [
        { path: 'D:/dump/maps', label: 'directory', source: 'directory' }] }),
      open_save: async () => ({ ok: true, maps: [] }),
    });
    await p.api.refresh();
    const list = picker(p);
    list.value = '__browse__';
    list.onchange();
    await new Promise((r) => setTimeout(r, 0));

    const after = picker(p);
    assert.match(groupOf(after, 'D:/dump/maps') || '', /by hand/i);
    assert.match(groupOf(after, 'C:/ryu/maps') || '', /found/i);
  });

  it('marks the open one as selected', async () => {
    const p = panelOver(two);
    await p.api.refresh();
    const [first, second] = saveOptions(picker(p));
    assert.equal(first.selected, true);
    assert.notEqual(second.selected, true);
  });

  it('puts the list back when browsing is cancelled', async () => {
    // Otherwise the picker reads "Choose a folder..." as though that were
    // the open save.
    const p = panelOver({
      ...two,
      browse_for_save: async () => ({ ok: true, cancelled: true, saves: [] }),
    });
    await p.api.refresh();
    const list = picker(p);
    list.value = '__browse__';
    list.onchange();
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(list.value, 'C:/ryu/maps');
  });

  it('opens the other one when it is chosen', async () => {
    const opened = [];
    const p = panelOver({
      ...two,
      open_save: async (path) => {
        opened.push(path);
        return { ok: true, maps: [] };
      },
    });
    await p.api.refresh();
    const list = picker(p);
    list.value = 'C:/yuzu/maps';
    list.onchange();
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(opened.at(-1), 'C:/yuzu/maps');
  });

  it('does not reopen the save already open', async () => {
    const opened = [];
    const p = panelOver({
      ...two,
      open_save: async (path) => {
        opened.push(path);
        return { ok: true, maps: [] };
      },
    });
    await p.api.refresh();
    const before = opened.length;
    const list = picker(p);
    list.value = 'C:/ryu/maps';
    list.onchange();
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(opened.length, before);
  });

  it('asks before switching away from unsaved changes', async () => {
    // Switching rebuilds the list from the other save, so anything staged
    // against this one is gone.
    const opened = [];
    const p = panelOver({
      ...two,
      open_save: async (path) => {
        opened.push(path);
        return { ok: true, maps: [] };
      },
    }, { confirms: [false] });
    await p.api.refresh();
    p.api.queue([{ name: 'Pending', size: { cols: 8, rows: 8 } }]);

    const before = opened.length;
    const list = picker(p);
    list.value = 'C:/yuzu/maps';
    list.onchange();
    await new Promise((r) => setTimeout(r, 0));
    assert.equal(opened.length, before, 'it should not have switched');
  });

  it('names the open save above the list when there is no picker',
     async () => {
    const p = panelOver(one);
    await p.api.refresh();
    const sub = byClass(p.panel, 'listhead')[0].children[1];
    assert.equal(text(sub), 'Ryujinx profile 0');
    assert.equal(sub.title, 'C:/ryu/maps', 'the path is still reachable');
  });

  it('shows the path there instead once the picker says which save',
     async () => {
    // The picker already names it; repeating it wastes the line.
    const p = panelOver(two);
    await p.api.refresh();
    const sub = byClass(p.panel, 'listhead')[0].children[1];
    assert.equal(text(sub), 'C:/ryu/maps');
  });

  it('names no emulator when it finds nothing', async () => {
    // Telling somebody their Ryujinx save is missing when they do not use
    // Ryujinx is worse than saying nothing.
    const p = panelOver({ find_saves: async () => ({ ok: true, saves: [] }) });
    await p.api.refresh();
    const said = text(byClass(p.panel, 'notice')[0]);
    assert.match(said, /No Advance Wars save was found/);
    assert.ok(!/Ryujinx|yuzu|Sudachi/i.test(said), said);
  });
});

describe('a save with no maps file in it', () => {
  // What a console save looks like when its owner has never opened the
  // Design Room. The tool makes the file rather than sending them away to
  // make a map by hand first.
  const noFileYet = {
    find_saves: async () => ({ ok: true, saves: [] }),
    browse_for_save: async () => ({
      ok: false, kind: 'NoMapsYet', canCreate: true,
      folder: 'D:/switch/ARX II-13',
      error: 'it has no maps file',
    }),
  };

  const doc = (name) => ({ name, size: { cols: 8, rows: 8 } });
  const picker = (p) => byClass(p.panel, 'savepick')[0];

  const browse = async (p) => {
    const list = picker(p);
    list.value = '__browse__';
    list.onchange();
    await new Promise((r) => setTimeout(r, 0));
  };

  it('offers to make one instead of refusing', async () => {
    const p = panelOver(noFileYet);
    await p.api.refresh();
    await browse(p);
    assert.equal(byClass(p.panel, 'making').length, 1,
                 'it should say the file will be made');
    assert.equal(p.alerts.length, 0, 'and not report it as an error');
  });

  it('names the folder it will write into', async () => {
    const p = panelOver(noFileYet);
    await p.api.refresh();
    await browse(p);
    assert.match(text(byClass(p.panel, 'making')[0]), /ARX II-13/);
  });

  it('shows the maps that will go in it', async () => {
    const p = panelOver(noFileYet);
    await p.api.refresh();
    await browse(p);
    p.api.queue([doc('One'), doc('Two')]);
    assert.equal(byClass(p.panel, 'coming').filter(
      (n) => String(n.className).includes('badge')).length, 2);
  });

  it('calls the button Create rather than Save', async () => {
    const p = panelOver(noFileYet);
    await p.api.refresh();
    await browse(p);
    p.api.queue([doc('One')]);
    assert.ok(byText(p.panel, 'Create maps file'),
              buttons(p.panel).map(text).join(' | '));
  });

  it('makes the file with the queued maps in it', async () => {
    let seen = null;
    const p = panelOver({
      ...noFileYet,
      create_save: async (folder, adds) => {
        seen = { folder, adds };
        return { ok: true, path: 'D:/switch/ARX II-13/SaveData/maps',
                 created: ['One', 'Two'] };
      },
      open_save: async () => ({ ok: true, maps: [] }),
    });
    await p.api.refresh();
    await browse(p);
    p.api.queue([doc('One'), doc('Two')]);
    await p.api.commit();

    assert.equal(seen.folder, 'D:/switch/ARX II-13');
    assert.deepEqual(seen.adds.map((a) => a.document.name), ['One', 'Two']);
  });

  it('refuses to make an empty one', async () => {
    // The file is built with the maps in it: an empty document carries only
    // the root class definitions and nothing could be added to it later.
    let called = false;
    const p = panelOver({
      ...noFileYet,
      create_save: async () => { called = true; return { ok: true }; },
    });
    await p.api.refresh();
    await browse(p);
    await p.api.commit();
    assert.equal(called, false);
  });

  it('asks before writing, and writes nothing when declined', async () => {
    let called = false;
    const p = panelOver({
      ...noFileYet,
      create_save: async () => { called = true; return { ok: true }; },
    }, { confirms: [false] });
    await p.api.refresh();
    await browse(p);
    p.api.queue([doc('One')]);
    await p.api.commit();
    assert.equal(called, false);
  });

  it('keeps the queue when making the file fails', async () => {
    const p = panelOver({
      ...noFileYet,
      create_save: async () => ({ ok: false, error: 'no' }),
    });
    await p.api.refresh();
    await browse(p);
    p.api.queue([doc('One'), doc('Two')]);
    await p.api.commit();
    assert.equal(byClass(p.panel, 'coming').filter(
      (n) => String(n.className).includes('badge')).length, 2);
  });

  it('opens the save it just made, like any other', async () => {
    const opened = [];
    const p = panelOver({
      ...noFileYet,
      create_save: async () => ({
        ok: true, path: 'D:/switch/ARX II-13/SaveData/maps',
        created: ['One'] }),
      open_save: async (path) => {
        opened.push(path);
        return { ok: true, maps: [] };
      },
    });
    await p.api.refresh();
    await browse(p);
    p.api.queue([doc('One')]);
    await p.api.commit();

    assert.equal(opened.at(-1), 'D:/switch/ARX II-13/SaveData/maps');
    assert.equal(byClass(p.panel, 'making').length, 0,
                 'it is an ordinary save now');
  });

  it('drops removal marks from the save you came from', async () => {
    // They are indices into a save that is no longer open. Carried over,
    // they would make commit() think there is work to do and reach the
    // create path with nothing to create.
    let called = false;
    const p = panelOver({
      find_saves: async () => ({ ok: true, saves: [
        { path: 'C:/ryu/maps', label: 'Ryujinx profile 0' }] }),
      open_save: async () => ({ ok: true, maps: [
        { index: 0, name: 'Old', playable: true, derived: { players: 2 },
          document: { size: { cols: 8, rows: 8 } } }] }),
      browse_for_save: async () => ({
        ok: false, kind: 'NoMapsYet', canCreate: true,
        folder: 'D:/switch/ARX II-13', error: 'no maps file' }),
      create_save: async () => { called = true; return { ok: true }; },
    });
    await p.api.refresh();
    buttons(p.panel).find((b) => b.textContent === 'Remove').onclick();
    await browse(p);
    await p.api.commit();

    assert.equal(called, false, 'nothing should have been created');
    assert.equal(byClass(p.panel, 'commitbar').length, 0,
                 'and nothing should still look pending');
  });

  it('still reports a browse that really did fail', async () => {
    const p = panelOver({
      find_saves: async () => ({ ok: true, saves: [] }),
      browse_for_save: async () => ({
        ok: false, kind: 'NotAFolder',
        error: 'a Switch over USB is a portable device' }),
    });
    await p.api.refresh();
    await browse(p);
    assert.equal(byClass(p.panel, 'making').length, 0);
    assert.ok(p.alerts.some((m) => /portable device/.test(m)),
              p.alerts.join(' | '));
  });
});
