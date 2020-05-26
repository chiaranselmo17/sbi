import pytest
import torch
from torch import distributions, zeros, ones, eye

import sbi.utils as utils
from sbi.inference.snl.snl import SNL
import tests.utils_for_testing.linearGaussian_logprob as test_utils
from sbi.simulators.linear_gaussian import (
    get_true_posterior_samples_linear_gaussian_mvn_prior,
    get_true_posterior_samples_linear_gaussian_uniform_prior,
    linear_gaussian,
)
from sbi.user_input.user_input_checks import prepare_sbi_problem

# use cpu by default
torch.set_default_tensor_type("torch.FloatTensor")


@pytest.mark.parametrize("num_dim", (1, 3))
def test_snl_on_linearGaussian_api(num_dim: int):
    """Test API for inference on linear Gaussian model using SNL.

    Avoids expensive computations by training on few simulations and generating few
    posterior samples.

    Args:
        num_dim: parameter dimension of the gaussian model
    """
    num_samples = 10

    prior = distributions.MultivariateNormal(
        loc=zeros(num_dim), covariance_matrix=eye(num_dim)
    )

    simulator, prior, x_o = prepare_sbi_problem(linear_gaussian, prior, zeros(num_dim))

    infer = SNL(
        simulator=simulator,
        prior=prior,
        x_o=x_o,
        density_estimator=None,  # Use default MAF.
        simulation_batch_size=50,
        mcmc_method="slice_np",
    )

    posterior = infer(num_rounds=1, num_simulations_per_round=1000)

    posterior.sample(num_samples=num_samples, num_chains=1)


@pytest.mark.slow
@pytest.mark.parametrize("num_dim", (1, 3))
@pytest.mark.parametrize("prior_str", ("uniform", "gaussian"))
def test_snl_on_linearGaussian_based_on_mmd(num_dim: int, prior_str: str, set_seed):
    """Test SNL on linear Gaussian, comparing to ground truth posterior via MMD.

    NOTE: The MMD threshold is calculated based on a number of test runs and taking the
    mean plus 2 stds.

    This test is seeded using the set_seed fixture defined in tests/conftest.py.

    Args:
        num_dim: parameter dimension of the gaussian model
        prior_str: one of "gaussian" or "uniform"
        set_seed: fixture for manual seeding, see tests/conftest.py
    """

    x_o = zeros((1, num_dim))
    num_samples = 200

    if prior_str == "gaussian":
        prior = distributions.MultivariateNormal(
            loc=zeros(num_dim), covariance_matrix=eye(num_dim)
        )
        target_samples = get_true_posterior_samples_linear_gaussian_mvn_prior(
            x_o, num_samples=num_samples
        )
    else:
        prior = utils.BoxUniform(-1.0 * ones(num_dim), ones(num_dim))
        target_samples = get_true_posterior_samples_linear_gaussian_uniform_prior(
            x_o, num_samples=num_samples, prior=prior
        )

    simulator, prior, x_o = prepare_sbi_problem(linear_gaussian, prior, x_o)

    infer = SNL(
        simulator=simulator,
        prior=prior,
        x_o=x_o,
        density_estimator=None,  # Use default MAF.
        mcmc_method="slice_np",
    )

    posterior = infer(num_rounds=1, num_simulations_per_round=1000)

    samples = posterior.sample(num_samples=num_samples)

    # compute the mmd
    mmd = utils.unbiased_mmd_squared(target_samples, samples)

    # check if mmd is larger than expected
    # NOTE: the mmd is calculated based on a number of test runs
    max_mmd = 0.02

    assert (
        mmd < max_mmd
    ), f"MMD={mmd} is more than 2 stds above the average performance."

    # TODO: we do not have a test for SNL log_prob(). This is because the output
    # TODO: density is not normalized, so KLd does not make sense.
    if prior_str == "uniform":
        # Check whether the returned probability outside of the support is zero.
        posterior_prob = test_utils.get_prob_outside_uniform_prior(posterior, num_dim)
        assert (
            posterior_prob == 0.0
        ), "The posterior probability outside of the prior support is not zero"


@pytest.mark.slow
def test_multi_round_snl_on_linearGaussian_based_on_mmd(set_seed):
    """Test SNL on linear Gaussian, comparing to ground truth posterior via MMD.

    NOTE: The MMD threshold is calculated based on a number of test runs and taking the
    mean plus 2 stds.
    
    This test is seeded using the set_seed fixture defined in tests/conftest.py.

    Args:
        set_seed: fixture for manual seeding, see tests/conftest.py
    """

    num_dim = 3
    x_o = zeros((1, num_dim))
    num_samples = 200

    prior = distributions.MultivariateNormal(
        loc=zeros(num_dim), covariance_matrix=eye(num_dim)
    )
    target_samples = get_true_posterior_samples_linear_gaussian_mvn_prior(
        x_o, num_samples=num_samples
    )

    simulator, prior, x_o = prepare_sbi_problem(linear_gaussian, prior, x_o)

    infer = SNL(
        simulator=simulator,
        prior=prior,
        x_o=x_o,
        density_estimator=None,  # Use default MAF.
        simulation_batch_size=50,
        mcmc_method="slice",
    )

    posterior = infer(num_rounds=2, num_simulations_per_round=1000)

    samples = posterior.sample(num_samples=500)

    mmd = utils.unbiased_mmd_squared(target_samples, samples)

    # check if mmd is larger than expected
    # NOTE: the mmd is calculated based on a number of test runs
    max_mmd = 0.02

    assert (
        mmd < max_mmd
    ), f"MMD={mmd} is more than 2 stds above the average performance."


@pytest.mark.slow
@pytest.mark.parametrize(
    "mcmc_method, prior_str",
    (
        ("slice_np", "gaussian"),
        ("slice_np", "uniform"),
        ("slice", "gaussian"),
        ("slice", "uniform"),
    ),
)
def test_snl_posterior_correction(mcmc_method: str, prior_str: str, set_seed):
    """Test SNL on linear Gaussian, comparing to ground truth posterior via MMD.

    NOTE: The mmd threshold is calculated based on a number of test runs and taking the
    mean plus 2 stds.

    This test is seeded using the set_seed fixture defined in tests/conftest.py.

    Args:
        mcmc_method: which mcmc method to use for sampling
        prior_str: use gaussian or uniform prior
        set_seed: fixture for manual seeding, see tests/conftest.py
    """

    num_dim = 2
    num_samples = 30
    x_o = zeros((1, num_dim))

    if prior_str == "gaussian":
        prior = distributions.MultivariateNormal(
            loc=zeros(num_dim), covariance_matrix=eye(num_dim)
        )
    else:
        prior = utils.BoxUniform(-1.0 * ones(num_dim), ones(num_dim))

    simulator, prior, x_o = prepare_sbi_problem(linear_gaussian, prior, x_o)

    infer = SNL(
        simulator=simulator,
        prior=prior,
        x_o=x_o,
        density_estimator=None,  # Use default MAF.
        simulation_batch_size=50,
        mcmc_method="slice_np",
    )

    posterior = infer(num_rounds=1, num_simulations_per_round=1000)

    posterior.sample(num_samples=num_samples)