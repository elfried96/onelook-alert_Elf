"""Petit VLM (piste du mentor) : la tuile vue comme deux images, une question, une réponse rédigée.

Le modèle reçoit la tuile en couleurs naturelles (B04, B03, B02) et en infrarouge court (B12, B08, B04), puis
répond par une lettre, A (normal), B (inondation) ou C (incendie), suivie d'une phrase sur ce qu'il voit.
La lettre se lit d'abord, en une passe : ses scores pour A, B et C deviennent des probabilités, traitées
exactement comme celles du réseau (seuil « inconnu », mêmes mesures). Le modèle écrit ensuite sa phrase à
partir de la lettre choisie, si bien que le texte ne contredit jamais la décision.
L'affinage LoRA apprend la lettre et une phrase modèle tirée des mesures de la tuile (`answer`), sur Colab.

Dépendances : groupe « vlm » (torch, transformers, peft), installé sur Colab, ou à la volée pour un essai local.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import torch
from PIL import Image

from onelook.data.labels import CLASSES, FIRE, FLOOD
from onelook.demo.tiles import VIEWS, stretch

DEFAULT_MODEL = "HuggingFaceTB/SmolVLM-256M-Instruct"
SIDE = 384  # côté des images données au VLM (une seule « tuile » d'encodeur, sans découpage)
LETTERS = ["A", "B", "C"]  # dans l'ordre de CLASSES : normal, inondation, incendie
END = "<end_of_utterance>"  # fin de tour de parole des modèles SmolVLM
PROMPT = (
    "You see one Sentinel-2 satellite tile (about 5 x 5 km) twice. Image 1: natural colours. "
    "Image 2: false colours (SWIR, near infrared, red), where water is black or dark blue, vegetation is green "
    "and freshly burned ground is red-brown.\n"
    "Rivers, lakes, sea, reservoirs, rice paddies, snow, deserts and old lava are normal.\n"
    "Which is true for this tile?\n"
    "A) normal, nothing to report\n"
    "B) flood: water covering land that is usually dry\n"
    "C) recent wildfire: a large freshly burned area\n"
    "Answer with the letter, then one short sentence saying what you see."
)
# Paysages des normales du catalogue, nommés dans les phrases modèles de l'affinage
LANDSCAPES = {
    "ocean": "open sea", "littoral": "a coastline", "estuaire": "an estuary", "riviere": "a river",
    "lac": "a lake", "reservoir": "a reservoir", "lagune_ville": "a lagoon and a city", "rizieres": "rice paddies",
    "desert": "desert", "salar": "a salt flat", "neige": "snow", "roche_volcanique": "old lava rock",
    "ville_asphalte": "a city", "sol_sombre_laboure": "dark ploughed fields", "nuages": "clouds",
    "ombres_relief": "mountain shadows", "foret_tropicale": "tropical forest", "agriculture": "farmland",
    "plantations": "plantations", "steppe": "steppe", "savane": "savanna", "toundra": "tundra",
}


def gpu_dtype() -> torch.dtype:
    """bfloat16 sur les GPU qui le gèrent, float16 sinon (T4 de Colab)."""
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def tile_images(image: np.ndarray) -> list[Image.Image]:
    """Les deux vues de la tuile (6 bandes dans l'ordre du modèle), réduites à SIDE × SIDE."""
    return [Image.fromarray(stretch(image[list(VIEWS[v])])).resize((SIDE, SIDE), Image.BILINEAR)
            for v in ("naturel", "swir")]


def _share(value: float) -> str:
    return f"about {max(5, round(100 * value / 5) * 5)}% of the tile"


def answer(row: pd.Series) -> str:
    """Réponse modèle d'une tuile pour l'affinage : la lettre, puis une phrase tirée des mesures de l'index."""
    if row["label"] == FLOOD:
        return f"B. Flood: water covers {_share(row['frac_flood'] * row['frac_valid'])} on land that is usually dry."
    if row["label"] == FIRE:
        return f"C. Wildfire: a fresh burn scar covers {_share(row['frac_burned'])}."
    if row["frac_permanent_jrc"] >= 0.05:
        return f"A. Normal: the water in view is permanent water (sea, river or lake), {_share(row['frac_permanent_jrc'])}."
    if row["scl_cloud"] >= 0.3:
        return "A. Normal: clouds hide much of the tile, no flood or burn scar in view."
    if row["category"] in LANDSCAPES:
        return f"A. Normal: {LANDSCAPES[row['category']]}, no flood water and no fresh burn scar."
    return "A. Normal: no flood water and no fresh burn scar."


class VLMClassifier:
    """Un VLM de la famille SmolVLM qui décide entre trois réponses et rédige sa justification."""

    def __init__(self, model_id: str = DEFAULT_MODEL, device: str | None = None, bits: int | None = None,
                 dtype: torch.dtype | None = None):
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.processor = AutoProcessor.from_pretrained(model_id)
        self.processor.image_processor.do_image_splitting = False
        self.processor.image_processor.size = {"longest_edge": SIDE}
        kwargs = {"dtype": dtype or (gpu_dtype() if self.device == "cuda" else torch.float32)}
        if bits:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=bits == 4, load_in_8bit=bits == 8, bnb_4bit_compute_dtype=gpu_dtype())
            kwargs["device_map"] = {"": self.device}
        self.model = AutoModelForImageTextToText.from_pretrained(model_id, **kwargs)
        if not bits:
            self.model.to(self.device)
        self.model.eval()
        self.tokenizer = self.processor.tokenizer
        self.letter_ids = self._letter_ids()
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "image"}, {"type": "text", "text": PROMPT}]}]
        # Le modèle commence sa réponse par « Answer: » : on l'écrit pour lui, la lettre vient juste après.
        self.prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True) + " Answer:"

    def _letter_ids(self) -> list[list[int]]:
        """Jetons de chaque lettre, avec et sans espace devant (selon le découpage du tokenizer)."""
        ids = []
        for letter in LETTERS:
            variants = {self.tokenizer.encode(t, add_special_tokens=False)[0] for t in (letter, " " + letter)}
            ids.append(sorted(variants))
        return ids

    def inputs(self, images: list[list[Image.Image]], suffixes: list[str] | None = None) -> dict:
        texts = [self.prompt + (s if suffixes else "") for s in (suffixes or [""] * len(images))]
        batch = self.processor(text=texts, images=images, return_tensors="pt", padding=True)
        return {k: v.to(self.device) for k, v in batch.items()}

    def letter_logits(self, batch: dict) -> torch.Tensor:
        """Scores des trois lettres (N, 3) à la dernière position : log-somme des variantes de chaque lettre."""
        logits = self.model(**batch).logits
        mask = batch["attention_mask"]
        last = mask.shape[1] - 1 - mask.flip(1).argmax(1)  # dernière position réelle, même avec bourrage à gauche ou à droite
        final = logits[torch.arange(len(last)), last].float()
        return torch.stack([final[:, ids].logsumexp(1) for ids in self.letter_ids], dim=1)

    def answer_loss(self, images: list[list[Image.Image]], answers: list[str]) -> torch.Tensor:
        """Perte de langage sur la réponse seule (lettre, phrase, fin de tour) : le prompt et les images ne comptent pas."""
        suffixes = [" " + a + END for a in answers]
        batch = self.inputs(images, suffixes)
        labels = torch.full_like(batch["input_ids"], -100)
        for i, suffix in enumerate(suffixes):
            n = len(self.tokenizer.encode(suffix, add_special_tokens=False))
            real = batch["attention_mask"][i].nonzero().squeeze(1)
            keep = real[-n:]
            labels[i, keep] = batch["input_ids"][i, keep]
        return self.model(**batch, labels=labels).loss

    @torch.no_grad()
    def predict(self, tiles: list[np.ndarray]) -> np.ndarray:
        """Probabilités (N, 3) dans l'ordre de CLASSES, sans rédaction (rapide)."""
        batch = self.inputs([tile_images(t) for t in tiles])
        return torch.softmax(self.letter_logits(batch), dim=1).cpu().numpy()

    @torch.no_grad()
    def describe(self, tiles: list[np.ndarray], max_new_tokens: int = 40) -> tuple[np.ndarray, list[str]]:
        """Probabilités (N, 3) et réponses rédigées : la lettre la plus probable, puis la phrase du modèle."""
        images = [tile_images(t) for t in tiles]
        probs = torch.softmax(self.letter_logits(self.inputs(images)), dim=1).cpu().numpy()
        letters = [LETTERS[k] for k in probs.argmax(1)]
        batch = self.inputs(images, [" " + letter for letter in letters])
        out = self.model.generate(**batch, max_new_tokens=max_new_tokens, do_sample=False)
        rest = self.tokenizer.batch_decode(out[:, batch["input_ids"].shape[1]:], skip_special_tokens=True)
        return probs, [f"{letter}{text}".strip() for letter, text in zip(letters, rest)]


assert len(LETTERS) == len(CLASSES)
