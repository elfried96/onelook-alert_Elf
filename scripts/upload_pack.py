"""Envoie le paquet d'entraînement (data/pack/) dans le dépôt de données privé Hugging Face.

Usage : uv run python scripts/upload_pack.py [--repo Elfried9684/onelook-alert-data] [--batch 200]
Prérequis : `uv run hf auth login` (droits d'écriture). Envoi par lots, un commit par lot :
une relance après coupure saute les fichiers déjà présents sur le dépôt.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import CommitOperationAdd, HfApi

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default="Elfried9684/onelook-alert-data")
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()

    api = HfApi()
    if not api.dataset_info(args.repo).private:
        raise SystemExit(f"{args.repo} est public : envoi refusé (le paquet doit rester privé)")
    remote = set(api.list_repo_files(args.repo, repo_type="dataset"))
    local = sorted(p.relative_to(args.pack).as_posix() for p in args.pack.rglob("*") if p.is_file())
    # L'index et la fiche en dernier : le dépôt n'annonce le paquet complet qu'une fois toutes les tuiles envoyées
    tiles = [p for p in local if p.startswith("tiles/") and p not in remote]
    meta = [p for p in local if not p.startswith("tiles/")]
    print(f"{len(local)} fichiers locaux, {len(remote)} déjà sur le dépôt, {len(tiles)} tuiles à envoyer")

    batches = [tiles[i:i + args.batch] for i in range(0, len(tiles), args.batch)] + [meta]
    for n, batch in enumerate(batches, 1):
        size = sum((args.pack / p).stat().st_size for p in batch) / 1e9
        api.create_commit(
            args.repo, repo_type="dataset",
            operations=[CommitOperationAdd(path_in_repo=p, path_or_fileobj=args.pack / p) for p in batch],
            commit_message=f"Paquet : lot {n}/{len(batches)} ({len(batch)} fichiers)",
        )
        print(f"Lot {n}/{len(batches)} envoyé : {len(batch)} fichiers, {size:.2f} Go", flush=True)
    print("Paquet complet sur", f"https://huggingface.co/datasets/{args.repo}")


if __name__ == "__main__":
    main()
