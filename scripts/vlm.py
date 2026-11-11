"""Piste du mentor : un petit VLM (SmolVLM) à la place du réseau, mesuré comme les autres approches.

Deux étapes :
    evaluate  décisions sur une partie (val, puis test) ; le seuil « inconnu » est calibré sur la validation
    train     affinage LoRA sur l'entraînement (GPU, Colab uniquement), meilleure époque sur la validation

    uv run --group vlm python scripts/vlm.py evaluate --name smolvlm256_zero --split val
    uv run --group vlm python scripts/vlm.py evaluate --name smolvlm256_zero --split test
    uv run --group vlm python scripts/vlm.py train --name smolvlm256_lora --epochs 2
    uv run --group vlm python scripts/vlm.py evaluate --name smolvlm256_lora --split val --adapter runs/smolvlm256_lora/adapter
Tout s'écrit dans runs/<nom>/ (config.json, decisions_<partie>_model.csv, eval_<partie>_model.json), comme pour le
réseau : scripts/calibrate.py et les figures d'échecs s'appliquent tels quels. --limit N : essai sur N tuiles.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from tqdm import tqdm

from onelook.data.labels import CLASSES
from onelook.data.pack import read_packed
from onelook.evaluation.metrics import confusion, decision_metrics, format_row
from onelook.models.vlm import DEFAULT_MODEL, PROMPT, VLMClassifier, gpu_dtype, tile_images
from onelook.ood.confidence import KEEP, calibrate_threshold, decisions

ROOT = Path(__file__).resolve().parents[1]


def load_classifier(model_id: str, adapter: Path | None, bits: int | None) -> VLMClassifier:
    clf = VLMClassifier(model_id, bits=bits)
    if adapter:
        from peft import PeftModel

        clf.model = PeftModel.from_pretrained(clf.model, str(adapter)).eval()
    return clf


def model_size_mb(clf: VLMClassifier) -> float:
    """Taille des poids en mémoire (poids quantifiés compris), adaptateur LoRA inclus."""
    return clf.model.get_memory_footprint() / 1e6


def evaluate(args: argparse.Namespace) -> None:
    run = ROOT / "runs" / args.name
    run.mkdir(parents=True, exist_ok=True)
    config_path = run / "config.json"
    config = json.loads(config_path.read_text()) if config_path.exists() else {}
    config.update(arch="vlm", model=args.model, adapter=str(args.adapter) if args.adapter else None,
                  bits=args.bits, classes=CLASSES, prompt=PROMPT)

    index = pd.read_csv(args.pack / "index.csv")
    index = index[index["split"] == args.split].reset_index(drop=True)
    if args.limit:
        index = index.groupby("label", group_keys=False).head(args.limit).reset_index(drop=True)
    clf = load_classifier(args.model, args.adapter, args.bits)

    probs = []
    for start in tqdm(range(0, len(index), args.batch), desc=f"VLM ({args.split})"):
        paths = index["path"].iloc[start:start + args.batch]
        probs.append(clf.predict([read_packed(args.pack / p)["image"] for p in paths]))
    probs = np.concatenate(probs)

    if args.split == "val":
        known = index["label"].isin(CLASSES).to_numpy()
        labels = np.array([CLASSES.index(c) for c in index.loc[known, "label"]])
        config.update(seuil_inconnu=calibrate_threshold(probs[known], labels), part_gardee=KEEP)
    if "seuil_inconnu" not in config:
        raise SystemExit("Pas de seuil « inconnu » : lancer d'abord --split val sur ce run")
    preds = decisions(probs, config["seuil_inconnu"])
    metrics = decision_metrics(index, preds)

    time_ms = None
    if args.timing:  # temps d'une tuile sur un seul cœur (CPU), comme pour le réseau ; seulement en local
        torch.set_num_threads(1)
        tiles = [read_packed(args.pack / p)["image"] for p in index["path"].head(args.timing + 1)]
        clf.predict(tiles[:1])
        times = []
        for tile in tiles[1:]:
            start = time.perf_counter()
            clf.predict([tile])
            times.append((time.perf_counter() - start) * 1000)
        time_ms = float(np.median(times))
    size_mb = model_size_mb(clf)

    print(confusion(index, preds), "\n")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print("\n" + format_row(f"{args.name} ({args.split})", metrics, size_mb, time_ms))
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))
    result = {"split": args.split, "modele": args.model, "taille_mo": size_mb, "temps_ms_1_coeur": time_ms,
              "limite": args.limit, **metrics}
    (run / f"eval_{args.split}_model.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    pd.DataFrame({"id": index["id"], "label": index["label"], "decision": preds,
                  **{f"p_{c}": probs[:, i] for i, c in enumerate(CLASSES)}}).to_csv(
        run / f"decisions_{args.split}_model.csv", index=False)


def train(args: argparse.Namespace) -> None:
    """Affinage LoRA : entropie croisée sur les scores des trois lettres. GPU requis (Colab)."""
    from peft import LoraConfig, get_peft_model
    from torch.utils.data import DataLoader

    from onelook.training.data import PackDataset, balanced_sampler, trainable

    if not torch.cuda.is_available():
        raise SystemExit("Pas de GPU : l'affinage tourne sur Colab, jamais en local")
    run = ROOT / "runs" / args.name
    run.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(args.seed)

    clf = VLMClassifier(args.model, dtype=torch.float32)  # poids en float32, calcul en précision mixte
    lora = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05,
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj"])
    clf.model = get_peft_model(clf.model, lora)
    clf.model.print_trainable_parameters()

    index = pd.read_csv(args.pack / "index.csv")
    train_idx, val_idx = trainable(index, "train"), trainable(index, "val")
    if args.smoke:  # essai éclair : deux pas, 16 tuiles de validation
        val_idx = val_idx.groupby("label", group_keys=False).head(6).reset_index(drop=True)
    loader = DataLoader(PackDataset(args.pack, train_idx, train=True, seed=args.seed), batch_size=args.batch,
                        sampler=balanced_sampler(train_idx), num_workers=2, collate_fn=lambda b: b)
    optimizer = torch.optim.AdamW([p for p in clf.model.parameters() if p.requires_grad], lr=args.lr)
    steps = 2 if args.smoke else args.epochs * len(loader)
    amp = gpu_dtype()
    scaler = torch.amp.GradScaler(enabled=amp == torch.float16)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=steps, pct_start=0.1)

    history, best = [], -1.0
    for epoch in range(1, args.epochs + 1):
        clf.model.train()
        losses, start = [], time.time()
        for step, batch in enumerate(tqdm(loader, desc=f"Époque {epoch}")):
            if args.smoke and step == steps:
                break
            images = [tile_images(image.numpy()) for image, _ in batch]
            labels = torch.tensor([label for _, label in batch], device=clf.device)
            with torch.autocast("cuda", dtype=amp):
                logits = clf.letter_logits(clf.inputs(images))
            loss = torch.nn.functional.cross_entropy(logits, labels)
            optimizer.zero_grad()
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            losses.append(loss.item())
        clf.model.eval()
        with torch.autocast("cuda", dtype=amp):
            probs = np.concatenate([clf.predict([read_packed(args.pack / p)["image"] for p in val_idx["path"].iloc[i:i + 16]])
                                    for i in range(0, len(val_idx), 16)])
        metrics = decision_metrics(val_idx, np.array(CLASSES, dtype=object)[probs.argmax(1)])
        history.append({"epoque": epoch, "perte": float(np.mean(losses)), "duree_s": round(time.time() - start, 1),
                        **metrics})
        print(json.dumps(history[-1], ensure_ascii=False))
        if args.smoke:
            break
        if metrics["f1_macro"] > best:
            best = metrics["f1_macro"]
            clf.model.save_pretrained(run / "adapter")
    (run / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False))
    (run / "config.json").write_text(json.dumps({"arch": "vlm", "model": args.model, "lora_rang": args.rank,
                                                 "epochs": args.epochs, "lr": args.lr, "batch": args.batch,
                                                 "classes": CLASSES, "prompt": PROMPT}, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="step", required=True)
    for name in ("evaluate", "train"):
        p = sub.add_parser(name)
        p.add_argument("--name", required=True, help="Dossier runs/<nom>")
        p.add_argument("--model", default=DEFAULT_MODEL)
        p.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
        p.add_argument("--batch", type=int, default=8)
    ev = sub.choices["evaluate"]
    ev.add_argument("--split", default="test")
    ev.add_argument("--adapter", type=Path, help="Adaptateur LoRA (runs/<nom>/adapter)")
    ev.add_argument("--bits", type=int, choices=[4, 8], help="Quantification à la volée (GPU)")
    ev.add_argument("--limit", type=int, help="Essai : N tuiles par décision attendue")
    ev.add_argument("--timing", type=int, default=0, help="Tuiles chronométrées sur un cœur (local)")
    tr = sub.choices["train"]
    tr.add_argument("--epochs", type=int, default=2)
    tr.add_argument("--lr", type=float, default=2e-4)
    tr.add_argument("--rank", type=int, default=16)
    tr.add_argument("--seed", type=int, default=0)
    tr.add_argument("--smoke", action="store_true", help="Essai éclair : deux pas, rien d'enregistré")
    args = parser.parse_args()
    evaluate(args) if args.step == "evaluate" else train(args)


if __name__ == "__main__":
    main()
