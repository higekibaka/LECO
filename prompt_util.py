from typing import Literal, Optional

import yaml
from pathlib import Path


from pydantic import BaseModel, validator, root_validator
import torch

ACTION_TYPES = Literal["erase", "enhance"]


class PromptCache:
    prompts: dict[str, torch.FloatTensor] = {}

    def __setitem__(self, __name: str, __value: torch.FloatTensor) -> None:
        self.prompts[__name] = __value

    def __getitem__(self, __name: str) -> Optional[torch.FloatTensor]:
        if __name in self.prompts:
            return self.prompts[__name]
        else:
            return None


class PromptSettings(BaseModel):
    target: str
    positive: str = None  # if None, target will be used
    unconditional: str = ""  # default is ""
    neutral: str = None  # if None, unconditional will be used
    action: ACTION_TYPES = "erase"  # default is "erase"
    guidance_scale: float = 1.0  # default is 1.0
    resolution: int = 512  # default is 512
    dynamic_resolution: bool = False  # default is False
    batch_size: int = 1  # default is 1

    @root_validator(pre=True)
    def fill_prompts(cls, values):
        keys = values.keys()
        if "target" not in keys:
            raise ValueError("target must be specified")
        if "positive" not in keys:
            values["positive"] = values["target"]
        if "unconditional" not in keys:
            values["unconditional"] = ""
        if "neutral" not in keys:
            values["neutral"] = values["unconditional"]

        return values


class PromptPair:
    target: torch.FloatTensor  # not want to generate the concept
    positive: torch.FloatTensor  # generate the concept
    unconditional: torch.FloatTensor  # uncondition (default should be empty)
    neutral: torch.FloatTensor  # base condition (default should be empty)

    guidance_scale: float
    resolution: int
    dynamic_resolution: bool
    batch_size: int

    loss_fn: torch.nn.Module
    action: ACTION_TYPES

    def __init__(
        self,
        loss_fn: torch.nn.Module,
        target: torch.FloatTensor,
        positive: torch.FloatTensor,
        unconditional: torch.FloatTensor,
        neutral: torch.FloatTensor,
        guidance_scale: float,
        resolution: int,
        dynamic_resolution: bool,
        batch_size: int,
        action: ACTION_TYPES,
    ) -> None:
        self.loss_fn = loss_fn
        self.target = target
        self.positive = positive
        self.unconditional = unconditional
        self.neutral = neutral
        self.guidance_scale = guidance_scale
        self.resolution = resolution
        self.dynamic_resolution = dynamic_resolution
        self.batch_size = batch_size
        self.action = action

    def _erase(
        self,
        target_latents: torch.FloatTensor,  # "van gogh"
        positive_latents: torch.FloatTensor,  # "van gogh"
        unconditional_latents: torch.FloatTensor,  # ""
        neutral_latents: torch.FloatTensor,  # ""
    ) -> torch.FloatTensor:
        """Target latents are going not to have the positive concept."""

        return self.loss_fn(
            target_latents,
            neutral_latents
            - self.guidance_scale * (positive_latents - unconditional_latents),
        )

    def _enhance(
        self,
        target_latents: torch.FloatTensor,  # "van gogh"
        positive_latents: torch.FloatTensor,  # "van gogh"
        unconditional_latents: torch.FloatTensor,  # ""
        neutral_latents: torch.FloatTensor,  # ""
    ):
        """Target latents are going to have the positive concept."""

        return self.loss_fn(
            target_latents,
            neutral_latents
            + self.guidance_scale * (positive_latents - unconditional_latents),
        )

    def loss(
        self,
        **kwargs,
    ):
        if self.action == "erase":
            return self._erase(**kwargs)

        elif self.action == "enhance":
            return self._enhance(**kwargs)

        else:
            raise ValueError("action must be erase or enhance")


def load_prompts_from_yaml(path: str | Path) -> list[PromptSettings]:
    with open(path, "r") as f:
        prompts = yaml.safe_load(f)

    if len(prompts) == 0:
        raise ValueError("prompts file is empty")

    prompt_settings = [PromptSettings(**prompt) for prompt in prompts]

    return prompt_settings
