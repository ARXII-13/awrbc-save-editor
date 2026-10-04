// The save panel.
//
// Appears only in the desktop app, which is shipped apart from the map editor
// on purpose: one writes to a file the game owns, the other talks to a public
// archive. This file is on the save side of that line and knows nothing about
// editing or about the archive.
//
// Previews come from the same renderer the editor uses - a map is a map, and
// a save manager has to show which one is which. That is the whole of what
// the two share.
//
// `poster` is passed in rather than imported so this stays free of any opinion
// about how a map is drawn (decision #47, which also makes it port).

import * as saves from './saves.js';

const THUMB = 7;   // pixels per tile in the list; big enough to recognise

// How big the picture gets when a thumbnail is clicked. The sprites are 16px
// tiles, so past about twice that it is upscaled blur rather than detail;
// below ten it is not worth having opened anything.
const BIG_MIN = 10;
const BIG_MAX = 32;

/**
 * Wire up the save panel.
 *
 * `pickMap()` answers the map to import, or null - a document the caller got
 * from somewhere else, because this tool does not make maps. It used to be
 * `currentDoc()`, the map open in the editor, which is exactly the coupling
 * the split removes.
 */
export function attachSaves({ panel, poster, pickMap }) {
  let savePath = null;
  let entries = [];

  const el = (tag, props = {}, ...kids) => {
    const node = Object.assign(document.createElement(tag), props);
    for (const k of kids) node.append(k);
    return node;
  };

  function say(message, isError = false) {
    panel.replaceChildren(el('div', {
      className: isError ? 'notice no' : 'notice', textContent: message }));
  }

  /**
   * The facts worth showing about a map, as badges.
   *
   * Built from `derived`, which Python computed from the map itself rather
   * than from anything it claims about itself. "Not playable" comes last and
   * is coloured, because it is the one that changes what you would do next.
   */
  function facts(entry) {
    const d = entry.derived ?? {};
    const size = entry.document?.size ?? {};
    const out = [
      { text: `${d.players ?? 0}p`, kind: 'key' },
      { text: `${size.cols ?? '?'}×${size.rows ?? '?'}`, kind: 'key' },
    ];
    for (const k of ['fog', 'navy', 'predeployed', 'structures']) {
      if (d[k]) out.push({ text: k, kind: '' });
    }
    if (!entry.playable) out.push({ text: 'not playable', kind: 'warn' });
    return out;
  }

  async function refresh() {
    const got = await saves.findSaves();
    if (!got.ok) return say(got.error, true);
    if (!got.saves.length) {
      return say('No Ryujinx save found on this machine.');
    }
    // One save is the common case; more than one means profiles, and the
    // path's tail is the only thing that tells them apart.
    savePath = savePath ?? got.saves[0].path;
    await open(savePath);
  }

  async function open(path) {
    say('Reading…');
    const got = await saves.openSave(path);
    if (!got.ok) return say(got.error, true);
    savePath = path;
    entries = got.maps;
    render();
  }

  /**
   * The tile size that fits this map on this screen.
   *
   * A thumbnail is for telling maps apart; this is for actually reading one,
   * so it takes the window and works backwards. Clamped at both ends: the
   * sprites are 16px, so a small map on a big screen would otherwise be
   * blown up into blur.
   */
  function bigTile(doc) {
    const cols = doc?.size?.cols || 1;
    const rows = doc?.size?.rows || 1;
    const room = globalThis.window ?? {};
    // These have to cover the overlay's own chrome, not a guess at it: 28px
    // of backdrop padding each side, 10px of frame padding, and a border.
    // Too small and a map that would have fitted gets a scrollbar.
    const wide = (room.innerWidth ?? 1000) - 88;
    const tall = (room.innerHeight ?? 800) - 150;     // the same, plus caption
    const fits = Math.floor(Math.min(wide / cols, tall / rows));
    return Math.max(BIG_MIN, Math.min(BIG_MAX, fits));
  }

  /**
   * The same map, big enough to look at.
   *
   * The renderer is already here and already the only thing this tool shares
   * with the editor, so this is a second call to it rather than anything new
   * - no editing, no interaction, just the picture at a size you can read.
   *
   * Dismissed by the button, by the backdrop, or by Escape. All three,
   * because an overlay with no visible way out is a trap, and this one can
   * cover the whole window.
   */
  function showBig(entry) {
    const doc = entry.document;
    if (!doc) return;

    const named = (entry.name || '').trim();
    const author = (entry.document?.author || '').trim();

    const shut = el('button', {
      className: 'bigshut', title: 'Close (Esc)', textContent: 'Close' });

    const frame = el('div', { className: 'bigframe' },
      poster(doc, bigTile(doc)));

    const caption = el('div', { className: 'bigcaption' },
      el('span', {
        className: named ? 'name' : 'name unnamed',
        textContent: named || 'Untitled',
      }),
      el('span', {
        className: 'by',
        textContent: author ? 'by ' + author : 'no author',
      }));

    const box = el('div', { className: 'bigbox' }, frame, caption);
    const sheet = el('div', {
      className: 'lightbox',
      role: 'dialog',
      ariaLabel: `${named || 'Untitled'}, full size`,
    }, box, shut);

    const onKey = (ev) => { if (ev.key === 'Escape') close(); };
    function close() {
      globalThis.document?.removeEventListener?.('keydown', onKey);
      sheet.remove?.();
    }

    shut.onclick = close;
    // Only the backdrop itself. A click that landed on the picture is
    // somebody looking at it, not somebody reaching for the way out.
    sheet.onclick = (ev) => { if (ev?.target === sheet) close(); };
    globalThis.document?.addEventListener?.('keydown', onKey);

    (globalThis.document?.body ?? panel).append(sheet);
    shut.focus?.();
    return { sheet, close };
  }

  /** One map, as a card: picture, what it is, and what you can do to it. */
  function card(entry, i) {
    // A button, not a div with a click on it: this is reachable by keyboard
    // and announces itself, and the picture is the obvious thing to press.
    const look = el('button', {
      className: 'thumb', title: 'Show this map bigger',
    }, poster(entry.document, THUMB));
    look.onclick = () => showBig(entry);

    // No "Open": there is nothing here to open a map into. Editing lives in
    // the map editor, which this tool is deliberately not.
    const drop = el('button', {
      className: 'danger', title: 'Remove this map from the save',
      textContent: 'Remove' });
    drop.onclick = () => removeAt(i);

    const author = (entry.document?.author || '').trim();
    const named = (entry.name || '').trim();

    return el('div', { className: 'mapcard' },
      look,
      el('div', { className: 'meta' },
        el('div', {
          className: named ? 'name' : 'name unnamed',
          textContent: named || 'Untitled',
        }),
        el('div', {
          className: author ? 'by' : 'by anon',
          textContent: author ? 'by ' + author : 'no author',
        }),
        el('div', { className: 'facts' },
          ...facts(entry).map((f) => el('span', {
            className: f.kind ? 'badge ' + f.kind : 'badge',
            textContent: f.text,
          })))),
      el('div', { className: 'cardactions' }, drop));
  }

  function render() {
    // Every write here takes a backup of its own, so these are for the times
    // that is not enough: before a run of edits, and after one went wrong.
    const takeBackup = el('button', {
      title: 'Copy this save somewhere safe, right now',
      textContent: 'Back up now' });
    takeBackup.onclick = backupNow;

    const roll = el('button', {
      title: 'Put an earlier copy of this save back',
      textContent: 'Restore…' });
    roll.onclick = restorePrompt;

    const count = entries.length;
    const head = el('div', { className: 'listhead' },
      el('h2', { textContent: count === 1 ? '1 map in this save'
                                          : `${count} maps in this save` }),
      el('span', { className: 'sub', textContent: savePath || '' }));

    panel.replaceChildren(
      el('div', { className: 'toolbar' }, takeBackup, roll),
      head,
      count
        ? el('div', { className: 'maplist' },
             ...entries.map((entry, i) => card(entry, i)))
        : el('div', { className: 'notice',
                      textContent: 'No custom maps in this save yet.' }));
  }

  async function backupNow() {
    const got = await saves.backupNow(savePath);
    if (!got.ok) return alert(got.error);
    alert(`Backed up as ${got.name}.`);
  }

  /**
   * Choose a snapshot to put back.
   *
   * A numbered list and a prompt rather than a dialog, because this panel is
   * a toolbar column and the framework rebuild (decision #47) is where a real
   * one belongs. The names carry a timestamp, so they sort newest-last and
   * reading them is the whole of the choice.
   */
  async function restorePrompt() {
    const got = await saves.snapshots(savePath);
    if (!got.ok) return alert(got.error);
    if (!got.snapshots.length) {
      return alert('No backups of this save yet.\n\n' +
                   'One is taken automatically before every write, and ' +
                   '"Back up now" takes one on demand.');
    }

    const list = got.snapshots.map(
      (s, i) => `${i + 1}. ${s.name}  (${s.taken})`).join('\n');
    const answer = prompt(
      'Restore which backup?\n\n' + list +
      '\n\nType its number. The save as it is now is kept as a backup too, ' +
      'so this is itself undoable.', String(got.snapshots.length));
    if (answer === null) return;

    const pick = got.snapshots[Number(answer) - 1];
    if (!pick) return alert(`There is no backup ${answer}.`);
    if (!confirm(`Replace the current save with ${pick.name}?\n\n` +
                 'The game must be closed.')) return;

    say('Restoring…');
    const done = await saves.restore(savePath, pick.name);
    if (!done.ok) {
      alert(done.error);
      return open(savePath);
    }
    await open(savePath);
    alert(`Restored ${done.restored}.`);
  }

  /** Put the map the caller picked into the save. */
  async function addPicked() {
    const doc = pickMap && pickMap();
    if (!doc) return;
    // Warn about the thing no undo reaches: this writes to a file the game
    // owns.
    if (!confirm(`Add "${doc.name || 'Untitled'}" to the save?\n\n` +
                 'A backup is taken first, and the game must be closed.')) {
      return;
    }
    say('Writing…');
    const got = await saves.importMap(savePath, doc);
    if (!got.ok) {
      const detail = (got.findings ?? [])
        .map((f) => `\n  ${f.code}: ${f.message}`).join('');
      alert(got.error + detail);
      return open(savePath);
    }
    await open(savePath);
    alert(`Added as slot ${got.slot}.\nBackup: ${got.backup}`);
  }

  async function removeAt(index) {
    const entry = entries[index];
    if (!confirm(`Remove "${entry.name || '(unnamed)'}" from the save?\n\n` +
                 'A backup is taken first.')) return;
    say('Writing…');
    const got = await saves.removeMap(savePath, index);
    if (!got.ok) {
      alert(got.error);
      return open(savePath);
    }
    await open(savePath);
  }

  refresh();
  return { refresh, addPicked, showBig };
}

/**
 * Show the panel only where a save can actually be reached.
 *
 * Returns null where there is no bridge, which is not a failure - it is the
 * boundary doing its job. Otherwise the panel's own handle, so the page can
 * hand it a map somebody picked.
 */
export async function attachIfDesktop(options) {
  if (!await saves.ready()) return null;
  options.panel.hidden = false;
  if (options.heading) options.heading.hidden = false;
  return attachSaves(options);
}
