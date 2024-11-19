"""
Takes a .fit file produced by indieVelo and modifies the fields so that Garmin
will think it came from a Garmin device and use it to determine training effect.

Simulates an Edge 830 device
"""
import argparse
from datetime import datetime
import os
import json
import logging
import sys
import time
from watchdog.observers import Observer
from watchdog.events import PatternMatchingEventHandler
import yaml
import re

from tempfile import NamedTemporaryFile
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from pick import pick

_logger = logging.getLogger('garmin')

# fit_tool configures logging for itself, so need to do this before importing it
logging.basicConfig(
    level=logging.NOTSET, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(markup=True)]
)
logging.basicConfig()
_logger.setLevel(logging.INFO)
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
logging.getLogger('oauth1_auth').setLevel(logging.WARNING)

from fit_tool.fit_file import FitFile
from fit_tool.profile.messages.device_info_message import DeviceInfoMessage
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.profile_type import Manufacturer, GarminProduct
from fit_tool.fit_file_builder import FitFileBuilder


load_dotenv()
c = Console()

EDGE830 = GarminProduct.EDGE_830
GARMIN = Manufacturer.GARMIN
FILES_UPLOADED_NAME = Path('.uploaded_files.json')
CONFIG_FILE = Path('.config')

class FitFileLogFilter(logging.Filter):
    """Filter to remove specific warning from the fit_tool module"""
    def filter(self, record):
        res = not '\n\tactual: ' in record.getMessage()
        return res
logging.getLogger('fit_tool').addFilter(FitFileLogFilter())

class NewFileEventHandler(PatternMatchingEventHandler):
    def __init__(self):
        PatternMatchingEventHandler.__init__(self, patterns=['*.fit'],
                                                             ignore_directories=True, case_sensitive=False)
    def on_created(self, event) -> None:
        _logger.debug("New file created - % s." % event.src_path)
        upload_all(Path(event.src_path).parent.absolute())

def print_message(prefix, message):
    man = Manufacturer(message.manufacturer).name if message.manufacturer in Manufacturer else "BLANK"
    gar_prod = GarminProduct(message.garmin_product) if message.garmin_product in GarminProduct else "BLANK"
    _logger.debug(f"{prefix} - manufacturer: {message.manufacturer} (\"{man}\") - "
              f"product: {message.product} - garmin product: {message.garmin_product} (\"{gar_prod}\")")
    
def first_run():
    _logger.info(f"Running first time setup")
    TPVPath = os.path.expanduser('~/Documents/TPVirtual')
    res = [f for f in os.listdir(TPVPath) if re.search(r'\A(\w){16}\Z', f)]
    if len(res) == 0:
        _logger.error('Cannot find a TP Virtual User folder in %s, please check if you have previously logged into TP Virtual', TPVPath)
        sys.exit(1)
    elif len(res) == 1:
        title = 'First run setup found TP Virtual User directory at ' + str(Path(TPVPath).joinpath(res[0])) + ', is this correct? '
        option, index = pick(['yes', 'no'], title)
        if option == 'no':
            _logger.error('First setup failed to find correct TP Virtual User folder please manually configure TPV_ID in config file: %s', CONFIG_FILE.absolute())
            with CONFIG_FILE.open('w') as f:
                yaml.dump({'TPV_ID': ''},f)
            sys.exit(1)
        else:
            index=0
    else:
        title = 'First run setup found multiple TP Virtual User directories, please select the directory for your user: '
        option, index = pick(res, title)
    TPVIDPath = Path(TPVPath).joinpath(res[index])
    _logger.info(f"Found TP Virtual User directory: {str(TPVIDPath.absolute())}, setting TPV_ID key in config file")
    with CONFIG_FILE.open('w') as f:
        yaml.dump({'TPV_ID': res[index]},f)

    email = os.environ.get('GARMIN_USERNAME', None)
    password = os.environ.get('GARMIN_PASSWORD', None)
    if not email or not password:
        title = 'Your environment has not specified your Garmin credentials. For the daemon mode to work these must be available as environment variables in your system, or stored in a local environment file. Would you like to store these now? '
        option, index = pick(['yes', 'no'], title)
        if option == 'yes':
            print("Please enter your Garmin Connect username:")
            user = input()
            print("Please enter your Garmin Connect password:")
            password = input()
            envFileContents = "GARMIN_USERNAME=\'%s\'\nGARMIN_PASSWORD=\'%s\'" % (user,password)
            with open(".env", "w") as f:
                f.write(envFileContents)
            _logger.info(f"Stored Garmin credentials in {str(Path('.env').absolute())}")

def get_date_from_fit(fit_path: Path) -> Optional[datetime]:
    fit_file = FitFile.from_file(str(fit_path))
    res = None
    for i, record in enumerate(fit_file.records):
        message = record.message
        if message.global_id == FileIdMessage.ID:
            if isinstance(message, FileIdMessage):
                res = datetime.fromtimestamp(message.time_created/1000.0) # type: ignore
                break
    return res

def edit_fit(fit_path: Path, output: Optional[Path] = None, dryrun: bool = False) -> Path:
    fit_file = FitFile.from_file(str(fit_path))
    if not output:
        output = fit_path.parent / f"{fit_path.stem}_modified.fit"

    builder = FitFileBuilder(auto_define=False)
    dt = None
    # loop through records, find the one we need to change, and modify the values:
    for i, record in enumerate(fit_file.records):
        message = record.message
        
        # change file id to indicate file was saved by Edge 830
        if message.global_id == FileIdMessage.ID:
            if isinstance(message, FileIdMessage):
                dt = datetime.fromtimestamp(message.time_created/1000.0)   # type: ignore
                _logger.info(f"Activity timestamp is \"{dt.isoformat()}\"")
                print_message(f"Record: {i}", message)
                if message.manufacturer == Manufacturer.DEVELOPMENT.value:
                    _logger.debug('    Modifying values')
                    message.product = GarminProduct.EDGE_830.value
                    message.manufacturer = Manufacturer.GARMIN.value
                    print_message(f"    New Record: {i}", message)
        
        # change device info messages
        if message.global_id == DeviceInfoMessage.ID:
            if isinstance(message, DeviceInfoMessage):
                print_message(f"Record: {i}", message)
                if message.manufacturer == Manufacturer.DEVELOPMENT.value or message.manufacturer == 0 or message.manufacturer == Manufacturer.WAHOO_FITNESS.value:
                    _logger.debug('    Modifying values')
                    message.garmin_product = GarminProduct.EDGE_830.value
                    message.product = GarminProduct.EDGE_830.value                                # type: ignore
                    message.manufacturer = Manufacturer.GARMIN.value
                    print_message(f"    New Record: {i}", message)

        builder.add(message)

    modified_file = builder.build()
    _logger.info(f"Saving modified data to \"{output}\"")
    if not dryrun:
        modified_file.to_file(str(output))
    return output
    
def upload(fn: Path, original_path: Optional[Path] = None, dryrun: bool = False):
    # get credentials and login if needed
    import garth
    from garth.exc import GarthException, GarthHTTPError

    try:
        garth.resume(".garth")
        garth.client.username
        _logger.debug("Using stored Garmin credentials from \".garth\" directory")
    except (GarthException, FileNotFoundError):
        # Session is expired. You'll need to log in again
        _logger.info("Authenticating to Garmin Connect")
        email = os.environ.get('GARMIN_USERNAME', None)
        password = os.environ.get('GARMIN_PASSWORD', None)
        if not email: 
            email = c.input("No \"GARMIN_USERNAME\" variable set; Enter email address: ")
        _logger.debug(f"Using username \"{email}\"")
        if not password:
            password = c.input("No \"GARMIN_PASSWORD\" variable set; Enter password: ", password=True)
            _logger.debug("Using password from user input")
        else:
            _logger.debug("Using password stored in \"GARMIN_PASSWORD\"")
        garth.login(email, password)
        garth.save(".garth")
        
    with fn.open('rb') as f:
        try:
            if not dryrun:
                upload_result = garth.client.upload(f)
            _logger.info(f':white_check_mark: Successfully uploaded "{str(original_path)}"')
            return upload_result
        except GarthHTTPError as e:
            if e.error.response.status_code == 409:
                _logger.warning(f":x: Received HTTP conflict (activity already exists) for \"{str(original_path)}\"")
            else:
                raise e
    
def upload_all(dir: Path, preinitialise: bool = False, dryrun: bool = False):
    files_uploaded = dir.joinpath(FILES_UPLOADED_NAME)
    if files_uploaded.exists():
        # load uploaded file list from disk
        with files_uploaded.open('r') as f:
            uploaded_files = json.load(f)
    else:
        uploaded_files = []
        with files_uploaded.open('w') as f:
            # write blank file
            json.dump(uploaded_files, f, indent=2)
    _logger.debug(f"Found the following already uploaded files: {uploaded_files}")
    abs_dir = str(dir.absolute())
    
    # glob all .fit files in the current directory
    files = [str(i) for i in dir.glob('*.fit', case_sensitive=False)]
    # strip any leading/trailing slashes from filenames
    files = [i.replace(str(dir), '').strip('/').strip('\\') for i in files]
    # remove files matching what we may have already processed
    files = [i for i in files if not i.endswith('_modified.fit')]
    # remove files found in the "already uploaded" list
    files = [i for i in files if not i in uploaded_files]
    
    _logger.info(f"Found {len(files)} files to edit/upload")
    _logger.debug(f"Files to upload: {files}")
    
    if not files:
        return
    
    for f in files:
        _logger.info(f"Processing \"{f}\"")  # type: ignore
        
        if not preinitialise:
            with NamedTemporaryFile(delete=True, delete_on_close=False) as fp:
                try:
                    output = edit_fit(Path(f), output=Path(fp.name))
                    _logger.info(f"Uploading modified file to Garmin Connect")
                    res = upload(output, original_path=Path(f), dryrun=dryrun)
                except:
                    _logger.warning(f"Failed  to modify file \"{f}\", possibly malformed FIT file.")
        _logger.debug(f"Adding \"{f}\" to \"uploaded_files\"")
        uploaded_files.append(f)
    
    if not dryrun:
        with files_uploaded.open('w') as f:
            json.dump(uploaded_files, f, indent=2)

def daemonise(watch_dir: Path):
    email = os.environ.get('GARMIN_USERNAME', None)
    password = os.environ.get('GARMIN_PASSWORD', None)
    if not email or not password:
        _logger.error('Your environment has not specified your Garmin credentials. For the daemon mode to work these must be available as environment variables in your system, or stored in a local environment file.')
        sys.exit(1)
        
    event_handler = NewFileEventHandler()
    observer = Observer()
    observer.schedule(event_handler, watch_dir, recursive=False)
    observer.start()
    _logger.info(f"Monitoring directory: {watch_dir.absolute()}")
    try:
        while True:
            time.sleep(300)
    except KeyboardInterrupt as e:
        _logger.info(f"Received keyboard interrupt, shutting down monitor")
    finally:
        observer.stop()
        observer.join()

if __name__ == '__main__':    
    parser = argparse.ArgumentParser(description="Tool to add Garmin device information to FIT files and upload them to Garmin Connect")
    parser.add_argument("input_file", nargs='?', default=[], help="the FIT file or directory to process")
    parser.add_argument("-u", "--upload", help="upload FIT file (after editing) to Garmin Connect", action="store_true")
    parser.add_argument(
        "-ua", 
        "--upload-all",  
        action="store_true",
        help="upload all FIT files in directory (if they are not in \"already processed\" list)"
    )
    parser.add_argument('-p', '--preinitialise', help='preinitialise the list of processed FIT files', action='store_true')
    parser.add_argument('-d','--daemonise',help='monitor a directory and upload all newly created FIT files',action='store_true')
    parser.add_argument('--dryrun', help='perform a dry run', action='store_true')
    parser.add_argument('-v', '--verbose', help='increase verbosity of log output', action='store_true')
    args = parser.parse_args()
    if not args.input_file and not (args.upload_all or args.daemonise or args.preinitialise):
        _logger.error('Specify either "--upload-all" or one input file/directory to use')
        parser.print_help()
        sys.exit(1)
    if args.daemonise and args.upload_all:
        _logger.error('Cannot use "--upload-all" and "--daemonise"')
        parser.print_help()
        sys.exit(1)
    if args.verbose:
        _logger.setLevel(logging.DEBUG)
        for l in ['urllib3.connectionpool', 'oauthlib.oauth1.rfc5849', 'requests_oauthlib.oauth1_auth']:
            logging.getLogger(l).setLevel(logging.INFO)
    else:
        _logger.setLevel(logging.INFO)
        for l in ['urllib3.connectionpool', 'oauthlib.oauth1.rfc5849', 'requests_oauthlib.oauth1_auth']:
            logging.getLogger(l).setLevel(logging.WARNING)
    if not CONFIG_FILE.is_file():
        first_run()
    config = yaml.safe_load(open(CONFIG_FILE))
    if args.upload_all or args.preinitialise:
        if not args.input_file:
            watch_dir = Path(os.path.expanduser('~/Documents/TPVirtual')).joinpath(config['TPV_ID']).joinpath('FITFiles')
        else:
            watch_dir = args.input_file
        upload_all(Path(watch_dir), args.preinitialise, args.dryrun)
    elif args.daemonise:
        if not args.input_file:
            watch_dir = Path(os.path.expanduser('~/Documents/TPVirtual')).joinpath(config['TPV_ID']).joinpath('FITFiles')
        else:
            watch_dir = args.input_file
        daemonise(Path(watch_dir))
    else:
        p = Path(args.input_file)
        output_path = edit_fit(p, dryrun=args.dryrun)
        if args.upload:
            upload(output_path, original_path=p, dryrun=args.dryrun)
