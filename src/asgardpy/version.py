"""
Asgardpy version
"""
MAJOR = "0"
MINOR = "4"
# On main and in a nightly release the patch should be one ahead of the last
# released build.
PATCH = "1"
# This is mainly for nightly builds which have the suffix ".dev$DATE". See
# https://semver.org/#is-v123-a-semantic-version for the semantics.
SUFFIX = ""

VERSION_SHORT = f"{MAJOR}.{MINOR}"
VERSION = f"{MAJOR}.{MINOR}.{PATCH}{SUFFIX}"


"""
try:
    from .version import VERSION
except Exception:
    import warnings
    warnings.warn(
        "Could not determine version; this indicates a broken installation."
        " Install from PyPI or from a local git repository."
        " Installing github's autogenerated source release tarballs "
        " does not include version information and should be avoided."
    )
    del warnings
    version = "0.0.0"
"""

__version__ = VERSION
