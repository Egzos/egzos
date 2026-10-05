# Copyright 2026 Ali Sasanian
# SPDX-License-Identifier: Apache-2.0
"""Every string the lifeboat renders, by its key in lifeboat.md §13 and the tap spec §13 — one place
in the codebase (lifeboat.md §5). Rendered verbatim; a new string needs a spec revision."""

from __future__ import annotations

from egzos.authz.presence import TAP_COPY

S: dict[str, str] = {
    # lifeboat.md §13
    "shell.container": "egzos · container {name} · {host}",
    "shell.viewer": "you · {user} · principal: interactive · present since {since}",
    "shell.window": "window open · {source} → {destination} · closes {closes}",
    "shell.lapsed": "presence lapsed at {at}",
    "nav.search": "search",
    "nav.pending": "pending · {n}",
    "nav.pending.zero": "pending",
    "search.label": "Search",
    "search.placeholder": "kind:rule scope:project:atlas vendor",
    "search.button": "Search",
    "search.clear": "Clear",
    "search.hints": "kind: · scope: · trust: · tag: · key: · ring: — free text searches titles and bodies",
    "search.invalid": "That query isn't valid. Check the prefixes below.",
    "results.recent": "Recent · {n} items",
    "results.count": "Results · {n}",
    "results.uncounted": "Results",
    "results.empty": "Nothing here yet. Items you can fetch will appear here.",
    "results.none": "No results.",
    "results.next": "Next 50",
    "row.untitled": "(untitled)",
    "item.ref": "ITEM {id} · {kind} · v{version}",
    "item.titled": "titled by {engine}",
    "section.content": "content",
    "section.provenance": "provenance",
    "section.trust": "trust",
    "section.lifecycle": "lifecycle",
    "section.tags": "tags and key",
    "content.more": "Show all",
    "content.empty": "(empty)",
    "content.download": "Download",
    "content.unavailable": "Download unavailable.",
    "prov.null": "—",
    "prov.actor": "actor",
    "prov.principal": "principal",
    "prov.client": "client",
    "prov.derived": "derived from",
    "prov.imported": "imported from",
    "prov.approved": "approved by",
    "life.created": "created",
    "life.updated": "updated",
    "life.version": "version",
    "meta.filename": "filename",
    "meta.size": "size",
    "meta.mime": "type",
    "meta.sha": "sha256",
    "row.meta": "{actor} · v{version}",
    # R8's trust and tags <dt> labels: §13 names none (design-gap #129); one place until it does.
    "dl.status": "status",
    "dl.tags": "tags",
    "dl.key": "key",
    "item.scope": "in {scope} · ring {ring}",
    "item.scope.root": "in {scope}",
    "trust.promoted": "promoted {at} · manifest sha256 {prefix}…",
    "act.promote": "Promote to verified",
    "act.promote.confirm": "Confirm promotion",
    "act.promote.sr": "Press again to confirm.",
    "act.promote.inflight": "Promoting…",
    "act.lapsed": "Presence lapsed at {at}. Nothing changed. Sign again to continue.",
    "act.invalid": "This item changed. Reload to see it.",
    "act.error": "That didn't go through. Nothing changed. Try again.",
    "scheme.light": "light",
    "scheme.darkNeutral": "dark · neutral",
    "scheme.darkViolet": "dark · violet",
    "notfound.title": "Nothing here.",
    "fail.error": "Something went wrong on the container. Nothing changed. Try again.",
    "fail.retry": "Retry",
    # R12's card label, verbatim (the card's word has no §13 key of its own).
    "card.error": "error",
    "print.footer": "printed {at} · {container}",
    "title.home": "egzos · search",
    "title.item": "egzos · item",
    "title.notfound": "egzos",
    # the tap spec §13 (the pending pages, rendered by the lifeboat per lifeboat.md R11)
    "title.pending": "egzos · pending",
    "queue.title": "Pending",
    "queue.count": "{n} waiting for you",
    "queue.empty": "Nothing is waiting for you.",
    "kind.publish": "publish · outward",
    "kind.quarantine": "quarantined · propagated",
    # The tap spec's R3 `quarantined` row, verbatim (its meta has no §13 key of its own).
    "queue.quarantine.meta": "derived_from {id} · quarantined {at}",
    "ref.proposal": "PROPOSAL {id} · filed {at}",
    "title.move": "Move {n} items outward: {source} → {destination}",
    "reason.attr": "{who} states:",
    "reason.none": "(no reason given)",
    "reason.more": "Show full reason",
    "section.moves": "what moves",
    "section.audience": "who will see it at {destination}",
    "section.presence": "presence",
    "moves.reset": "agent-run move resets",
    "moves.quarantined": "Contains a quarantined item. It cannot move.",
    "audience.count": "{people} people · {agents} agents · resolved from token grants and scope membership",
    "consequence": "Consequence. Everything under {destination} inherits this — every team, project and thread, now and in future.",
    "presence.zero": "Signing proves you are here. No window opens.",
    "act.sign": "Sign and approve",
    "act.confirm": "Confirm signature",
    "act.confirm.sr": "Press again to confirm.",
    "act.inflight": "Signing…",
    "act.deny": "Deny",
    "act.nowindow": "Approve without a window",
    "window.open": "window open · closes {closes}",
    "tap.return": "Return to pending",
    # The outcome lines, shared with the tap the CLI hosts — defined once, in presence.TAP_COPY.
    **TAP_COPY,
}


def around(key: str, slot: str, **values: object) -> tuple[str, str]:
    """The text before and after `{slot}` in the string for `key`, the other placeholders filled:
    for a string that wraps markup (a link) the template puts between the two halves."""
    before, after = S[key].split("{" + slot + "}")
    return before.format(**values), after.format(**values)


def number_free(key: str) -> str:
    """A counted header without its number (R3 `empty`): the string up to its first ` · `."""
    return S[key].split(" · ")[0]


def t(key: str, **values: object) -> str:
    """The string for `key`, with its placeholders filled. Values are escaped by the template."""
    return S[key].format(**values) if values else S[key]
