"""A Merkle root over a case's evidence, and a proof that one file was in it.

The report already prints every evidence hash, which lets a reader check any file they hold. It
does not let anybody fix the *set*: a file quietly dropped from a later report leaves the remaining
hashes all still correct. A root over the whole set is one value that changes if anything is added,
removed or reordered.

The property this buys in a courtroom is the inclusion proof. A court can be shown that one
particular file was in the case at the moment the report was generated, using a short path of
sibling hashes -- without being handed the hashes of every other file in the case, which are not
theirs to see and may belong to people who are not on trial.

**What the root proves and what it does not.** It fixes which files were in the set at that moment.
It says nothing about whether the contents are genuine, whether they were lawfully obtained, or
whether the file has since changed -- that last one is what the individual hash is for. A root over
a set of fabricated files is a perfectly valid root over a set of fabricated files.

The construction is deliberately the plain one. Leaves are the evidence SHA-256 values in a fixed
order; a lone node at any level is carried up rather than paired with itself, because duplicating
it is the classic construction bug that lets two different sets produce one root.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

MERKLE_VERSION = "merkle-v1"

WHAT_IT_PROVES = (
    "This root fixes which evidence files were held in this case when the report was generated: adding, removing or "
    "reordering any of them produces a different root. It does not establish that the files are genuine, that they "
    "were lawfully obtained, or that any one of them has not changed since -- the per-file hash is what answers that."
)


@dataclass
class Proof:
    """The short path showing one leaf belongs under a root, without revealing the other leaves."""

    leaf: str
    index: int
    path: list[dict[str, str]]
    root: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaf": self.leaf,
            "index": self.index,
            "path": self.path,
            "root": self.root,
            "merkle_version": MERKLE_VERSION,
            "proves": WHAT_IT_PROVES,
        }


def _pair(left: str, right: str) -> str:
    return hashlib.sha256(f"{left}{right}".encode("utf-8")).hexdigest()


def _levels(leaves: list[str]) -> list[list[str]]:
    """Every level of the tree, leaves first.

    A level with an odd count carries its last node up unchanged. Hashing it against itself -- the
    usual shortcut -- lets a set of n items and a set of n+1 where the last is duplicated produce
    the same root, which would make an inclusion proof provable for a file that was never there.
    """
    if not leaves:
        return []
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        current = levels[-1]
        nxt = [_pair(current[i], current[i + 1]) for i in range(0, len(current) - 1, 2)]
        if len(current) % 2:
            nxt.append(current[-1])
        levels.append(nxt)
    return levels


def root(leaves: list[str]) -> str | None:
    """One value standing for the whole set, or None when there is no set.

    A case with no evidence has no root rather than the hash of nothing: an empty case and a case
    whose evidence was removed must not present the same value.
    """
    levels = _levels(leaves)
    return levels[-1][0] if levels else None


def proof(leaves: list[str], index: int) -> Proof | None:
    """The sibling path from one leaf to the root."""
    levels = _levels(leaves)
    if not levels or not 0 <= index < len(leaves):
        return None

    path: list[dict[str, str]] = []
    position = index
    for level in levels[:-1]:
        if position % 2 == 0:
            if position + 1 < len(level):
                path.append({"side": "right", "hash": level[position + 1]})
            # No sibling: this node was carried up unchanged, so there is nothing to record.
        else:
            path.append({"side": "left", "hash": level[position - 1]})
        position //= 2
    return Proof(leaf=leaves[index], index=index, path=path, root=levels[-1][0])


def verify(leaf: str, path: list[dict[str, str]], expected_root: str) -> bool:
    """Recompute the root from one leaf and its path. This is what a court's own expert would run."""
    current = leaf
    for step in path:
        sibling = step.get("hash", "")
        current = _pair(sibling, current) if step.get("side") == "left" else _pair(current, sibling)
    return current == expected_root
