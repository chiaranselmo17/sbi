from typing import Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch import Tensor

from sbi.neural_nets.embedding_nets import GaussianFourierTimeEmbedding
from sbi.neural_nets.estimators.score_estimator import (
    ConditionalScoreEstimator,
    VEScoreEstimator,
    VPScoreEstimator,
    subVPScoreEstimator,
)
from sbi.utils.sbiutils import standardizing_net, z_score_parser, z_standardization
from sbi.utils.user_input_checks import check_data_device


class EmbedInputs(nn.Module):
    """Constructs input layer that concatenates (and optionally standardizes and/or
    embeds) the input and conditioning variables, as well as the diffusion time
    embedding.
    """

    def __init__(self, embedding_net_x, embedding_net_y, embedding_net_t, dim_x, dim_y):
        """Initializes the input layer.

        Args:
            embedding_net_x: Embedding network for x.
            embedding_net_y: Embedding network for y.
            embedding_net_t: Embedding network for time.
            dim_x: dimensionality of x.
            dim_y: dimensionality of y.
        """
        super().__init__()
        self.embedding_net_x = embedding_net_x
        self.embedding_net_y = embedding_net_y
        self.embedding_net_t = embedding_net_t
        self.dim_x = dim_x
        self.dim_y = dim_y

    def forward(self, inputs: list) -> Tensor:
        """Forward pass of the input layer.

        Args:
            inputs: List containing raw theta, x, and diffusion time.

        Returns:
            Concatenated and potentially standardized and/or embedded output.
        """

        assert (
            isinstance(inputs, list) and len(inputs) == 3
        ), """Inputs to network must be a list containing raw theta, x, and 1d time."""

        embeddings = [
            self.embedding_net_x(inputs[0]),
            self.embedding_net_y(inputs[1]),
            self.embedding_net_t(inputs[2]),
        ]
        out = torch.cat(
            embeddings,
            dim=-1,
        )
        return out


def build_input_layer(
    batch_x: Tensor,
    batch_y: Tensor,
    t_embedding_dim: int,
    z_score_x: Optional[str] = None,
    z_score_y: Optional[str] = "independent",
    embedding_net_x: nn.Module = nn.Identity(),
    embedding_net_y: nn.Module = nn.Identity(),
    min_std: float = 1e-4,
) -> nn.Module:
    """Builds input layer for vector field regression, including time embedding, and
    optionally z-scores.

    Args:
        batch_x: Batch of xs, used to infer dimensionality and (optional) z-scoring.
        batch_y: Batch of ys, used to infer dimensionality and (optional) z-scoring.
        t_embedding_dim: Dimensionality of the time embedding.
        z_score_x: Whether to z-score xs passing into the network, can be one of:
            - `none`, or None: do not z-score.
            - `independent`: z-score each dimension independently.
            - `structured`: treat dimensions as related, therefore compute mean and std
            over the entire batch, instead of per-dimension. Should be used when each
            sample is, for example, a time series or an image.
        z_score_y: Whether to z-score ys passing into the network, same options as
            z_score_x.
        embedding_net_x: Optional embedding network for x.
        embedding_net_y: Optional embedding network for y.

    Returns:
        Input layer that concatenates x, y, and time embedding, optionally z-scores.
    """
    z_score_x_bool, structured_x = z_score_parser(z_score_x)
    if z_score_x_bool:
        # TODO remove will move to score_estimator
        embedding_net_x = nn.Sequential(
            standardizing_net(batch_x, structured_x), embedding_net_x
        )

    z_score_y_bool, structured_y = z_score_parser(z_score_y)
    if z_score_y_bool:
        embedding_net_y = nn.Sequential(
            standardizing_net(batch_y, structured_y), embedding_net_y
        )
    embedding_net_t = GaussianFourierTimeEmbedding(t_embedding_dim)
    input_layer = EmbedInputs(
        embedding_net_x,
        embedding_net_y,
        embedding_net_t,
        dim_x=batch_x.shape[1],
        dim_y=batch_y.shape[1],
    )
    return input_layer


def build_score_estimator(
    batch_x: Tensor,
    batch_y: Tensor,
    sde_type: Optional[str] = "vp",
    score_net: Optional[Union[str, nn.Module]] = "mlp",
    z_score_x: Optional[str] = None,
    z_score_y: Optional[str] = "independent",
    t_embedding_dim: int = 32,
    num_layers: int = 3,
    hidden_features: int = 100,
    embedding_net_x: nn.Module = nn.Identity(),
    embedding_net_y: nn.Module = nn.Identity(),
    **kwargs,
) -> ConditionalScoreEstimator:
    """Builds score estimator for score-based generative models.

    Args:
        batch_x: Batch of xs, used to infer dimensionality and (optional) z-scoring.
        batch_y: Batch of ys, used to infer dimensionality and (optional) z-scoring.
        sde_type: SDE type used, which defines the mean and std functions. One of:
            - 'vp': Variance preserving.
            - 'subvp': Sub-variance preserving.
            - 've': Variance exploding.
            Defaults to 'vp'.
        score_net: Type of regression network. One of:
            - 'mlp': Fully connected feed-forward network.
            - 'resnet': Residual network (NOT IMPLEMENTED).
            -  nn.Module: Custom network
            Defaults to 'mlp'.
        z_score_x: Whether to z-score xs passing into the network, can be one of:
            - `none`, or None: do not z-score.
            - `independent`: z-score each dimension independently.
            - `structured`: treat dimensions as related, therefore compute mean and std
            over the entire batch, instead of per-dimension. Should be used when each
            sample is, for example, a time series or an image.
        z_score_y: Whether to z-score ys passing into the network, same options as
            z_score_x.
        t_embedding_dim: Embedding dimension of diffusion time. Defaults to 16.
        num_layers: Number of MLP hidden layers. Defaults to 3.
        hidden_features: Number of hidden units per layer. Defaults to 50.
        embedding_net_x: Embedding network for x. Defaults to nn.Identity().
        embedding_net_y: Embedding network for y. Defaults to nn.Identity().
        kwargs: Additional arguments that are passed by the build function for score
            network hyperparameters.


    Returns:
        ScoreEstimator object with a specific SDE implementation.
    """

    """Builds score estimator for score-based generative models."""
    check_data_device(batch_x, batch_y)
    # check_embedding_net_device(embedding_net=embedding_net_x, datum=batch_y)
    # check_embedding_net_device(embedding_net=embedding_net_y, datum=batch_y)

    mean_0, std_0 = z_standardization(batch_x, z_score_x == "structured")

    input_layer = build_input_layer(
        batch_x,
        batch_y,
        t_embedding_dim,
        z_score_x,
        z_score_y,
        embedding_net_x,
        embedding_net_y,
    )

    # Infer the output dimensionalities of the embedding_net by making a forward pass.
    x_dim = batch_x.shape[1]
    x_numel = embedding_net_x(batch_x[:1]).numel()
    y_numel = embedding_net_y(batch_y[:1]).numel()
    if score_net == "mlp":
        score_net = MLP(
            x_numel + y_numel + t_embedding_dim,
            x_dim,
            hidden_dim=hidden_features,
            num_layers=num_layers,
        )
    elif score_net == "resnet":
        raise NotImplementedError
    elif isinstance(score_net, nn.Module):
        pass
    else:
        raise ValueError(f"Invalid score network: {score_net}")

    if sde_type == 'vp':
        estimator = VPScoreEstimator
    elif sde_type == 've':
        estimator = VEScoreEstimator
    elif sde_type == 'subvp':
        estimator = subVPScoreEstimator
    else:
        raise ValueError(f"SDE type: {sde_type} not supported.")

    neural_net = nn.Sequential(input_layer, score_net)
    return estimator(neural_net, batch_x.shape[1:], batch_y.shape[1:], **kwargs)


class MLP(nn.Module):
    """Simple fully connected neural network."""

    def __init__(self, input_dim, output_dim, hidden_dim=256, num_layers=3):
        super().__init__()
        self.layers = nn.ModuleList([nn.Linear(input_dim, hidden_dim)])
        for _ in range(num_layers - 1):
            self.layers.append(nn.Linear(hidden_dim, hidden_dim))
        self.layers.append(nn.Linear(hidden_dim, output_dim))

    def forward(self, x):
        for layer in self.layers[:-1]:
            x = F.relu(layer(x))
        return self.layers[-1](x)
