# Rebuilding Lee Davison's Website

> ⚠️ *If you have any backups of Lee Davison's website from any time period, or
if you downloaded any individual files from his website, please [get in touch](https://github.com/mnaberez) via email or [open an issue](https://github.com/6502org/mycorner/issues) on this repository. Many files are still missing and we need your help to find them.* ⚠️

Lee Davison [passed away](http://forum.6502.org/viewtopic.php?f=5&t=3024) on September 21, 2013.  When news of his passing spread months later, Lee's website was already down.  No complete backup of the last version of his website is known to exist.  This project rebuilds Lee's website by combining all files that have been found.

## Approach

Lee's website was online for over a decade.  Over the years, it had these hosts:

 - `http://mycorner.no-ip.org/` (most recent)
 - `http://themotionstore.com/leeedavison/`
 - `http://members.lycos.co.uk/leedavison/`
 - `http://members.multimania.co.uk/leeedavison/`
 - `http://www.geocities.com/leeedavison/`

All available captures of these websites have been downloaded and stored in [`websites/`](./websites)
in this repository.  A build script indexes all files and then combines them into a single website.  The most recent copy of each file, based on the capture date, is used.  Special preference is given to files from `mycorner.no-ip.org`.  Many truncated or otherwise corrupted files are removed.  Tracking and advertising JavaScript inserted into the pages by the free web hosts is also removed.

The result is imperfect and many files are still missing.  However, it is the most complete collection of Lee's work that we have.  Files from all the various hosts and years ended up being used.  Lee helpfully put a "Last updated" date in the footer of all pages.

## Build

Requires a Unix-like system with Python 3.8 or later:

```text
$ python3 build.py

$ python3 -m http.server --bind 127.0.0.1 --directory combined/ 8000
```

The combined files will be written to `combined/`.  Open a browser to http://127.0.0.1:8000/ to view.

It may not be necessary to run build the files locally or run a webserver to view them.  The most recent [GitHub Actions](https://github.com/6502org/mycorner/actions) run may have the combined files (see "Artifacts").  The website should work if the local file `combined/index.html` is opened in a browser.

## Credits

The following captures were used in this project:

 - [Wayback Machine](https://archive.org/web/) - Provided the majority of the captures.  Although no captures were complete and many files had silent corruption, this project would not have otherwise been possible.

 - [Phil Pemberton](https://www.philpem.me.uk/) - Published his own [capture](https://www.philpem.me.uk/leeedavison/) of Lee's website.  The exact date of capture is unknown.  These files have been given a capture date of 2003-06-04, since that is the most recent date found in the "Last updated" footer of the pages.
