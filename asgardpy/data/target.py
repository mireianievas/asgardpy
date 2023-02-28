"""
Classes containing the Target config parameters for the high-level interface and
also the functions involving Models generation and assignment to datasets.
"""

from typing import List

import numpy as np
from astropy.coordinates import SkyCoord
from gammapy.maps import Map
from gammapy.modeling import Parameter, Parameters
from gammapy.modeling.models import (
    SPATIAL_MODEL_REGISTRY,
    SPECTRAL_MODEL_REGISTRY,
    DatasetModels,
    EBLAbsorptionNormSpectralModel,
    Models,
    SkyModel,
    SpectralModel,
    create_fermi_isotropic_diffuse_model,
)

from asgardpy.data.base import BaseConfig, PathType
from asgardpy.data.geom import SkyCoordConfig

__all__ = [
    "EBLAbsorptionModel",
    "SpectralModelConfig",
    "SpatialModelConfig",
    "Target",
    "ExpCutoffLogParabolaSpectralModel",
    "set_models",
    "config_to_dict",
    "read_models_from_asgardpy_config",
    "xml_spectral_model_to_gammapy_params",
    "xml_spatial_model_to_gammapy",
    "create_source_skymodel",
    "create_iso_diffuse_skymodel",
    "create_gal_diffuse_skymodel",
]


# Basic components to define the Target Config and any Models Config
class EBLAbsorptionModel(BaseConfig):
    filename: PathType = PathType(".")
    reference: str = "dominguez"
    type: str = "EBLAbsorptionNormSpectralModel"
    redshift: float = 0.4
    alpha_norm: float = 1.0


class ModelParams(BaseConfig):
    name: str = ""
    value: float = 1
    unit: str = " "
    error: float = 0.1
    min: float = 0.1
    max: float = 10
    frozen: bool = True


class SpectralModelConfig(BaseConfig):
    type: str = ""
    parameters: List[ModelParams] = [ModelParams()]
    ebl_abs: EBLAbsorptionModel = EBLAbsorptionModel()


class SpatialModelConfig(BaseConfig):
    type: str = ""
    parameters: List[ModelParams] = [ModelParams()]


class SkyModelComponent(BaseConfig):
    name: str = ""
    type: str = "SkyModel"
    spectral: SpectralModelConfig = SpectralModelConfig()
    spatial: SpatialModelConfig = SpatialModelConfig()


class Target(BaseConfig):
    source_name: str = ""
    sky_position: SkyCoordConfig = SkyCoordConfig()
    use_uniform_position: bool = True
    models_file: PathType = PathType(".")
    extended: bool = False
    components: List[SkyModelComponent] = [SkyModelComponent()]
    covariance: str = ""
    from_3d: bool = False


class ExpCutoffLogParabolaSpectralModel(SpectralModel):
    r"""Spectral Exponential Cutoff Log Parabola model.

    Using a simple template from Gammapy.

    Parameters
    ----------
    amplitude : `~astropy.units.Quantity`
        :math:`\phi_0`
    reference : `~astropy.units.Quantity`
        :math:`E_0`
    alpha_1 : `~astropy.units.Quantity`
        :math:`\alpha_1`
    beta : `~astropy.units.Quantity`
        :math:`\beta`
    lambda_ : `~astropy.units.Quantity`
        :math:`\lambda`
    alpha_2 : `~astropy.units.Quantity`
        :math:`\alpha_2`
    """
    tag = ["ExpCutoffLogParabolaSpectralModel", "ECLP"]

    amplitude = Parameter(
        "amplitude",
        "1e-12 cm-2 s-1 TeV-1",
        scale_method="scale10",
        interp="log",
        is_norm=True,
    )
    reference = Parameter("reference", "1 TeV", frozen=True)
    alpha_1 = Parameter("alpha_1", -2)
    alpha_2 = Parameter("alpha_2", 1, frozen=True)
    beta = Parameter("beta", 1)
    lambda_ = Parameter("lambda_", "0.1 TeV-1")

    @staticmethod
    def evaluate(energy, amplitude, reference, alpha_1, beta, lambda_, alpha_2):
        """Evaluate the model (static function)."""
        xx = energy / reference
        exponent = -alpha_1 - beta * np.log(xx)
        cutoff = np.exp(-np.power(energy * lambda_, alpha_2))

        return amplitude * np.power(xx, exponent) * cutoff


# Function for Models assignment
def set_models(
    config, datasets, datasets_name_list=None, models=None, target_source_name=None, extend=False
):
    """
    Set models on given Datasets.

    Parameters
    ----------
    config: `AsgardpyConfig` or others?
        AsgardpyConfig containing target information.
    datasets: `gammapy.datasets.Datasets`
        Datasets object
    dataset_name_list: List
        List of datasets_names to be used on the Models, before assigning them
        to the given datasets.
    models : `~gammapy.modeling.models.Models` or str
        Models object or YAML models string
    target_source_name: str
        Name of the Target source, to use to update only that Model's
        datasets_names, when a list of more than 1 models are provided.
    extend : bool
        Extend the existing models on the datasets or replace them with
        another model, maybe a Background Model. Not worked out currently.

    Returns
    -------
    datasets: `gammapy.datasets.Datasets`
        Datasets object with Models assigned.
    """
    # Have some checks on argument types
    if isinstance(models, DatasetModels) or isinstance(models, list):
        models = Models(models)
    elif isinstance(models, PathType):
        models = Models.read(models)
    elif len(config.components) > 0:
        spectral_model, spatial_model = read_models_from_asgardpy_config(config)
        models = Models(
            SkyModel(
                spectral_model=spectral_model,
                spatial_model=spatial_model,
                name=config.source_name,
            )
        )
    else:
        raise TypeError(f"Invalid type: {type(models)}")

    # if extend:
    # For extending a Background Model
    #    Models(models).extend(self.bkg_models)

    if datasets_name_list is None:
        datasets_name_list = datasets.names

    if target_source_name is None:
        target_source_name = config.source_name

    if len(models) > 1:
        models[target_source_name].datasets_names = datasets_name_list
    else:
        models.datasets_names = datasets_name_list

    datasets.models = models

    return datasets


# Functions for Models generation
def read_models_from_asgardpy_config(config):
    """
    Reading Models information from AsgardpyConfig and return Spectral and
    Spatial Models object to be combined later into SkyModels/Models object.

    Parameter
    ---------
    config: `AsgardpyConfig`
        Config section containing Target source information

    Returns
    -------
    spectral_model: `gammapy.modeling.models.SpectralModel`
        Spectral Model components of a gammapy SkyModel object.
    spatial_model: `gammapy.modeling.models.SpatialModel`
        Spatial Model components of a gammapy SkyModel object.
    """
    model_config = config.components[0]

    # Spectral Model
    if model_config.spectral.ebl_abs.reference != "":
        if model_config.spectral.type == "ExpCutoffLogParabolaSpectralModel":
            model1 = ExpCutoffLogParabolaSpectralModel().from_dict(
                {"spectral": config_to_dict(model_config.spectral)}
            )
        else:
            model1 = SPECTRAL_MODEL_REGISTRY.get_cls(model_config.spectral.type)().from_dict(
                {"spectral": config_to_dict(model_config.spectral)}
            )

        ebl_model = model_config.spectral.ebl_abs

        # First check for filename of a custom EBL model
        if ebl_model.filename.is_file():
            model2 = EBLAbsorptionNormSpectralModel.read(
                str(ebl_model.filename), redshift=ebl_model.redshift
            )
            # Update the reference name when using the custom EBL model for logging
            ebl_model.reference = ebl_model.filename.name[:-8].replace("-", "_")
        else:
            model2 = EBLAbsorptionNormSpectralModel.read_builtin(
                ebl_model.reference, redshift=ebl_model.redshift
            )
        if ebl_model.alpha_norm:
            model2.alpha_norm.value = ebl_model.alpha_norm
        spectral_model = model1 * model2
    else:
        if model_config.spectral.type == "ExpCutoffLogParabolaSpectralModel":
            spectral_model = ExpCutoffLogParabolaSpectralModel().from_dict(
                {"spectral": config_to_dict(model_config.spectral)}
            )
        else:
            spectral_model = SPECTRAL_MODEL_REGISTRY.get_cls(
                model_config.spectral.type
            )().from_dict({"spectral": config_to_dict(model_config.spectral)})
    spectral_model.name = config.source_name

    # Spatial model if provided
    if model_config.spatial.type != "":
        spatial_model = SPATIAL_MODEL_REGISTRY.get_cls(model_config.spatial.type)().from_dict(
            {"spatial": config_to_dict(model_config.spatial)}
        )
    else:
        spatial_model = None

    return spectral_model, spatial_model


def config_to_dict(model_config):
    """
    Convert the Spectral/Spatial models into dict.
    Probably an extra step and maybe removed later.

    Parameter
    ---------
    model_config: `AsgardpyConfig`
        Config section containg Target Model SkyModel components only.

    Returns
    -------
    model_dict: dict
        dictionary of the particular model.
    """
    model_dict = {}
    model_dict["type"] = str(model_config.type)
    model_dict["parameters"] = []

    for par in model_config.parameters:
        par_dict = {}
        par_dict["name"] = par.name
        par_dict["value"] = par.value
        par_dict["unit"] = par.unit
        par_dict["error"] = par.error
        par_dict["min"] = par.min
        par_dict["max"] = par.max
        par_dict["frozen"] = par.frozen
        model_dict["parameters"].append(par_dict)

    return model_dict


def xml_spectral_model_to_gammapy_params(params, spectrum_type, is_target=False, keep_sign=False):
    """
    Convert the Spectral Models information from XML model of FermiTools to Gammapy
    standards and return Parameters list.
    Details of the XML model can be seen at
    https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/source_models.html
    and with examples at
    https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/xml_model_defs.html

    Models from the XML model, not read are -
    ExpCutoff, BPLExpCutoff, PLSuperExpCutoff3, Gaussian, BandFunction

    Parameters
    ----------
    params: `gammapy.modeling.Parameters`
        List of gammapy Parameter object of a particular Model
    spectrum_type: str
        Spectrum type as defined in XML. To be used only for special cases like
        PLSuperExpCutoff, PLSuperExpCutoff2 and PLSuperExpCutoff4
    is_target: bool
        Boolean to check if the given list of Parameters belong to the target
        source model or not.
    keep_sign: bool
        Boolean to keep the same sign on the parameter values or not.

    Returns
    -------
    params_final: `gammapy.modeling.Parameters`
        Final list of gammapy Parameter object
    """
    new_params = []

    for par in params:
        new_par = {}

        for key_ in par.keys():
            # Getting the "@par_name" for each parameter without the "@"
            if key_ != "@free":
                new_par[key_[1:].lower()] = par[key_]
            else:
                if par["@name"].lower() not in ["scale", "eb"]:
                    new_par["frozen"] = (par[key_] == "0") and not is_target
                else:
                    # Never change frozen status of Reference Energy
                    new_par["frozen"] = par[key_] == "0"
            new_par["unit"] = ""
            new_par["is_norm"] = False

            # Using the nomenclature as used in Gammapy
            # Making scale = 1, by multiplying it to the value, min and max
            if par["@name"].lower() in ["norm", "prefactor", "integral"]:
                new_par["name"] = "amplitude"
                new_par["unit"] = "cm-2 s-1 TeV-1"
                new_par["is_norm"] = True

            if par["@name"].lower() in ["scale", "eb"]:
                new_par["name"] = "reference"

            if par["@name"].lower() in ["breakvalue"]:
                new_par["name"] = "ebreak"

            if par["@name"].lower() in ["lowerlimit"]:
                new_par["name"] = "emin"

            if par["@name"].lower() in ["upperlimit"]:
                new_par["name"] = "emax"

            if par["@name"].lower() in ["cutoff", "expfactor"]:
                new_par["name"] = "lambda_"
                new_par["unit"] = "TeV-1"

            if par["@name"].lower() in ["index"]:
                new_par["name"] = "index"

            if par["@name"].lower() in ["index1"]:
                if spectrum_type in ["PLSuperExpCutoff", "PLSuperExpCutoff2"]:
                    new_par["name"] = "index"
                else:
                    new_par["name"] = "index1"  # For spectrum_type == "BrokenPowerLaw"

            if par["@name"].lower() in ["indexs"]:
                new_par["name"] = "index_1"  # For spectrum_type == "PLSuperExpCutoff4"

            if par["@name"].lower() in ["index2"]:
                if spectrum_type == "PLSuperExpCutoff4":
                    new_par["name"] = "index_2"
                elif spectrum_type in ["PLSuperExpCutoff", "PLSuperExpCutoff2"]:
                    new_par["name"] = "alpha"
                else:
                    new_par["name"] = "index2"  # For spectrum_type == "BrokenPowerLaw"

            if par["@name"].lower() in ["expfactors"]:
                new_par["name"] = "expfactor"

        # Some modifications on scaling/sign:
        if new_par["name"] in ["reference", "ebreak", "emin", "emax"]:
            new_par["unit"] = "TeV"
            new_par["value"] = float(new_par["value"]) * float(new_par["scale"]) * 1.0e-6
            if "error" in new_par:
                new_par["error"] = float(new_par["error"]) * float(new_par["scale"]) * 1.0e-6
            new_par["min"] = float(new_par["min"]) * float(new_par["scale"]) * 1.0e-6
            new_par["max"] = float(new_par["max"]) * float(new_par["scale"]) * 1.0e-6

        if new_par["name"] in ["amplitude"]:
            new_par["value"] = float(new_par["value"]) * float(new_par["scale"]) * 1.0e6
            if "error" in new_par:
                new_par["error"] = float(new_par["error"]) * float(new_par["scale"]) * 1.0e6
            new_par["min"] = float(new_par["min"]) * float(new_par["scale"]) * 1.0e6
            new_par["max"] = float(new_par["max"]) * float(new_par["scale"]) * 1.0e6

        if new_par["name"] in ["index", "index_1", "index_2", "beta"] and not keep_sign:
            # Other than EBL Attenuated Power Law?
            # spectral indices in gammapy are always taken as positive values.
            val_ = float(new_par["value"]) * float(new_par["scale"])
            if val_ < 0:
                new_par["value"] = -1 * val_

                # Reverse the limits while changing the sign
                min_ = -1 * float(new_par["min"]) * float(new_par["scale"])
                max_ = -1 * float(new_par["max"]) * float(new_par["scale"])
                new_par["min"] = min(min_, max_)
                new_par["max"] = max(min_, max_)

        if new_par["name"] in ["lambda_"]:
            if spectrum_type == "PLSuperExpCutoff":
                # Original parameter is inverse of what gammapy uses
                val_ = float(new_par["value"]) * float(new_par["scale"])
                new_par["value"] = 1.0e6 / val_
                if "error" in new_par:
                    new_par["error"] = 1.0e6 * float(new_par["error"]) / (val_**2)
                min_ = 1.0e6 / (float(new_par["min"]) * float(new_par["scale"]))
                max_ = 1.0e6 / (float(new_par["max"]) * float(new_par["scale"]))
                new_par["min"] = min(min_, max_)
                new_par["max"] = max(min_, max_)

            if spectrum_type == "PLSuperExpCutoff2":
                val_ = float(new_par["value"]) * float(new_par["scale"]) * 1.0e6
                new_par["value"] = val_
                if "error" in new_par:
                    new_par["error"] = float(new_par["error"]) * float(new_par["scale"]) * 1.0e6
                min_ = float(new_par["min"]) * float(new_par["scale"]) * 1.0e6
                max_ = float(new_par["max"]) * float(new_par["scale"]) * 1.0e6
                new_par["min"] = min_
                new_par["max"] = max_

        if new_par["name"] == "alpha" and spectrum_type in [
            "PLSuperExpCutoff",
            "PLSuperExpCutoff2",
        ]:
            new_par["frozen"] = par["@free"] == "0"

        # Read into Gammapy Parameter object
        new_param = Parameter(name=new_par["name"], value=new_par["value"])
        if "error" in new_par:
            new_param.error = new_par["error"]
        new_param.min = new_par["min"]
        new_param.max = new_par["max"]
        new_param.unit = new_par["unit"]
        new_param.frozen = new_par["frozen"]
        new_param._is_norm = new_par["is_norm"]

        new_params.append(new_param)

    params_final2 = Parameters(new_params)

    return params_final2


def xml_spatial_model_to_gammapy(aux_path, xml_spatial_model):
    """
    Read the spatial model component of the XMl model to Gammapy SpatialModel
    object.

    Details of the XML model can be seen at
    https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/source_models.html
    and with examples at
    https://fermi.gsfc.nasa.gov/ssc/data/analysis/scitools/xml_model_defs.html

    Paramaters
    ----------
    aux_path: `Path`
        Path to the template diffuse models
    xml_spatial_model: `dict`
        Spatial Model component of a particular source from the XML file

    Returns
    -------
    spatial_model: `gammapy.modeling.models.SpatialModel`
        Gammapy Spatial Model object
    """
    spatial_pars = xml_spatial_model["parameter"]

    if xml_spatial_model["@type"] == "SkyDirFunction":
        for par_ in spatial_pars:
            if par_["@name"] == "RA":
                lon_0 = f"{par_['@value']} deg"
            if par_["@name"] == "DEC":
                lat_0 = f"{par_['@value']} deg"
        fk5_frame = SkyCoord(
            lon_0,
            lat_0,
            frame="fk5",
        )
        gal_frame = fk5_frame.transform_to("galactic")
        spatial_model = SPATIAL_MODEL_REGISTRY.get_cls("PointSpatialModel")().from_position(
            gal_frame
        )

    elif xml_spatial_model["@type"] == "SpatialMap":
        file_name = xml_spatial_model["@file"].split("/")[-1]
        file_path = aux_path / f"Templates/{file_name}"

        spatial_map = Map.read(file_path)
        spatial_map = spatial_map.copy(unit="sr^-1")

        spatial_model = SPATIAL_MODEL_REGISTRY.get_cls("TemplateSpatialModel")(
            spatial_map, filename=file_path
        )

    elif xml_spatial_model["@type"] == "RadialGaussian":
        for par_ in spatial_pars:
            if par_["@name"] == "RA":
                lon_0 = f"{par_['@value']} deg"
            if par_["@name"] == "DEC":
                lat_0 = f"{par_['@value']} deg"
            if par_["@name"] == "Sigma":
                sigma = f"{par_['@value']} deg"

        spatial_model = SPATIAL_MODEL_REGISTRY.get_cls("GaussianSpatialModel")(
            lon_0=lon_0, lat_0=lat_0, sigma=sigma, frame="fk5"
        )

    return spatial_model


def create_source_skymodel(config_target, source, aux_path):
    """
    Build SkyModels from a given AsgardpyConfig section of the target
    source information, list of LAT files and other relevant information.

    Parameters
    ----------
    config_target: `AsgardpyConfig`
        Config section containing the Target source information.
    source: dict
        Dictionary containing the source models infromation from XML file.
    aux_path: str
        Path location of the LAT auxillary files.

    Returns
    -------
    source_sky_model: `gammapy.modeling.SkyModel`
        SkyModels object for the given source information.
    is_source_target: bool
        Boolean to check if the Models belong to the target source.
    """
    source_name = source["@name"]
    spectrum_type = source["spectrum"]["@type"].split("EblAtten::")[-1]
    spectrum = source["spectrum"]["parameter"]

    source_name_check = source_name.replace("_", "").replace(" ", "")
    target_check = config_target.source_name.replace("_", "").replace(" ", "")

    # initialized to check for the case if target spectral model information
    # is to be taken from the Config
    spectral_model = None

    # Check if target_source file exists
    is_source_target = False
    ebl_atten_pl = False

    # If Target source model's spectral component is to be taken from Config
    # and not from 3D dataset.
    if source_name_check == target_check:
        source_name = config_target.source_name
        is_source_target = True

        # Only taking the spectral model information right now.
        if not config_target.from_3d:
            spectral_model, _ = read_models_from_asgardpy_config(config_target)

    if spectral_model is None:
        # Define the Spectral Model type for Gammapy
        for spec in spectrum:
            if spec["@name"] not in ["GalDiffModel", "IsoDiffModel"]:
                if spectrum_type in ["PLSuperExpCutoff", "PLSuperExpCutoff2"]:
                    spectrum_type_final = "ExpCutoffPowerLawSpectralModel"
                elif spectrum_type == "PLSuperExpCutoff4":
                    spectrum_type_final = "SuperExpCutoffPowerLaw4FGLDR3SpectralModel"
                else:
                    spectrum_type_final = f"{spectrum_type}SpectralModel"

                spectral_model = SPECTRAL_MODEL_REGISTRY.get_cls(spectrum_type_final)()

                if spectrum_type == "LogParabola":
                    if "EblAtten" in source["spectrum"]["@type"]:
                        spectral_model = SPECTRAL_MODEL_REGISTRY.get_cls("PowerLawSpectralModel")()
                        ebl_atten_pl = True
                    else:
                        spectral_model = SPECTRAL_MODEL_REGISTRY.get_cls(
                            "LogParabolaSpectralModel"
                        )()

        # Read the parameter values from XML file to create SpectralModel
        params_list = xml_spectral_model_to_gammapy_params(
            spectrum,
            spectrum_type,
            is_target=is_source_target,
            keep_sign=ebl_atten_pl,
        )

        for param_ in params_list:
            setattr(spectral_model, param_.name, param_)
        config_spectral = config_target.components[0].spectral
        ebl_absorption_included = config_spectral.ebl_abs is not None

        if is_source_target and ebl_absorption_included:
            ebl_model = config_spectral.ebl_abs

            if ebl_model.filename.is_file():
                ebl_spectral_model = EBLAbsorptionNormSpectralModel.read(
                    str(ebl_model.filename), redshift=ebl_model.redshift
                )
                ebl_model.reference = ebl_model.filename.name[:-8].replace("-", "_")
            else:
                ebl_spectral_model = EBLAbsorptionNormSpectralModel.read_builtin(
                    ebl_model.reference, redshift=ebl_model.redshift
                )
            spectral_model = spectral_model * ebl_spectral_model

    # Reading Spatial model from the XML file
    spatial_model = xml_spatial_model_to_gammapy(aux_path, source["spatialModel"])

    spatial_model.freeze()
    source_sky_model = SkyModel(
        spectral_model=spectral_model,
        spatial_model=spatial_model,
        name=source_name,
    )

    return source_sky_model, is_source_target


def create_iso_diffuse_skymodel(iso_file, key):
    """
    Create a SkyModel of the Fermi Isotropic Diffuse Model and assigning
    name as per the observation key.
    """
    diff_iso = create_fermi_isotropic_diffuse_model(
        filename=iso_file, interp_kwargs={"fill_value": None}
    )
    diff_iso._name = f"{diff_iso.name}-{key}"

    # Parameters' limits
    diff_iso.spectral_model.model1.parameters[0].min = 0.001
    diff_iso.spectral_model.model1.parameters[0].max = 10
    diff_iso.spectral_model.model2.parameters[0].min = 0
    diff_iso.spectral_model.model2.parameters[0].max = 10

    return diff_iso


def create_gal_diffuse_skymodel(diff_gal):
    """
    Create SkyModel of the Diffuse Galactic sources.
    """
    template_diffuse = SPATIAL_MODEL_REGISTRY.get_cls("TemplateSpatialModel")(
        diff_gal, normalize=False
    )
    source = SkyModel(
        spectral_model=SPECTRAL_MODEL_REGISTRY.get_cls("PowerLawNormSpectralModel")(),
        spatial_model=template_diffuse,
        name="diffuse-iem",
    )
    source.parameters["norm"].min = 0
    source.parameters["norm"].max = 10
    source.parameters["norm"].frozen = False

    return source
