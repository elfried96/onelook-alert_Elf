"""Entraîne le réseau léger, choisit la meilleure époque sur la validation, exporte en ONNX.

Usage (sur Colab, GPU) : uv run python scripts/train.py --arch mobilenet_v3_small --epochs 15
Essai rapide sur CPU, pour vérifier que tout tourne : --smoke (quelques tuiles, deux pas).
Aucun entraînement réel en local : voir la page Reproduire.

Écrit dans runs/<nom>/ : model.onnx, config.json (normalisation, seuil « inconnu », mesures de
validation), history.json (courbes), best.pt (poids, non versionnés).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader

from onelook.data.labels import CLASSES
from onelook.data.pack import PACK_BANDS
from onelook.evaluation.metrics import decision_metrics
from onelook.models.cnn import ARCHS, OneLookNet
from onelook.ood.confidence import calibrate_threshold, decisions, softmax
from onelook.training.data import PackDataset, balanced_sampler, band_stats, trainable

ROOT = Path(__file__).resolve().parents[1]


@torch.no_grad()
def predict(model: nn.Module, loader: DataLoader, device: str) -> np.ndarray:
    model.eval()
    logits = [model(x.to(device, non_blocking=True)).float().cpu() for x, _ in loader]
    return torch.cat(logits).numpy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pack", type=Path, default=ROOT / "data" / "pack")
    parser.add_argument("--arch", choices=ARCHS, default="mobilenet_v3_small")
    parser.add_argument("--size", type=int, default=256, help="Côté de l'image vue par le réseau (512 = pleine résolution)")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--name", help="Nom du dossier runs/<nom> (par défaut : architecture et taille)")
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Essai : 24 tuiles, 2 pas, CPU accepté")
    args = parser.parse_args()

    torch.manual_seed(0)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" and not args.smoke:
        raise SystemExit("Pas de GPU : l'entraînement se lance sur Colab (ou --smoke pour un essai).")
    name = args.name or f"{args.arch}_{args.size}" + ("_smoke" if args.smoke else "")
    out = ROOT / "runs" / name
    out.mkdir(parents=True, exist_ok=True)

    index = pd.read_csv(args.pack / "index.csv")
    train_idx, val_idx = trainable(index, "train"), trainable(index, "val")
    if args.smoke:
        train_idx = train_idx.groupby("label").head(8).reset_index(drop=True)
        val_idx = val_idx.groupby("label").head(4).reset_index(drop=True)
        args.epochs, args.batch = 1, 4
    mean, std = band_stats(args.pack, train_idx, n=24 if args.smoke else 200)

    model = OneLookNet(args.arch, mean, std, size=args.size, pretrained=not args.no_pretrained).to(device)
    train_loader = DataLoader(PackDataset(args.pack, train_idx, train=True), batch_size=args.batch,
                              sampler=balanced_sampler(train_idx), num_workers=args.workers,
                              pin_memory=device == "cuda", drop_last=True, persistent_workers=args.workers > 0)
    val_loader = DataLoader(PackDataset(args.pack, val_idx), batch_size=args.batch, num_workers=args.workers)
    steps = 2 if args.smoke else len(train_loader) * args.epochs
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=steps)
    scaler = torch.amp.GradScaler(enabled=device == "cuda")
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.05)

    history, best_f1, step = [], -1.0, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        start, losses = time.time(), []
        for x, y in train_loader:
            with torch.autocast(device_type=device, enabled=device == "cuda"):
                loss = loss_fn(model(x.to(device, non_blocking=True)), y.to(device))
            optimizer.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            losses.append(loss.item())
            step += 1
            if step >= steps:
                break
        probs = softmax(predict(model, val_loader, device))
        val = decision_metrics(val_idx, np.array(CLASSES, dtype=object)[probs.argmax(axis=1)])
        history.append({"epoque": epoch, "perte": float(np.mean(losses)), "duree_s": round(time.time() - start, 1), **val})
        print(f"Époque {epoch:2d} · perte {np.mean(losses):.3f} · val F1 macro {val['f1_macro']:.3f} · "
              f"rappel inond. {val['rappel_inondation']:.0%} · incendie {val['rappel_incendie']:.0%} · "
              f"fausses alertes {val['fausses_alertes']:.1%} · {time.time() - start:.0f} s", flush=True)
        if val["f1_macro"] > best_f1:
            best_f1 = val["f1_macro"]
            torch.save(model.state_dict(), out / "best.pt")
        if step >= steps:
            break

    # Meilleure époque : seuil « inconnu » calibré sur la validation, puis export
    model.load_state_dict(torch.load(out / "best.pt", map_location=device))
    probs = softmax(predict(model, val_loader, device))
    threshold = calibrate_threshold(probs, np.array([CLASSES.index(c) for c in val_idx["label"]]))
    val_final = decision_metrics(val_idx, decisions(probs, threshold))
    model.eval().cpu()
    torch.onnx.export(model, torch.zeros(1, 6, 512, 512), out / "model.onnx", input_names=["image"],
                      output_names=["logits"], dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
                      opset_version=17, dynamo=False)
    config = {"arch": args.arch, "size": args.size, "bands": PACK_BANDS[:6], "classes": CLASSES,
              "mean": mean, "std": std, "seuil_inconnu": threshold, "epochs": args.epochs, "lr": args.lr,
              "batch": args.batch, "pretrained": not args.no_pretrained, "val": val_final,
              "parametres": sum(p.numel() for p in model.parameters())}
    (out / "config.json").write_text(json.dumps(config, indent=2, ensure_ascii=False))
    (out / "history.json").write_text(json.dumps(history, indent=2, ensure_ascii=False))
    size_mb = (out / "model.onnx").stat().st_size / 1e6
    print(f"\nMeilleure validation : F1 macro {best_f1:.3f} · seuil « inconnu » {threshold:.2f} · "
          f"ONNX {size_mb:.1f} Mo -> {out}")


if __name__ == "__main__":
    main()
