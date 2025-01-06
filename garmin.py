# ruff: noqa: E402
"""
Takes a .fit file produced by TrainingPeaks Virtual and modifies the fields so that Garmin
will think it came from a Garmin device and use it to determine training effect.

Simulates an Edge 830 device
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional, cast

import questionary
import semver
from rich.console import Console
from rich.logging import RichHandler
from rich.traceback import install
from watchdog.events import PatternMatchingEventHandler
from watchdog.observers.polling import PollingObserver as Observer

_logger = logging.getLogger("garmin")
install()

# fit_tool configures logging for itself, so need to do this before importing it
logging.basicConfig(
    level=logging.NOTSET,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(markup=True)],
)
logging.basicConfig()
_logger.setLevel(logging.INFO)
logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
logging.getLogger("oauth1_auth").setLevel(logging.WARNING)

from fit_tool.fit_file import FitFile
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.profile_type import GarminProduct, Manufacturer

c = Console()

EDGE830 = GarminProduct.EDGE_830
GARMIN = Manufacturer.GARMIN
FILES_UPLOADED_NAME = Path(".uploaded_files.json")


@dataclass
class Config:
    garmin_username: str | None = None
    garmin_password: str | None = None
    fitfiles_path: Path | None = None


# set up config file and in-memory config store
_config_file = Path(__file__).parent / ".config.json"
_config_file.touch(exist_ok=True)
_config_keys = ["garmin_username", "garmin_password", "fitfiles_path"]
with _config_file.open("r") as f:
    if _config_file.stat().st_size == 0:
        _config = Config()
    else:
        _config = Config(**json.load(f))


class FitFileLogFilter(logging.Filter):
    """Filter to remove specific warning from the fit_tool module"""

    def filter(self, record):
        res = "\n\tactual: " not in record.getMessage()
        return res


logging.getLogger("fit_tool").addFilter(FitFileLogFilter())


class NewFileEventHandler(PatternMatchingEventHandler):
    def __init__(self, dryrun: bool = False):
        _logger.debug(f"Creating NewFileEventHandler with {dryrun=}")
        super().__init__(patterns=["*.fit"], ignore_directories=True, case_sensitive=False)
        self.dryrun = dryrun

    def on_created(self, event) -> None:
        _logger.info(f"New file detected - \"{event.src_path}\"; sleeping for 5 seconds "
                      "to ensure TPV finishes writing file")
        if not self.dryrun:
            # Wait for a short time to make sure TPV has finished writing to the file
            time.sleep(5)
            # Run the upload all function
            p = event.src_path
            if isinstance(p, bytes):
                p = p.decode()
            p = cast(str, p)
            upload_all(Path(p).parent.absolute())
        else:
            _logger.warning("Found new file, but not processing because dryrun was requested")


def print_message(prefix, message):
    man = (
        Manufacturer(message.manufacturer).name
        if message.manufacturer in Manufacturer
        else "BLANK"
    )
    gar_prod = (
        GarminProduct(message.garmin_product)
        if message.garmin_product in GarminProduct
        else "BLANK"
    )
    _logger.debug(
        f'{prefix} - manufacturer: {message.manufacturer} ("{man}") - '
        f'product: {message.product} - garmin product: {message.garmin_product} ("{gar_prod}")'
    )


def get_fitfiles_path(existing_path: Path | None) -> Path:
    """
    Will attempt to auto-find the FITFiles folder inside a TPVirtual data directory.

    On OSX/Windows, TPVirtual data directory will be auto-detected. This folder can
    be overridden using the ``TPV_DATA_PATH`` environment variable.
    """
    _logger.info("Getting FITFiles folder")

    TPVPath = get_tpv_folder(existing_path)
    res = [f for f in os.listdir(TPVPath) if re.search(r"\A(\w){16}\Z", f)]
    if len(res) == 0:
        _logger.error(
            'Cannot find a TP Virtual User folder in "%s", please check if you have previously logged into TP Virtual',
            TPVPath,
        )
        sys.exit(1)
    elif len(res) == 1:
        title = f'Found TP Virtual User directory at "{Path(TPVPath) / res[0]}", is this correct? '
        option = questionary.select(title, choices=["yes", "no"]).ask()
        if option == "no":
            _logger.error(
                'Failed to find correct TP Virtual User folder please manually configure "fitfiles_path" in config file: %s',
                _config_file.absolute(),
            )
            sys.exit(1)
        else:
            option = res[0]
    else:
        title = "Found multiple TP Virtual User directories, please select the directory for your user: "
        option = questionary.select(title, choices=res).ask()
    TPV_data_path = Path(TPVPath) / option
    _logger.info(
        f'Found TP Virtual User directory: "{str(TPV_data_path.absolute())}", '
        'setting "fitfiles_path" in config file'
    )
    return TPV_data_path / "FITFiles"


def get_tpv_folder(default_path: Path | None) -> Path:
    if os.environ.get("TPV_DATA_PATH", None):
        p = str(os.environ.get("TPV_DATA_PATH"))
        _logger.info(f'Using TPV_DATA_PATH value read from the environment: "{p}"')
        return Path(p)
    if sys.platform == "darwin":
        TPVPath = os.path.expanduser("~/TPVirtual")
    elif sys.platform == "win32":
        TPVPath = os.path.expanduser("~/Documents/TPVirtual")
    else:
        _logger.warning(
            "TrainingPeaks Virtual user folder can only be automatically detected on Windows and OSX"
        )
        TPVPath = questionary.path(
            'Please enter your TrainingPeaks Virtual data folder (by default, ends with "TPVirtual"): ',
            default=str(default_path) if default_path else "",
        ).ask()
    return Path(TPVPath)


def get_date_from_fit(fit_path: Path) -> Optional[datetime]:
    fit_file = FitFile.from_file(str(fit_path))
    res = None
    for i, record in enumerate(fit_file.records):
        message = record.message
        if message.global_id == FileIdMessage.ID:
            if isinstance(message, FileIdMessage):
                res = datetime.fromtimestamp(message.time_created / 1000.0)  # type: ignore
                break
    return res


def edit_fit(
    fit_path: Path, output: Optional[Path] = None, dryrun: bool = False
) -> Path | None:
    if dryrun:
        _logger.warning('In "dryrun" mode; will not actually write new file.')
    _logger.info(f'Processing "{fit_path}"')
    try:
        fit_file = FitFile.from_file(str(fit_path))
    except Exception:
        _logger.error("File does not appear to be a FIT file, skipping...")
        # c.print_exception(show_locals=True)
        return None
        
    if not output:
        output = fit_path.parent / f"{fit_path.stem}_modified.fit"

    builder = FitFileBuilder(auto_define=True)
    dt = None
    # loop through records, find the one we need to change, and modify the values:
    for i, record in enumerate(fit_file.records):
        message = record.message

        # change file id to indicate file was saved by Edge 830
        if message.global_id == FileIdMessage.ID:
            if isinstance(message, FileIdMessage):
                dt = datetime.fromtimestamp(message.time_created / 1000.0)  # type: ignore
                _logger.info(f'Activity timestamp is "{dt.isoformat()}"')
                print_message(f"Record: {i}", message)
                if message.manufacturer == Manufacturer.DEVELOPMENT.value:
                    _logger.debug("    Modifying values")
                    message.product = GarminProduct.EDGE_830.value
                    message.manufacturer = Manufacturer.GARMIN.value
                    print_message(f"    New Record: {i}", message)

        # change device info messages
        if message.global_id == DeviceInfoMessage.ID:
            if isinstance(message, DeviceInfoMessage):
                print_message(f"Record: {i}", message)
                if (
                    message.manufacturer == Manufacturer.DEVELOPMENT.value
                    or message.manufacturer == 0
                    or message.manufacturer == Manufacturer.WAHOO_FITNESS.value
                ):
                    _logger.debug("    Modifying values")
                    message.garmin_product = GarminProduct.EDGE_830.value
                    message.product = GarminProduct.EDGE_830.value  # type: ignore
                    message.manufacturer = Manufacturer.GARMIN.value
                    print_message(f"    New Record: {i}", message)

        builder.add(message)

    modified_file = builder.build()
    if not dryrun:
        _logger.info(f'Saving modified data to "{output}"')
        modified_file.to_file(str(output))
    else:
        _logger.info(
            f"Dryrun requested, so not saving data "
            f'(would have written to "{output}")'
        )
    return output


def upload(fn: Path, original_path: Optional[Path] = None, dryrun: bool = False):
    # get credentials and login if needed
    import garth
    from garth.exc import GarthException, GarthHTTPError

    garth_dir = Path(__file__).parent / ".garth"
    garth_dir.mkdir(exist_ok=True)

    try:
        garth.resume(str(garth_dir.absolute()))
        garth.client.username
        _logger.debug(f'Using stored Garmin credentials from "{garth_dir}" directory')
    except (GarthException, FileNotFoundError):
        # Session is expired. You'll need to log in again
        _logger.info("Authenticating to Garmin Connect")
        email = _config.garmin_username
        password = _config.garmin_password
        if not email:
            email = questionary.text(
                'No "garmin_username" variable set; Enter email address: '
            ).ask()
        _logger.debug(f'Using username "{email}"')
        if not password:
            password = questionary.password(
                'No "garmin_password" variable set; Enter password: '
            ).ask()
            _logger.debug("Using password from user input")
        else:
            _logger.debug('Using password stored in "garmin_password"')
        garth.login(email, password)
        garth.save(str(garth_dir.absolute()))

    with fn.open("rb") as f:
        try:
            if not dryrun:
                _logger.info(f'Uploading "{fn}" using garth')
                garth.client.upload(f)
                _logger.info(
                    f':white_check_mark: Successfully uploaded "{str(original_path)}"'
                )
            else:
                _logger.info(f'Skipping upload of "{fn}" because dryrun was requested')
        except GarthHTTPError as e:
            if e.error.response.status_code == 409:
                _logger.warning(
                    f':x: Received HTTP conflict (activity already exists) for "{str(original_path)}"'
                )
            else:
                raise e


def upload_all(dir: Path, preinitialize: bool = False, dryrun: bool = False):
    files_uploaded = dir.joinpath(FILES_UPLOADED_NAME)
    if files_uploaded.exists():
        # load uploaded file list from disk
        with files_uploaded.open("r") as f:
            uploaded_files = json.load(f)
    else:
        uploaded_files = []
        with files_uploaded.open("w") as f:
            # write blank file
            json.dump(uploaded_files, f, indent=2)
    _logger.debug(f"Found the following already uploaded files: {uploaded_files}")

    # glob all .fit files in the current directory
    files = [str(i) for i in dir.glob("*.fit", case_sensitive=False)]
    # strip any leading/trailing slashes from filenames
    files = [i.replace(str(dir), "").strip("/").strip("\\") for i in files]
    # remove files matching what we may have already processed
    files = [i for i in files if not i.endswith("_modified.fit")]
    # remove files found in the "already uploaded" list
    files = [i for i in files if i not in uploaded_files]

    _logger.info(f"Found {len(files)} files to edit/upload")
    _logger.debug(f"Files to upload: {files}")

    if not files:
        return

    for f in files:
        _logger.info(f'Processing "{f}"')  # type: ignore

        if not preinitialize:
            with NamedTemporaryFile(delete=True, delete_on_close=False) as fp:
                output = edit_fit(dir.joinpath(f), output=Path(fp.name))
                if output:
                    _logger.info("Uploading modified file to Garmin Connect")
                    upload(output, original_path=Path(f), dryrun=dryrun)
                    _logger.debug(f'Adding "{f}" to "uploaded_files"')
        else:
            _logger.info(
                "Preinitialize was requested, so just marking as uploaded (not actually processing)"
            )
        uploaded_files.append(f)

    if not dryrun:
        with files_uploaded.open("w") as f:
            json.dump(uploaded_files, f, indent=2)


def monitor(watch_dir: Path, dryrun: bool = False):
    event_handler = NewFileEventHandler(dryrun=dryrun)
    observer = Observer()
    observer.schedule(event_handler, str(watch_dir.absolute()), recursive=True)
    observer.start()
    if dryrun:
        _logger.warning("Dryrun was requested, so will not actually take any actions")
    _logger.info(f"Monitoring directory: \"{watch_dir.absolute()}\"")
    try:
        while observer.is_alive():
            observer.join(1)
    except KeyboardInterrupt:
        _logger.info("Received keyboard interrupt, shutting down monitor")
    finally:
        observer.stop()
        observer.join()


def config_is_valid(excluded_keys=[]) -> bool:
    missing_vals = []
    for k in _config_keys:
        if (
            not hasattr(_config, k) or getattr(_config, k) is None
        ) and k not in excluded_keys:
            missing_vals.append(k)
    if missing_vals:
        _logger.error(f"The following configuration values are missing: {missing_vals}")
        return False
    return True


def build_config_file(
    overwrite_existing_vals: bool = False,
    rewrite_config: bool = True,
    excluded_keys: list[str] = [],
):
    for k in _config_keys:
        if (
            getattr(_config, k) is None or overwrite_existing_vals
        ) and k not in excluded_keys:
            valid_input = False
            while not valid_input:
                try:
                    if not hasattr(_config, k) or getattr(_config, k) is None:
                        _logger.warning(f'Required value "{k}" not found in config')
                    msg = f'Enter value to use for "{k}"'

                    if hasattr(_config, k) and getattr(_config, k):
                        msg += f'\nor press enter to use existing value of "{getattr(_config, k)}"'
                        if k == "garmin_password":
                            msg = msg.replace(getattr(_config, k), "<**hidden**>")

                    if k != "fitfiles_path":
                        if "password" in k:
                            val = questionary.password(msg).unsafe_ask()
                        else:
                            val = questionary.text(msg).unsafe_ask()
                    else:
                        val = str(get_fitfiles_path(
                            Path(_config.fitfiles_path).parent.parent if _config.fitfiles_path else None
                        ))
                    if val:
                        valid_input = True
                        setattr(_config, k, val)
                    elif hasattr(_config, k) and getattr(_config, k):
                        valid_input = True
                        val = getattr(_config, k)
                    else:
                        _logger.warning(
                            "Entered input was not valid, please try again (or press Ctrl-C to cancel)"
                        )
                except KeyboardInterrupt:
                    _logger.error("User canceled input; exiting!")
                    sys.exit(1)
    if rewrite_config:
        with open(_config_file, "w") as f:
            json.dump(asdict(_config), f, indent=2)
    config_content = json.dumps(asdict(_config), indent=2)
    if hasattr(_config, "garmin_password") and getattr(_config, "garmin_password") is not None:
        config_content = config_content.replace(cast(str, _config.garmin_password), "<**hidden**>")
    _logger.info(f"Config file is now:\n{config_content}")


if __name__ == "__main__":
    v = sys.version_info
    v_str = f"{v.major}.{v.minor}.{v.micro}"
    min_ver = "3.12.0"
    ver = semver.Version.parse(v_str)
    if not ver >= semver.Version.parse(min_ver):
        msg = f'This program requires Python "{min_ver}" or greater (current version is "{v_str}"). Please upgrade your python version.'
        raise OSError(msg)

    parser = argparse.ArgumentParser(
        description="Tool to add Garmin device information to FIT files and upload them to Garmin Connect. "
        "Currently, only FIT files produced by the TrainingPeaks Virtual (https://www.trainingpeaks.com/virtual/) "
        "are supported."
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        default=[],
        help="the FIT file or directory to process. This argument can be omitted if the 'fitfiles_path'"
        "config value is set (that directory will be used instead). By default, files will just be edited. "
        'Specify the "-u" flag to also upload them to Garmin Connect.',
    )
    parser.add_argument(
        "-s",
        "--initial-setup",
        help="Use this option to interactively initialize the configuration file (.config.json)",
        action="store_true",
    )
    parser.add_argument(
        "-u",
        "--upload",
        help="upload FIT file (after editing) to Garmin Connect",
        action="store_true",
    )
    parser.add_argument(
        "-ua",
        "--upload-all",
        action="store_true",
        help='upload all FIT files in directory (if they are not in "already processed" list)',
    )
    parser.add_argument(
        "-p",
        "--preinitialize",
        help="preinitialize the list of processed FIT files (mark all existing files in directory as already uploaded)",
        action="store_true",
    )
    parser.add_argument(
        "-m",
        "--monitor",
        help="monitor a directory and upload all newly created FIT files as they are found",
        action="store_true",
    )
    parser.add_argument(
        "--dryrun",
        help="perform a dry run, meaning any files processed will not be saved nor uploaded",
        action="store_true",
    )
    parser.add_argument(
        "-v", "--verbose", help="increase verbosity of log output", action="store_true"
    )
    args = parser.parse_args()

    # setup logging before anything else
    if args.verbose:
        _logger.setLevel(logging.DEBUG)
        for logger in [
            "urllib3.connectionpool",
            "oauthlib.oauth1.rfc5849",
            "requests_oauthlib.oauth1_auth",
            "asyncio",
            "watchdog.observers.inotify_buffer",
        ]:
            logging.getLogger(logger).setLevel(logging.INFO)
    else:
        _logger.setLevel(logging.INFO)
        for logger in [
            "urllib3.connectionpool",
            "oauthlib.oauth1.rfc5849",
            "requests_oauthlib.oauth1_auth",
            "asyncio",
            "watchdog.observers.inotify_buffer",
        ]:
            logging.getLogger(logger).setLevel(logging.WARNING)

    # if initial_setup, just do config file building
    if args.initial_setup:
        build_config_file(overwrite_existing_vals=True, rewrite_config=True)
        _logger.info(
            "Config file has been written, now run one of the other options to start editing/uploading files!"
        )
        sys.exit(0)
    if not args.input_path and not (
        args.upload_all or args.monitor or args.preinitialize
    ):
        _logger.error(
            '***************************\nSpecify either "--upload-all", "--monitor", "--preinitialize", or one input file/directory to use\n***************************\n'
        )
        parser.print_help()
        sys.exit(1)
    if args.monitor and args.upload_all:
        _logger.error('***************************\nCannot use "--upload-all" and "--monitor" together\n***************************\n')
        parser.print_help()
        sys.exit(1)

    # check configuration and prompt for values if needed
    excluded_keys = ["fitfiles_path"] if args.input_path else []
    if not config_is_valid(excluded_keys=excluded_keys):
        _logger.warning(
            "Config file was not valid, please fill out the following values."
        )
        build_config_file(
            overwrite_existing_vals=False,
            rewrite_config=True,
            excluded_keys=excluded_keys,
        )

    if args.input_path:
        p = Path(args.input_path).absolute()
        _logger.info(f'Using path "{p}" from command line input')
    else:
        if _config.fitfiles_path is None:
            raise EnvironmentError
        p = Path(_config.fitfiles_path).absolute()
        _logger.info(f'Using path "{p}" from configuration file')

    if not p.exists():
        _logger.error(
            f'Configured/selected path "{p}" does not exist, please check your configuration.'
        )
        sys.exit(1)
    if p.is_file():
        # if p is a single file, do edit and upload
        _logger.debug(f'"{p}" is a single file')
        output_path = edit_fit(p, dryrun=args.dryrun)
        if (args.upload or args.upload_all) and output_path:
            upload(output_path, original_path=p, dryrun=args.dryrun)
    else:
        _logger.debug(f'"{p}" is a directory')
        # if p is directory, do other stuff
        if args.upload_all or args.preinitialize:
            upload_all(p, args.preinitialize, args.dryrun)
        elif args.monitor:
            monitor(p, args.dryrun)
        else:
            files_to_edit = list(p.glob("*.fit", case_sensitive=False))
            _logger.info(f"Found {len(files_to_edit)} FIT files to edit")
            for f in files_to_edit:
                edit_fit(f, dryrun=args.dryrun)
