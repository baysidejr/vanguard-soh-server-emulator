"""Bring the server's content up to date with the archive scrape, in one command.

    python tools/refresh_archive.py              # report only: what would be added
    python tools/refresh_archive.py --apply      # add it, then check the content

It reads the collection branch's newest raw batches (without merging the branch), then runs the
zone import (NPCs, creatures, camps, zone-map people, altars and mailboxes, merchant stocks,
icons; tools/import_zone.py --all) and adds the archive quests that became playable
(tools/quest_readiness.py); with --apply it then moves spawns whose archive chunk label is wrong
(tools/chunk_audit.py) and reports quests that can't be finished (tools/quest_check.py). Nothing
already there is overwritten. The Sundering Wastelands and
Wildgrowth Forest keep their hand-made camps unless --all-zones is given.
Uses only the Python standard library.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import import_zone  # noqa: E402
import quest_readiness  # noqa: E402

KEEP = ("Sundering Wastelands", "Wildgrowth Forest")       # the hand-made camps


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true", help="add to server/content (otherwise report only)")
    ap.add_argument("--branch", default="origin/crowdsourced/archive-collection", help="the scrape's git branch")
    ap.add_argument("--all-zones", action="store_true", help="also import into " + " and ".join(KEEP))
    a = ap.parse_args(argv)
    import_zone.EXTRA_RAW.append(import_zone.branch_raw(a.branch))
    import_zone.SOURCES.append(f"branch {a.branch}")
    print("== zones ==")
    import_zone.import_all(a.apply, set() if a.all_zones else set(KEEP))
    print("== loot names ==")
    print(f"{import_zone.fix_loot_names(a.apply)} loot rows named from a URL slug get their apostrophe back (B-030)")
    print("== quest targets ==")
    quests, world, chunks = (import_zone.archive_npcs(kind="quest"), quest_readiness.zone_world(),
                             import_zone.zone_chunks())
    camps = quest_readiness.placeholder_camps(quests, world, chunks, import_zone.archive_npcs(kind="creature"))
    print(f"{sum(len(v) for v in camps.values())} kill targets without a location get a placeholder camp near the giver")
    if a.apply:
        loot = import_zone.archive_npcs(kind="loot")
        for level, entries in camps.items():
            mobs = {k: t for k, t, _ in entries}
            import_zone.attach_loot(mobs, loot)
            import_zone.apply(level, mobs, [sp for _, _, camp in entries for sp in camp])
        world = quest_readiness.zone_world()
    print("== quests ==")
    ready = sorted((q for q in quests.values() if quest_readiness.readiness(q, world, chunks) == "ready"),
                   key=lambda q: (q.get("zone") or "", q["name"]))
    print(f"{len(ready)} archive quests are playable with what is placed")
    deliveries, steps_for = quest_readiness.delivery_plan(quests, world, chunks)
    print(f"{len(deliveries)} more have no recorded objectives but a placed hand-in NPC: played as deliveries")
    if a.apply:
        print("added %d quests and %d items" % quest_readiness.apply(ready, world, chunks))
        print("added %d delivery quests (%d items)" % quest_readiness.apply(deliveries, world, chunks, steps_for=steps_for))
        print("linked %d quests to the quest before them in their chain" % quest_readiness.link_chains(quests))
        # Archive zone labels are sometimes wrong (Tracker Nok stood in the sea): move spawns whose
        # recorded height only fits a neighbouring chunk (backlog B-020), then check every offered
        # quest can still be finished (B-018).
        print("== chunks ==")
        import chunk_audit
        chunk_audit.main(["--apply"])
        print("== finishable quests ==")
        import quest_check
        quest_check.main([])
        print("== check ==")
        r = subprocess.run([sys.executable, "content.py"], cwd=os.path.join(ROOT, "server"))
        return r.returncode
    print("(run again with --apply to add them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
