# indieVelo to Garmin Connect editor/uploader

This repo contains a script `garmin.py` that will edit [FIT](https://developer.garmin.com/fit/overview/) files
to make them appear to come from a Garmin device (Edge 830, currently) and upload them to Garmin Connect
using the [`garth`](https://github.com/matin/garth/) library. The FIT editing
is done using Stages Cycling's [`fit_tool`](https://bitbucket.org/stagescycling/python_fit_tool/src/main/) library.

My primary use case for this is that [indieVelo](https://indievelo.com/) does not support (AFAIK, Garmin does not allow)
automatic uploading to [Garmin Connect](http://connect.garmin.com/). The files can be manually uploaded after the fact,
but since they are not "from Garmin", they will not be used to calculate Garmin's "Training Effect",
which is used for suggested workouts and other stuff. By changing the FIT file to appear to come
from a Garmin device, those features will be should be enabled.

## Installation

Required Python 3.12. If your system python is older than that, I recommend
using [pyenv](https://github.com/pyenv/pyenv) to manage locally installed versions.

It's probably best to create a new virtual environment:

```bash
$ python -m venv .venv
$ source .venv/bin/activate
```

Then install the requirements:

```bash
(.venv) $ pip install -r requirements.txt 
```

## Usage

The script is pretty simple, and has a couple options. To see the help, run with the `-h` flag:

```bash
(.venv) $ python garmin.py -h
```
```
usage: garmin.py [-h] [-u] [-ua] [-v] [input_file]

Tool to add Garmin device information to FIT files and upload them to Garmin Connect

positional arguments:
  input_file         the Garmin FIT file to modify

options:
  -h, --help         show this help message and exit
  -u, --upload       upload FIT file (after editing) to Garmin Connect
  -ua, --upload-all  upload all FIT files in current directory (if they are not in "already processed"
                     list -- will override other all options)
  -v, --verbose      increase verbosity of log output
```

The default behavior will load the FIT file, and output a file named `path_to_file_modified.fit`
that has been edited, and can be manually imported to Garmin Connect:

```bash
(.venv) $ python garmin.py path_to_file.fit
```

Supplying the `-u` option will attempt to upload the edited file to Garmin Connect. Credentials
can be supplied either as environment variables named `GARMIN_USERNAME` and `GARMIN_PASSWORD`,
or by putting those values in a `.env` file in the same directory as this script (see `.env.example`).
Alternatively, if neither option is supplied, the script will prompt you interactively for a username/email
and password. The OAuth credentials will be stored in a local directory named `./.garth` (see
that library's [documentation](https://github.com/matin/garth/?tab=readme-ov-file#authentication-and-stability))
for details:

```bash
(.venv) $ python garmin.py -u path_to_file.fit
```
```
[12:14:06] INFO     Activity timestamp is "2024-05-21T17:15:48"                              garmin.py:84
           INFO     Saving modified data to path_to_file_modified.fit                        garmin.py:106
[12:14:08] INFO     ✅ Successfully uploaded "path_to_file.fit"                              garmin.py:137
```

The `-v` flag can be used (with any of the other options) to provide more debugging output:

```bash
(.venv) $ python garmin.py -u path_to_file.fit -v
```
```
[12:38:33] INFO     Activity timestamp is "2024-05-21T17:15:48"                              garmin.py:84
           DEBUG    Record: 1 - manufacturer: 255 ("DEVELOPMENT") - product: 0 - garmin      garmin.py:55
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     garmin.py:87
           DEBUG        New Record: 1 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin  garmin.py:55
                    product: 3122 ("GarminProduct.EDGE_830")
           DEBUG    Record: 14 - manufacturer: 32 ("WAHOO_FITNESS") - product: 40 - garmin   garmin.py:55
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     garmin.py:97
           DEBUG        New Record: 14 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin garmin.py:55
                    product: 3122 ("GarminProduct.EDGE_830")
           DEBUG    Record: 15 - manufacturer: 32 ("WAHOO_FITNESS") - product: 6 - garmin    garmin.py:55
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     garmin.py:97
           DEBUG        New Record: 15 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin garmin.py:55
                    product: 3122 ("GarminProduct.EDGE_830")
           DEBUG    Record: 16 - manufacturer: 1 ("GARMIN") - product: 18 - garmin product:  garmin.py:55
                    18 ("BLANK")
           INFO     Saving modified data to                                                 garmin.py:106
                    "path_to_file_modified.fit"
[12:38:34] DEBUG    Using stored Garmin credentials from ".garth" directory                 garmin.py:118
[12:38:35] INFO     ✅ Successfully uploaded "path_to_file.fit"                             garmin.py:137
```

The way I personally use this script is with the `--upload-all` option, which will search
for all FIT files in the current directory, compare them to a list of files already seen (stored in
`.uploaded_files.json`) edit them, and upload each to Garmin Connect. The edited files will be written
into a temporary file and discarded when the script finishes running, and the filenames will be stored
into a JSON file in the current directory so they are skipped the next time the script is run.
This script can be scheduled to run on a regular basis to effectively "watch" a given directory and upload
any FIT files it finds. I have this configured to watch the `FITFiles` directory of my indieVelo
installation so activities are automatically uploaded soon after they are created. This can be done with
cron, systemd, the windows task scheduler, etc.:

```bash
(.venv) $ python garmin.py --upload-all -v
```
```
[13:26:56] DEBUG    Found the following already uploaded files: []                           garmin.py:157
           INFO     Found 5 files to edit/upload                                             garmin.py:164
           DEBUG    Files to upload: ['fit_file_1.fit',                                      garmin.py:165
                    'fit_file_2.fit',
                    'fit_file_3.fit',
                    'fit_file_4.fit',
                    'fit_file_5.fit']
           INFO     Processing "fit_file_1.fit"                                              garmin.py:171
[13:26:59] INFO     Activity timestamp is "2024-05-20T17:11:55"                              garmin.py:85
           DEBUG    Record: 1 - manufacturer: 255 ("DEVELOPMENT") - product: 0 - garmin      garmin.py:56
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     garmin.py:88
           DEBUG        New Record: 1 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin  garmin.py:56
....
[13:27:00] INFO     Saving modified data to "/tmp/tmpljc9mx67"                               garmin.py:107
           INFO     Uploading modifed file to Garmin Connect                                 garmin.py:175
           INFO     Authenticating to Garmin Connect                                         garmin.py:122
           DEBUG    Using username "user"                                                    garmin.py:127
           DEBUG    Using password stored in "GARMIN_PASSWORD"                               garmin.py:132
[13:27:04] INFO     ✅ Successfully uploaded "fit_file_1.fit"                                garmin.py:139
           DEBUG    Adding "fit_file_1.fit" to "uploaded_files"                              garmin.py:177
           INFO     Processing "fit_file_2.fit"                                              garmin.py:171
[13:27:07] INFO     Activity timestamp is "2024-05-10T17:17:34"                              garmin.py:85
           DEBUG    Record: 1 - manufacturer: 255 ("DEVELOPMENT") - product: 0 - garmin      garmin.py:56
                    product: None ("BLANK")
           DEBUG        Modifying values                                                     garmin.py:88
           DEBUG        New Record: 1 - manufacturer: 1 ("GARMIN") - product: 3122 - garmin  garmin.py:56
....
           INFO     Saving modified data to "/tmp/tmpvb_npaxt"                               garmin.py:107
           INFO     Uploading modifed file to Garmin Connect                                 garmin.py:175
[13:27:08] DEBUG    Using stored Garmin credentials from ".garth" directory                  garmin.py:119
           INFO     ✅ Successfully uploaded "fit_file_2.fit"                                garmin.py:139
           DEBUG    Adding "fit_file_2.fit" to "uploaded_files"                              garmin.py:177
           INFO     Processing "fit_file_3.fit"                                              garmin.py:171
[13:27:12] INFO     Activity timestamp is "2024-05-14T16:42:09"                              garmin.py:85
....
[13:27:13] INFO     Saving modified data to "/tmp/tmprt3nt1wq"                               garmin.py:107
           INFO     Uploading modifed file to Garmin Connect                                 garmin.py:175
           DEBUG    Using stored Garmin credentials from ".garth" directory                  garmin.py:119
[13:27:14] INFO     ✅ Successfully uploaded "fit_file_3.fit"                                garmin.py:139
           DEBUG    Adding "fit_file_3.fit" to "uploaded_files"                              garmin.py:177
           INFO     Processing "fit_file_4.fit"                                              garmin.py:171
[13:27:17] INFO     Activity timestamp is "2024-05-21T17:15:48"                              garmin.py:85
....
[13:27:18] INFO     Saving modified data to "/tmp/tmpqkh5iygz"                               garmin.py:107
           INFO     Uploading modifed file to Garmin Connect                                 garmin.py:175
           DEBUG    Using stored Garmin credentials from ".garth" directory                  garmin.py:119
[13:27:19] INFO     ✅ Successfully uploaded "fit_file_4.fit"                                garmin.py:139
           DEBUG    Adding "fit_file_4.fit" to "uploaded_files"                              garmin.py:177
           INFO     Processing "fit_file_5.fit"                                              garmin.py:171
[13:27:21] INFO     Activity timestamp is "2024-05-13T16:57:41"                              garmin.py:85
....
[13:27:22] INFO     Saving modified data to "/tmp/tmpd04eg3b8"                               garmin.py:107
           INFO     Uploading modifed file to Garmin Connect                                 garmin.py:175
           DEBUG    Using stored Garmin credentials from ".garth" directory                  garmin.py:119
[13:27:23] INFO     ✅ Successfully uploaded "fit_file_5.fit"                                garmin.py:139
           DEBUG    Adding "fit_file_5.fit" to "uploaded_files"                              garmin.py:177
```

### Already uploaded files

A note: if a file with the same timestamp already exists on the Garmin Connect account, Garmin
will reject the upload. This script will detect that, and output something like the following:

```bash
(.venv) $ python garmin.py -u path_to_file.fit -v
```
```
[13:32:48] INFO     Activity timestamp is "2024-05-10T17:17:34"                              garmin.py:85
           INFO     Saving modified data to "path_to_file_modified.fit"                      garmin.py:107
[13:32:49] WARNING  ❌ Received HTTP conflict (activity already exists) for                  garmin.py:143
                    "path_to_file.fit"
```

## Disclaimer

The use of any registered or unregistered trademarks owned by third-parties are used only for 
informational purposes and no endorsement of this software by the owners of such trademarks are
implied, explicity or otherwise.
