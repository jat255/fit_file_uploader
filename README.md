# Fit File Faker - a FIT File editor and uploader

This repo contains a tool that will edit [FIT](https://developer.garmin.com/fit/overview/) files
to make them appear to come from a Garmin device (Edge 830, currently) and upload them to Garmin Connect
using the [`garth`](https://github.com/matin/garth/) library. The FIT editing
is done using Stages Cycling's [`fit_tool`](https://bitbucket.org/stagescycling/python_fit_tool/src/main/) library.

The primary use case for this is that [TrainingPeaks Virtual](https://www.trainingpeaks.com/virtual/) (previously 
[indieVelo](https://indievelo.com/)) does not support (AFAIK, Garmin does not allow) automatic uploading to
[Garmin Connect](http://connect.garmin.com/). The files can be manually uploaded after the fact,
but since they are not "from Garmin", they will not be used to calculate Garmin's "Training Effect",
which is used for suggested workouts and other stuff. By changing the FIT file to appear to come
from a Garmin device, those features should be enabled.

Other users have reported using this tool to edit FIT files produced by [Zwift](https://www.zwift.com/)
prior to uploading to Garmin Connect so that activities on that platform will count towards Garmin Connect
badges and challenges (see [1](https://forums.zwift.com/t/garmin-disabled-zwift-rides-badges/528612) and
[2](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-web/251574/zwift-rides-no-longer-count-towards-challenges)).

## Contributors

- [jat255](https://github.com/jat255): Primary author
- [benjmarshall](https://github.com/benjmarshall): bug fixes, monitor mode, and other improvements
- [Kellett](https://github.com/Kellett): support for Zwift FIT files

## Installation

Requires Python 3.12. If your system python is older than that,
[pyenv](https://github.com/pyenv/pyenv) or [uv](https://docs.astral.sh/uv/) can be
used to manage locally installed versions.

This tool should work cross-platform on Windows, MacOS, or Linux, though it is primarily
developed on Linux, so it's possible there are some cross-platform bugs.

### pipx install

If you have [pipx](https://pipx.pypa.io/latest/installation/) installed, a simple

```bash
$ pipx install fit-file-faker
```

will install the tool, and make the script named `fit-file-faker` available on your PATH.

### Manual virtual environment

You can also install manually using `pip`. If so, it's best to create a new
virtual environment:

```bash
$ python -m venv .venv
$ source .venv/bin/activate
```

Then install via pip:

```bash
$ pip install fit-file-faker 
```

The pip package installs a script named `fit-file-faker` that should be available on your
path assuming the virtual envrionment is activated.

### Development install

If you want to install a development version, clone the repo, and use the
[uv](https://docs.astral.sh/uv/):

```bash
$ git clone https://github.com/jat255/fit_file_uploader.git
$ cd fit_file_uploader
$ uv sync  # this installs the dependencies
```

## Configuration

The script uses a configuration file named `.config.json` stored in your system's user config directory
(as determined by the [`platformdirs`](https://github.com/tox-dev/platformdirs) library).
An example is provided in this repo in `.config.json.example`: 

```json
{
  "garmin_username": "username",
  "garmin_password": "password",
  "fitfiles_path": "C:\\Users\\username\\Documents\\TPVirtual\\0123456789ABCDEF\\FITFiles"
}
```

The best way to fill out this config file is to run the "initial setup"
option via the `-s` flag, which will allow you to define the three required values interactively:

```bash
$ fit-file-faker -s

[13:50:02] WARNING  Required value "garmin_username" not found in config                app.py:404
? Enter value to use for "garmin_username" username
[13:50:05] WARNING  Required value "garmin_password" not found in config                app.py:404
? Enter value to use for "garmin_password" ********
[13:50:06] WARNING  Required value "fitfiles_path" not found in config                  app.py:404
           INFO     Getting FITFiles folder                                             app.py:133
           WARNING  TrainingPeaks Virtual user folder can only be automatically         app.py:175
                    detected on Windows and OSX                                                 
? Please enter your TrainingPeaks Virtual data folder (by default, ends with "TPVirtual"):
/home/user/Documents/TPVirtual
? Found TP Virtual User directory at "/home/user/Documents/TPVirtual/0123456789ABCDEF", is this correct?
yes
[13:50:17] INFO     Found TP Virtual User directory: "/home/user/Documents/TPVirtual      app.py:158
                    sync/0123456789ABCEDF", setting "fitfiles_path" in config file              
           INFO     Config file is now:                                                 app.py:440
                    {                                                                           
                      "garmin_username": "username",                                            
                      "garmin_password": "<**hidden**>",                                    
                      "fitfiles_path": "/home/user/Documents/TPVirtual/0123456789ABCDEF/FITFiles"                                             
                    }                                                                           
           INFO     Config file has been written, now run one of the other options      app.py:530
                    to start editing/uploading files! 
```

## Usage

The script has a few options. To see the help, run with the `-h` flag:

```bash
$ fit-file-faker -h
```
```
usage: fit-file-faker [-h] [-s] [-u] [-ua] [-p] [-m] [--dryrun] [-v] [input_path]

Tool to add Garmin device information to FIT files and upload them to Garmin Connect. Currently,
only FIT files produced by TrainingPeaks Virtual (https://www.trainingpeaks.com/virtual/) and
Zwift (https://www.zwift.com/) are supported, but it's possible others may work.


positional arguments:
  input_path           the FIT file or directory to process. This argument can be omitted if
                       the 'fitfiles_path' config value is set (that directory will be used
                       instead). By default, files will just be edited. Specify the "-u" flag
                       to also upload them to Garmin Connect.

options:
  -h, --help           show this help message and exit
  -s, --initial-setup  Use this option to interactively initialize the configuration file
                       (.config.json)
  -u, --upload         upload FIT file (after editing) to Garmin Connect
  -ua, --upload-all    upload all FIT files in directory (if they are not in "already
                       processed" list)
  -p, --preinitialize  preinitialize the list of processed FIT files (mark all existing files
                       in directory as already uploaded)
  -m, --monitor        monitor a directory and upload all newly created FIT files as they are
                       found
  -d, --dryrun         perform a dry run, meaning any files processed will not be saved nor
                       uploaded
  -v, --verbose        increase verbosity of log output
```

### Basic usage

The default behavior with no other options load a given FIT file, and output a file named `path_to_file_modified.fit`
that has been edited, and can be manually imported to Garmin Connect:

```bash
$ fit-file-faker path_to_file.fit
```

If a directory is supplied rather than a single file, all FIT files in that directory will be processed in
the same way.

Supplying the `-u` option will attempt to upload the edited file to Garmin Connect. If
your credentials are not stored in the configuration file, the script will prompt you for them.
The OAuth credentials obtained for the Garmin web service will be stored in a directory
named `.garth` in your system's user cache folder (as determined by
[`platformdirs`](https://github.com/tox-dev/platformdirs)). See the `garth` library's
[documentation](https://github.com/matin/garth/?tab=readme-ov-file#authentication-and-stability)
for details:

```bash
$ fit-file-faker -u path_to_file.fit
```
```
[12:14:06] INFO     Activity timestamp is "2024-05-21T17:15:48"                              app.py:84
           INFO     Saving modified data to path_to_file_modified.fit                        app.py:106
[12:14:08] INFO     ✅ Successfully uploaded "path_to_file.fit"                              app.py:137
```

The `-v` flag can be used (with any of the other options) to provide more debugging output:

```bash
$ fit-file-faker -u path_to_file.fit -v
```
```
[12:38:33] INFO     Activity timestamp is "2024-05-21T17:15:48"                              app.py:84
           DEBUG    Record: 1 - manufacturer: 255 ("DEVELOPMENT") - product: 0 - garmin      app.py:55
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     app.py:87
           DEBUG        New Record: 1 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin  app.py:55
                    product: 3122 ("GarminProduct.EDGE_830")
           DEBUG    Record: 14 - manufacturer: 32 ("WAHOO_FITNESS") - product: 40 - garmin   app.py:55
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     app.py:97
           DEBUG        New Record: 14 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin app.py:55
                    product: 3122 ("GarminProduct.EDGE_830")
           DEBUG    Record: 15 - manufacturer: 32 ("WAHOO_FITNESS") - product: 6 - garmin    app.py:55
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     app.py:97
           DEBUG        New Record: 15 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin app.py:55
                    product: 3122 ("GarminProduct.EDGE_830")
           DEBUG    Record: 16 - manufacturer: 1 ("GARMIN") - product: 18 - garmin product:  app.py:55
                    18 ("BLANK")
           INFO     Saving modified data to                                                 app.py:106
                    "path_to_file_modified.fit"
[12:38:34] DEBUG    Using stored Garmin credentials from ".garth" directory                 app.py:118
[12:38:35] INFO     ✅ Successfully uploaded "path_to_file.fit"                             app.py:137
```

### "Upload all" and "monitor" modes

The `--upload-all` option will search for all FIT files eith in the directory given on the command line,
or in the one specified in the `fitfiles_path` config option. The script will compare the files found to a
list of files already seen (stored in that directory's `.uploaded_files.json` file), edit them, and upload
each to Garmin Connect. The edited files will be written into a temporary file and discarded when the
script finishes running, and the filenames will be stored into a JSON file in the current directory so
they are skipped the next time the script is run.

The upload all function can alternatively be automated using the  `--monitor` option, which will start
watching the filesystem in the specified directory for any new FIT files, and continue running until
the user interrupts the process by pressing `ctrl-c`. Here is an example output when a new file named
`new_fit_file.fit` is detected:

```
$ fit-file-faker --monitor /home/user/Documents/TPVirtual/0123456789ABCEDF/FITFiles

[14:03:32] INFO     Using path "/home/user/Documents/TPVirtual/                    app.py:561
                    0123456789ABCEDF/FITFiles" from command line input                     
           INFO     Monitoring directory: "/home/user/Documents/TPVirtual/         app.py:367
                    0123456789ABCEDF/FITFiles"                                             
[14:03:44] INFO     New file detected - "/home/user/Documents/TPVirtual/           app.py:94
                    0123456789ABCEDF/FITFiles/new_fit_file.fit"; sleeping for              
                    5 seconds to ensure TPV finishes writing file                               
[14:03:50] INFO     Found 1 files to edit/upload                                   app.py:333
           INFO     Processing "new_fit_file.fit"                                  app.py:340
           INFO     Processing "/home/user/Documents/TPVirtual                     app.py:202
                    sync/0123456789ABCEDF/FITFiles/new_fit_file.fit"                            
[14:03:58] INFO     Activity timestamp is "2025-01-03T17:01:45"                    app.py:223
[14:03:59] INFO     Saving modified data to "/tmp/tmpsn4gvpkh"                     app.py:250
[14:04:00] INFO     Uploading modified file to Garmin Connect                      app.py:346
[14:04:01] INFO     Uploading "/tmp/tmpsn4gvpkh" using garth                       app.py:295
^C[14:04:46] INFO     Received keyboard interrupt, shutting down monitor           app.py:372
```

If your TrainingPeaks Virtual user data folder already contains FIT files which you have previously uploaded
to Garmin Connect using a different method then you can pre-initialise the list of uploaded files to avoid
any possibility of uploading duplicates (though these files *should* be rejected by Garmin Connect
if they're exact duplicates). Use the `--preinitialize` option to process a directory (defaults to
the configured TrainingPeaks Virtual user data directory) and add all files to the list of previous uploaded
files. After this any use of the `--upload-all` or `--monitor` options will ignore these pre-existing files.

### Already uploaded files

A note: if a file with the same timestamp already exists on the Garmin Connect account, Garmin
will reject the upload. This script will detect that, and output something like the following:

```bash
$ fit-file-faker -u path_to_file.fit -v
```
```
[13:32:48] INFO     Activity timestamp is "2024-05-10T17:17:34"                              app.py:85
           INFO     Saving modified data to "path_to_file_modified.fit"                      app.py:107
[13:32:49] WARNING  ❌ Received HTTP conflict (activity already exists) for                  app.py:143
                    "path_to_file.fit"
```

## Troubleshooting

If you run into problems, please
[create an issue](https://github.com/jat255/fit_file_uploader/issues/new/choose) on the GitHub
repo. As this is a side-project provided for free (as in speech and beer), support times may vary 😅.

## Disclaimer

The use of any registered or unregistered trademarks owned by third-parties are used only for 
informational purposes and no endorsement of this software by the owners of such trademarks are
implied, explicitly or otherwise. The terms/trademarks indieVelo, TrainingPeaks, TrainingPeaks Virtual,
Garmin Connect, Stages Cycling, and any others are used under fair use doctrine solely to
facilitate understanding.
