import pytest


@pytest.mark.test_data
def test_dataset1d(base_config_1d):
    from asgardpy.analysis import AsgardpyAnalysis

    analysis = AsgardpyAnalysis(base_config_1d)

    analysis.get_1d_datasets


@pytest.mark.test_data
def test_only_1d_full_analysis(base_config_1d):
    analysis = AsgardpyAnalysis(base_config_1d)

    analysis.config.fit_params.fit_range.min = "500 GeV"

    analysis.run(["datasets-1d"])
    analysis.run(["fit"])
    analysis.run(["flux-points"])
