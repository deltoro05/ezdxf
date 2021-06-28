# Copyright (c) 2011-2021, Manfred Moitzi
# License: MIT License
from typing import TextIO, List, Union, Tuple
import os
import sys
from pathlib import Path
from configparser import ConfigParser

# The MATPLOTLIB global shows that Matplotlib is installed:
try:
    import matplotlib

    MATPLOTLIB = True
except ImportError:
    MATPLOTLIB = False

TRUE_STATE = {"True", "true", "On", "on", "1"}
CORE = "core"
BROWSE_COMMAND = "browse-command"
VIEW_COMMAND = "view-command"
DRAW_COMMAND = "draw-command"
INI_NAME = "ezdxf.ini"
DEFAULT_FILES = [
    Path(f"~/.ezdxf/{INI_NAME}").expanduser(),
    Path(f"./{INI_NAME}"),
]


def default_config() -> ConfigParser:
    config = ConfigParser()
    config[CORE] = {
        "TEST_FILES": "",
        "FONT_CACHE_DIRECTORY": "",
        "AUTO_LOAD_FONTS": "true",
        "LOAD_PROXY_GRAPHICS": "true",
        "STORE_PROXY_GRAPHICS": "true",
        "LOG_UNPROCESSED_TAGS": "true",
        "FILTER_INVALID_XDATA_GROUP_CODES": "true",
        "WRITE_FIXED_META_DATA_FOR_TESTING": "false",
        "DEFAULT_TEXT_STYLE": "OpenSans",
        "DEFAULT_DIMENSION_TEXT_STYLE": "OpenSansCondensed-Light",
    }
    config[BROWSE_COMMAND] = {
        "TEXT_EDITOR": r"C:\Program Files\Notepad++\notepad++.exe",
        "GOTO_LINE_ARGUMENT": "-n{num}",  # .format(num=line_number)
    }
    return config


def config_files() -> List[Path]:
    # loading order
    # 1. user home directory "~/.ezdxf/ezdxf.ini" (lowest priority)
    # 2. current working directory "./ezdxf.ini"
    # 3. config file specified by EZDXF_CONFIG_FILE (highest priority)

    paths = list(DEFAULT_FILES)
    env_cfg = os.getenv("EZDXF_CONFIG_FILE", "")
    if env_cfg:
        paths.append(Path(env_cfg))
    return paths


def load_config_files(paths: List[Path]) -> ConfigParser:
    config = default_config()
    config.read(paths, encoding="utf8")

    # environment variables override config files
    for name, env_name in [("TEST_FILES", "EZDXF_TEST_FILES")]:
        value = os.environ.get(env_name, "")
        if value:
            config[CORE][name] = value
    return config


def boolstr(value: bool) -> str:
    return str(value).lower()


class Options:
    CORE = CORE
    BROWSE_COMMAND = BROWSE_COMMAND
    VIEW_COMMAND = VIEW_COMMAND
    DRAW_COMMAND = DRAW_COMMAND

    CONFIG_VARS = [
        "EZDXF_DISABLE_C_EXT",
        "EZDXF_TEST_FILES",
        "EZDXF_CONFIG_FILE",
    ]

    def __init__(self):
        paths = config_files()
        self._loaded_paths = [p for p in paths if p.exists()]
        self._config = load_config_files(paths)
        # needs fast access:
        self.log_unprocessed_tags = True
        # Activate/deactivate Matplotlib support (e.g. for testing)
        self._use_matplotlib = MATPLOTLIB
        self.update_cached_options()

    def set(self, section: str, key: str, value: str) -> None:
        self._config.set(section, key, value)

    def get(self, section: str, key: str, default: str = "") -> str:
        return self._config.get(section, key, fallback=default)

    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        return self._config.getboolean(section, key, fallback=default)

    def update_cached_options(self) -> None:
        self.log_unprocessed_tags = self.get_bool(
            Options.CORE, "LOG_UNPROCESSED_TAGS", default=True
        )

    def rewrite_cached_options(self):
        # rewrite cached options
        self._config.set(
            Options.CORE,
            "LOG_UNPROCESSED_TAGS",
            boolstr(self.log_unprocessed_tags),
        )

    @property
    def loaded_config_files(self) -> Tuple[Path]:
        return tuple(self._loaded_paths)

    def read_file(self, filename: str) -> None:
        """Append content from config file `filename`, but does not reset the
        configuration.
        """
        try:
            self._config.read(filename)
        except IOError as e:
            print(str(e))
        else:
            self._loaded_paths.append(Path(filename))
            self.update_cached_options()

    def write(self, fp: TextIO) -> None:
        """Write current configuration into given file object, the file object
        must be a writeable text file with 'utf8' encoding.
        """
        self.rewrite_cached_options()
        try:
            self._config.write(fp)
        except IOError as e:
            print(str(e))

    def write_file(self, filename: str = INI_NAME) -> None:
        """Write current configuration into file `filename`."""
        with open(os.path.expanduser(filename), "wt", encoding="utf8") as fp:
            self.write(fp)

    @property
    def filter_invalid_xdata_group_codes(self) -> bool:
        return self.get_bool(
            CORE, "FILTER_INVALID_XDATA_GROUP_CODES", default=True
        )

    @property
    def default_text_style(self) -> str:
        return self.get(CORE, "DEFAULT_TEXT_STYLE", default="OpenSans")

    @property
    def default_dimension_text_style(self) -> str:
        # Set path to an external font cache directory: e.g. "~/ezdxf", see
        # docs for ezdxf.options for an example how to create your own
        # external font cache:
        return self.get(
            CORE,
            "DEFAULT_DIMENSION_TEXT_STYLE",
            default="OpenSansCondensed-Light",
        )

    @property
    def font_cache_directory(self) -> str:
        return os.path.expanduser(self.get(CORE, "FONT_CACHE_DIRECTORY"))

    @font_cache_directory.setter
    def font_cache_directory(self, dirname: Union[str, Path]) -> None:
        p = Path(dirname).expanduser()
        if p.exists():
            absolute = p.absolute()
            if p.is_dir():
                self.set(CORE, "FONT_CACHE_DIRECTORY", str(absolute))
            else:
                raise ValueError(f'"{absolute}" is not a directory')
        else:
            raise ValueError(f'directory "{dirname}" does not exist')

    @property
    def test_files(self) -> str:
        return os.path.expanduser(self.get(CORE, "TEST_FILES"))

    @property
    def test_files_path(self) -> Path:
        return Path(self.test_files)

    @property
    def load_proxy_graphics(self) -> bool:
        return self.get_bool(CORE, "LOAD_PROXY_GRAPHICS", default=True)

    @property
    def store_proxy_graphics(self) -> bool:
        return self.get_bool(CORE, "STORE_PROXY_GRAPHICS", default=True)

    @property
    def write_fixed_meta_data_for_testing(self) -> bool:
        # Enable this option to always create same meta data for testing
        # scenarios, e.g. to use a diff like tool to compare DXF documents.
        return self.get_bool(
            CORE, "WRITE_FIXED_META_DATA_FOR_TESTING", default=False
        )

    @write_fixed_meta_data_for_testing.setter
    def write_fixed_meta_data_for_testing(self, state: bool) -> None:
        self.set(CORE, "write_fixed_meta_data_for_testing", boolstr(state))

    @property
    def auto_load_fonts(self) -> bool:
        # Set "AUTO_LOAD_FONTS = false" to deactivate auto font loading,
        # if this this procedure slows down your startup time and font measuring is not
        # important to you. Fonts can always loaded manually: ezdxf.fonts.load()
        return self.get_bool(CORE, "AUTO_LOAD_FONTS", default=True)

    @property
    def use_matplotlib(self) -> bool:
        """Activate/deactivate Matplotlib support e.g. for testing"""
        return self._use_matplotlib

    @use_matplotlib.setter
    def use_matplotlib(self, state: bool) -> None:
        if MATPLOTLIB:
            self._use_matplotlib = state
        else:  # Matplotlib is not installed
            self._use_matplotlib = False

    def preserve_proxy_graphics(self, state: bool = True) -> None:
        """Enable/disable proxy graphic load/store support."""
        value = "true" if state else "false"
        self.set(CORE, "LOAD_PROXY_GRAPHICS", value)
        self.set(CORE, "STORE_PROXY_GRAPHICS", value)

    def print(self):
        """Print current configuration to `stdout`."""
        self._config.write(sys.stdout)

    def write_home_config(self):
        """Write current configuration into file "~/.ezdxf/ezdxf.ini"."""
        p = Path("~/.ezdxf").expanduser()
        if not p.exists():
            try:
                p.mkdir()
            except IOError as e:
                print(str(e))
                return
        try:
            with open(p / "ezdxf.ini", "wt", encoding="utf8") as fp:
                self.write(fp)
        except IOError as e:
            print(str(e))
        else:
            print(f"created config file: '{fp.name}'")

    def reset(self):
        self._loaded_paths = []
        self._config = default_config()
        self.update_cached_options()
        delete_config_files()


def delete_config_files():
    for file in DEFAULT_FILES:
        if file.exists():
            try:
                file.unlink()
                print(f"deleted config file: '{file}'")
            except IOError as e:
                print(str(e))


# Global Options
options = Options()
