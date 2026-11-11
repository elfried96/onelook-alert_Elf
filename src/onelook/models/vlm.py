"""Petit VLM (piste du mentor) : la tuile vue comme deux images, une question, une lettre en réponse.

Le modèle reçoit la tuile en couleurs naturelles (B04, B03, B02) et en infrarouge court (B12, B08, B04), puis
choisit A (normal), B (inondation) ou C (incendie). On ne le laisse pas écrire librement : on lit, en une
seule passe, ses scores pour les trois lettres au point où il commencerait à répondre. Ces trois scores
deviennent des probabilités, traitées exactement comme celles du réseau (seuil « inconnu », mêmes mesures).
L'affinage LoRA entraîne directement ces trois scores (entropie croisée), sur Colab uniquement.

Dépendances : groupe « vlm » (torch, transformers, peft), installé sur Colab, ou à la volée pour un essai local.
"""

from __future__ import annotations

import numpy as np
import torch
from PIL import Image

from onelook.data.labels import CLASSES
from onelook.demo.tiles import VIEWS, stretch

DEFAULT_MODEL = "HuggingFaceTB/SmolVLM-256M-Instruct"
SIDE = 384  # côté des images données au VLM (une seule « tuile » d'encodeur, sans découpage)
LETTERS = ["A", "B", "C"]  # dans l'ordre de CLASSES : normal, inondation, incendie
PROMPT = (
    "You see one Sentinel-2 satellite tile (about 5 x 5 km) twice. Image 1: natural colours. "
    "Image 2: false colours (SWIR, near infrared, red), where water is black or dark blue, vegetation is green "
    "and freshly burned ground is red-brown.\n"
    "Rivers, lakes, sea, reservoirs, rice paddies, snow, deserts and old lava are normal.\n"
    "Which is true for this tile?\n"
    "A) normal, nothing to report\n"
    "B) flood: water covering land that is usually dry\n"
    "C) recent wildfire: a large freshly burned area\n"
    "Answer with one letter."
)


def gpu_dtype() -> torch.dtype:
    """bfloat16 sur les GPU qui le gèrent, float16 sinon (T4 de Colab)."""
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


def tile_images(image: np.ndarray) -> list[Image.Image]:
    """Les deux vues de la tuile (6 bandes dans l'ordre du modèle), réduites à SIDE × SIDE."""
    return [Image.fromarray(stretch(image[list(VIEWS[v])])).resize((SIDE, SIDE), Image.BILINEAR)
            for v in ("naturel", "swir")]


class VLMClassifier:
    """Un VLM de la famille SmolVLM utilisé comme classifieur à trois décisions."""

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
        self.letter_ids = self._letter_ids()

    def _letter_ids(self) -> list[list[int]]:
        """Jetons de chaque lettre, avec et sans espace devant (selon le découpage du tokenizer)."""
        tokenizer = self.processor.tokenizer
        ids = []
        for letter in LETTERS:
            variants = {tokenizer.encode(t, add_special_tokens=False)[0] for t in (letter, " " + letter)}
            ids.append(sorted(variants))
        return ids

    def inputs(self, images: list[list[Image.Image]]) -> dict:
        messages = [{"role": "user", "content": [{"type": "image"}, {"type": "image"}, {"type": "text", "text": PROMPT}]}]
        # Le modèle commence sa réponse par « Answer: » : on l'écrit pour lui, la lettre vient juste après.
        prompt = self.processor.apply_chat_template(messages, add_generation_prompt=True) + " Answer:"
        batch = self.processor(text=[prompt] * len(images), images=images, return_tensors="pt", padding=True)
        return {k: v.to(self.device) for k, v in batch.items()}

    def letter_logits(self, batch: dict) -> torch.Tensor:
        """Scores des trois lettres (N, 3) à la dernière position : log-somme des variantes de chaque lettre."""
        logits = self.model(**batch).logits
        mask = batch["attention_mask"]
        last = mask.shape[1] - 1 - mask.flip(1).argmax(1)  # dernière position réelle, même avec bourrage à gauche ou à droite
        final = logits[torch.arange(len(last)), last].float()
        return torch.stack([final[:, ids].logsumexp(1) for ids in self.letter_ids], dim=1)

    @torch.no_grad()
    def predict(self, tiles: list[np.ndarray]) -> np.ndarray:
        """Probabilités (N, 3) dans l'ordre de CLASSES."""
        batch = self.inputs([tile_images(t) for t in tiles])
        return torch.softmax(self.letter_logits(batch), dim=1).cpu().numpy()


assert len(LETTERS) == len(CLASSES)
