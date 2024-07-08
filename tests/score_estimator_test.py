# This file is part of sbi, a toolkit for simulation-based inference. sbi is licensed
# under the Apache License Version 2.0, see <https://www.apache.org/licenses/>

from __future__ import annotations

from typing import Tuple

import pytest
import torch

from sbi.neural_nets.score_nets import build_score_estimator

# TODO: Test different build options for score estimators!


@pytest.mark.parametrize(
    "sde_type",
    [
        "vp",
        "ve",
        "subvp",
    ],
)
@pytest.mark.parametrize("input_sample_dim", (1, 2))
@pytest.mark.parametrize("input_event_shape", ((1,), (4,)))
@pytest.mark.parametrize("condition_event_shape", ((1,), (7,)))
@pytest.mark.parametrize("batch_dim", (1, 10))
def test_score_estimator_loss_shapes(
    sde_type,
    input_sample_dim,
    input_event_shape,
    condition_event_shape,
    batch_dim,
):
    """Test whether `loss` of DensityEstimators follow the shape convention."""
    score_estimator, inputs, conditions = _build_score_estimator_and_tensors(
        sde_type,
        input_event_shape,
        condition_event_shape,
        batch_dim,
        input_sample_dim,
    )

    losses = score_estimator.loss(inputs[0], condition=conditions)
    assert losses.shape == (batch_dim,)


@pytest.mark.parametrize(
    "sde_type",
    [
        "vp",
        "ve",
        "subvp",
    ],
)
@pytest.mark.parametrize("input_sample_dim", (1, 2))
@pytest.mark.parametrize("input_event_shape", ((1,), (4,)))
@pytest.mark.parametrize("condition_event_shape", ((1,), (7,)))
@pytest.mark.parametrize("batch_dim", (1, 10))
def test_score_estimator_forward_shapes(
    sde_type,
    input_sample_dim,
    input_event_shape,
    condition_event_shape,
    batch_dim,
):
    """Test whether `forward` of DensityEstimators follow the shape convention."""
    score_estimator, inputs, conditions = _build_score_estimator_and_tensors(
        sde_type,
        input_event_shape,
        condition_event_shape,
        batch_dim,
        input_sample_dim,
    )
    # Batched times
    times = torch.rand((batch_dim,))
    outputs = score_estimator(inputs[0], condition=conditions, time=times)
    assert outputs.shape == (batch_dim, *input_event_shape), "Output shape mismatch."

    # Single time
    time = torch.rand(())
    outputs = score_estimator(inputs[0], condition=conditions, time=time)
    assert outputs.shape == (batch_dim, *input_event_shape), "Output shape mismatch."


def _build_score_estimator_and_tensors(
    sde_type: str,
    input_event_shape: Tuple[int],
    condition_event_shape: Tuple[int],
    batch_dim: int,
    input_sample_dim: int = 1,
    **kwargs,
):
    """Helper function for all tests that deal with shapes of density estimators."""

    # Use discrete thetas such that categorical density esitmators can also use them.
    building_thetas = torch.randint(
        0, 4, (1000, *input_event_shape), dtype=torch.float32
    )
    building_xs = torch.randn((1000, *condition_event_shape))

    # TODO Test other build options!
    # if len(condition_event_shape) > 1:
    #     embedding_net = CNNEmbedding(condition_event_shape, kernel_size=1)
    # else:
    #     embedding_net = torch.nn.Identity()

    score_estimator = build_score_estimator(
        torch.randn_like(building_thetas),
        torch.randn_like(building_xs),
        sde_type=sde_type,
    )

    inputs = building_thetas[:batch_dim]
    condition = building_xs[:batch_dim]

    inputs = inputs.unsqueeze(0)
    inputs = inputs.expand(input_sample_dim, -1, -1)
    condition = condition
    return score_estimator, inputs, condition