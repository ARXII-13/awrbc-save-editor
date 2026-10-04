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
 * The caller hands maps in with `queue()` - documents it got from somewhere
 * else, because this tool does not make them. It used to reach for
 * `currentDoc()`, the map open in the editor, which is exactly the coupling
 * the split removes.
 *
 * Nothing written here is immediate. Marks and queued maps accumulate until
 * `commit()`, which is one read, one backup and one write however many
 * changes are riding on it.
 */
export function attachSaves({ panel, poster, importControl }) {
  let savePath = null;
  let entries = [];
  let found = [];        // every save on this machine, not just the open one

  // What has been decided but not yet written. Nothing here has touched the
  // save: `going` holds indices marked for removal, `queued` holds documents
  // waiting to go in. Writing once at the end is the point - a write per map
  // meant a backup per map, and a half-finished clear-out left five
  // snapshots and five chances for the game to be reopened in the middle.
  let going = new Set();
  let queued = [];

  const pending = () => going.size + queued.length;
  function clearStaged() { going = new Set(); queued = []; }

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
    found = got.saves ?? [];
    if (!found.length) {
      // Deliberately not naming one emulator. A save can come from any of
      // them, or off a modded console, and telling somebody their Ryujinx
      // save is missing when they do not use Ryujinx is worse than saying
      // nothing.
      return say('No Advance Wars save found on this machine. ' +
                 'If yours is somewhere else - a portable install, or a ' +
                 'copy off a console - the command line can be pointed at ' +
                 'it with --save-dir.');
    }
    savePath = savePath ?? found[0].path;
    await open(savePath);
  }

  /** The save currently open, as the locator described it. */
  function current() {
    return found.find((s) => s.path === savePath);
  }

  /**
   * One button per save, when there is a choice to make.
   *
   * Two profiles in one emulator, or two emulators side by side, both end up
   * here. Hidden entirely for the ordinary case of a single save, because a
   * row of one button is a decision nobody has.
   */
  function switcher() {
    const browse = el('button', {
      title: 'Point at a save yourself - a folder, or the maps file',
      textContent: 'Open a save…' });
    browse.onclick = browseForSave;

    // A row of buttons was fine for two and a mess for four, which is what
    // a machine with two profiles and a folder copy actually produces. A
    // list is the ordinary control for picking one of several and does not
    // grow sideways.
    if (found.length < 2) {
      return el('div', { className: 'saverow' }, browse);
    }

    const pick = el('select', { className: 'savepick' });
    for (const save of found) {
      const opt = el('option', {
        value: save.path,
        textContent: save.label || save.source || 'save',
      });
      if (save.path === savePath) opt.selected = true;
      pick.append(opt);
    }
    pick.onchange = () => {
      const chosen = pick.value;
      if (!chosen || chosen === savePath) return;
      if (pending() && !confirm(
          'You have unsaved changes. Switching saves forgets them.\n\n' +
          'The save itself has not been touched.')) {
        pick.value = savePath;        // put the list back where it was
        return;
      }
      clearStaged();
      savePath = chosen;
      open(chosen);
    };

    return el('div', { className: 'saverow' },
      el('span', { className: 'rowlabel', textContent: 'Save' }),
      pick, browse);
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

  /**
   * A map waiting to go in, drawn like the ones already there.
   *
   * Same card, because it is the same kind of thing and will look exactly
   * like this once it lands. The difference is said in a badge rather than
   * in a different shape.
   */
  function queuedCard(item, i) {
    const named = (item.name || item.document?.name || '').trim();
    const author = (item.document?.author || '').trim();

    const undo = el('button', {
      title: 'Do not add this one after all', textContent: 'Remove' });
    undo.onclick = () => { queued.splice(i, 1); render(); };

    return el('div', { className: 'mapcard coming' },
      el('button', {
        className: 'thumb', title: 'Show this map bigger',
        onclick: () => showBig({ name: named, document: item.document }),
      }, poster(item.document, THUMB)),
      el('div', { className: 'meta' },
        el('div', { className: named ? 'name' : 'name unnamed',
                    textContent: named || 'Untitled' }),
        el('div', { className: author ? 'by' : 'by anon',
                    textContent: author ? 'by ' + author : 'no author' }),
        el('div', { className: 'facts' },
          el('span', { className: 'badge coming',
                       textContent: 'will be added' }),
          el('span', {
            className: 'badge key',
            textContent: `${item.document?.size?.cols ?? '?'}×${item.document?.size?.rows ?? '?'}`,
          }))),
      el('div', { className: 'cardactions' }, undo));
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
    //
    // Marks rather than removes. Nothing leaves the save until Save changes,
    // so this is reversible right up to that point and says so by turning
    // into its own undo.
    const marked = going.has(i);
    const drop = el('button', {
      className: marked ? '' : 'danger',
      title: marked ? 'Keep this map after all'
                    : 'Mark this map to be removed when you save',
      textContent: marked ? 'Keep' : 'Remove',
    });
    drop.onclick = () => {
      if (marked) going.delete(i); else going.add(i);
      render();
    };

    const author = (entry.document?.author || '').trim();
    const named = (entry.name || '').trim();

    return el('div', { className: marked ? 'mapcard going' : 'mapcard' },
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
          ...(marked ? [el('span', { className: 'badge going',
                                     textContent: 'will be removed' })] : []),
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
    const where = current();
    const head = el('div', { className: 'listhead' },
      el('h2', { textContent: count === 1 ? '1 map in this save'
                                          : `${count} maps in this save` }),
      // Whichever of the two is not already on screen. With the switcher
      // up, the selected chip has said which save this is, so repeating it
      // here wastes the line that could carry the path instead.
      el('span', {
        className: 'sub', title: savePath || '',
        textContent: (found.length > 1
          ? savePath
          : where?.label || savePath) || '',
      }));

    const pickers = switcher();
    const bar = commitBar();

    const list = (count || queued.length)
      ? el('div', { className: 'maplist' },
           ...entries.map((entry, i) => card(entry, i)),
           ...queued.map((item, i) => queuedCard(item, i)))
      : el('div', { className: 'notice',
                    textContent: 'No custom maps in this save yet.' });

    // The import control belongs to the page, which knows how to read a
    // file; it is placed here so every control sits on one row instead of
    // the page drawing a toolbar above the panel's own.
    panel.replaceChildren(
      el('div', { className: 'toolbar' },
         ...(importControl ? [importControl] : []), takeBackup, roll),
      ...(pickers ? [pickers] : []),
      ...(bar ? [bar] : []),
      head,
      list);
  }

  /**
   * What is about to happen, and the two buttons that decide it.
   *
   * Absent entirely when nothing is staged, so the panel in its resting
   * state looks exactly as it did before any of this existed.
   */
  function commitBar() {
    if (!pending()) return null;

    const parts = [];
    if (going.size) parts.push(going.size === 1 ? '1 map to remove'
                                                : `${going.size} maps to remove`);
    if (queued.length) parts.push(queued.length === 1 ? '1 to add'
                                                      : `${queued.length} to add`);

    const save = el('button', {
      className: 'btn primary',
      title: 'Write every pending change to the save, in one go',
      textContent: 'Save changes' });
    save.onclick = commit;

    const drop = el('button', {
      title: 'Forget the pending changes. The save has not been touched.',
      textContent: 'Discard' });
    drop.onclick = () => { clearStaged(); render(); };

    return el('div', { className: 'commitbar' },
      el('span', { className: 'what', textContent: parts.join(', ') }),
      el('span', { className: 'spacer' }),
      drop, save);
  }

  /** Add maps to the queue. Nothing is written until Save changes. */
  function queue(documents) {
    const list = Array.isArray(documents) ? documents : [documents];
    for (const document of list) {
      if (document) queued.push({ document, name: document.name || null });
    }
    render();
  }

  /** Write everything at once. */
  async function commit() {
    if (!pending()) return;
    const bits = [];
    if (going.size) {
      bits.push(`remove ${going.size} map${going.size === 1 ? '' : 's'}`);
    }
    if (queued.length) {
      bits.push(`add ${queued.length} map${queued.length === 1 ? '' : 's'}`);
    }
    // The one warning worth keeping: this writes to a file the game owns.
    if (!confirm(`Save changes to ${bits.join(' and ')}?\n\n` +
                 'A backup is taken first, and the game must be closed.')) {
      return;
    }

    say('Writing…');
    const got = await saves.applyChanges(
      savePath, [...going], queued.map((q) => ({ document: q.document,
                                                 name: q.name })));
    if (!got.ok) {
      const detail = (got.findings ?? [])
        .map((f) => `\n  ${f.code}: ${f.message}`).join('');
      alert(got.error + detail);
      // Kept, not thrown away - the queue is what somebody would have to
      // rebuild by hand, and a refused batch changed nothing.
      return render();
    }
    clearStaged();
    await open(savePath);
    const done = [];
    if (got.removed?.length) done.push(`removed ${got.removed.length}`);
    if (got.added?.length) done.push(`added ${got.added.length}`);
    alert(`Saved: ${done.join(', ')}.\nBackup: ${got.backup}`);
  }

  /** Point at a save by hand - the answer for a console dump. */
  async function browseForSave() {
    if (pending() && !confirm(
        'You have unsaved changes. Opening another save forgets them.\n\n' +
        'The save itself has not been touched.')) {
      return;
    }
    const got = await saves.browseForSave('folder');
    if (!got.ok) return alert(got.error);
    if (got.cancelled || !got.saves?.length) return;

    // Added to the list rather than replacing it, so a hand-picked save
    // sits beside the found ones and can be switched back from.
    for (const save of got.saves) {
      if (!found.some((s) => s.path === save.path)) found.push(save);
    }
    clearStaged();
    savePath = got.saves[0].path;
    await open(savePath);
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

  refresh();
  return { refresh, queue, commit, showBig };
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
